"""Dados de exemplo de `resultados/` (spec 3.2) para desenvolver e testar o dashboard sem a API.

  python -m dashboard.exemplo PASTA      # grava os arquivos de exemplo em PASTA
  RESULTADOS_DIR=PASTA streamlit run dashboard/app.py

Os arquivos seguem o formato real do juiz (regulamento 12.3). As séries são sintéticas, mas coerentes
com as métricas: mesmo número de perdas e de retiradas, pico e energia calculados a partir da potência.
Tudo é determinístico (semente fixa).
"""
import json
import math
import random
import sys
from pathlib import Path

from recarga import chave
from kickoff import tempo

AGENCIA = "Bangkok"
HORARIO = [(480, 1080)] * 5 + [(480, 720), None]  # Seg..Dom, como em Bangkok/agencias.md
PASSO = 15
JANELAS = 28 * 96  # 4 semanas públicas
PESOS_REAIS = {"certo": 10.0, "upgrade": 6.0, "nao_atendido": -12.0, "demanda_contratada": -3.0,
               "energia_ponta_kwh": -0.25, "infraestrutura": -2.0}
CUSTO_OBRA = {"ac_7": 2, "ac_11": 3, "dc_30": 8, "ac_22x2": 7, "dc_60x2": 18, "b3_75": 6, "a4_150": 14}  # pontos

SUB_A = {"agencia": AGENCIA, "carregadores": {"ac_22x2": 1, "dc_60x2": 2}, "entrada": "a4_150",
         "demanda_contratada_kw": 90,
         "politica": {"prioridade": "proxima_retirada", "evitar_ponta": True, "divisao": "prioridade"}}
SUB_B = {"agencia": AGENCIA, "carregadores": {"ac_7": 2, "dc_30": 1}, "entrada": "b3_45",
         "demanda_contratada_kw": None,
         "politica": {"prioridade": "menor_soc", "evitar_ponta": False, "divisao": "igual"}}
OUTRAS = (
    {"agencia": AGENCIA, "carregadores": {"ac_22x2": 1, "dc_60x2": 2}, "entrada": "b3_75",
     "demanda_contratada_kw": None,
     "politica": {"prioridade": "proxima_retirada", "evitar_ponta": True, "divisao": "prioridade"}},
    {"agencia": AGENCIA, "carregadores": {"dc_60x2": 3}, "entrada": "a4_150", "demanda_contratada_kw": 90,
     "politica": {"prioridade": "proxima_retirada", "evitar_ponta": True, "divisao": "prioridade"}},
    {"agencia": AGENCIA, "carregadores": {"ac_11": 3, "dc_30": 1}, "entrada": "b3_75",
     "demanda_contratada_kw": None,
     "politica": {"prioridade": "chegada", "evitar_ponta": False, "divisao": "igual"}},
)


def hash_sub(sub: dict) -> str:
    return chave.chave(sub, [])


def _intensidade(t: int, evitar_ponta: bool) -> float:
    """Perfil de carga (0..1) ao longo da semana: pico no horário comercial e recarga noturna."""
    dia = tempo.dia_semana(t)
    h = (t % 1440) / 60
    if dia == 6:  # domingo fechado: só terminam recargas
        v = 0.2 if h >= 7 else 0.1
    elif HORARIO[dia][0] / 60 <= h < HORARIO[dia][1] / 60:
        v = 0.45 + 0.4 * math.sin(math.pi * (h - 8) / ((HORARIO[dia][1] - HORARIO[dia][0]) / 60))
    elif h >= HORARIO[dia][1] / 60:
        v = max(0.15, 0.95 - 0.13 * (h - HORARIO[dia][1] / 60))
    else:
        v = 0.45 if h < 6 else 0.25
    if evitar_ponta:
        if tempo.eh_ponta(t):
            v *= 0.06
        elif 21 <= h < 24 or h < 6:
            v *= 1.3
    return v


def _series(semente: int, limite: float, saidas: int, vagas: int, unidade: float, carga: float,
            evitar_ponta: bool, n_perdas: int, n_retiradas: int) -> dict:
    rng = random.Random(semente)
    ini = tempo.T0
    pot, plug, fila = [], [], []
    for k in range(JANELAS):
        t = ini + PASSO * k
        p = min(limite, max(0.0, _intensidade(t, evitar_ponta) * carga * limite * rng.uniform(0.75, 1.2)))
        n = min(saidas, int(-(-p // unidade))) if p > 0.3 else 0
        f = rng.choice((0, 1, 1, 2, 3)) if p >= 0.97 * limite else 0
        pot.append(round(p, 4))
        plug.append(n)
        fila.append(max(0, min(f, vagas - n)))
    janelas = [k for k in range(JANELAS) if HORARIO[tempo.dia_semana(ini + PASSO * k)] is not None
               and HORARIO[tempo.dia_semana(ini + PASSO * k)][0] <= (ini + PASSO * k) % 1440
               < HORARIO[tempo.dia_semana(ini + PASSO * k)][1]]
    pesos = []
    for k in janelas:
        t = ini + PASSO * k
        h = (t % 1440) / 60
        pesos.append((1.6 if tempo.dia_semana(t) in (0, 4, 5) else 1.0) * (1.8 if 8 <= h < 10 or 16 <= h < 18 else 1.0))
    perdas = sorted(float(PASSO * k + rng.randrange(PASSO)) for k in rng.choices(janelas, pesos, k=n_perdas))
    soc = [round(min(100.0, 80 + 20 * rng.betavariate(1.3, 2.6)), 1) for _ in range(n_retiradas)]
    return {"inicio_min": ini, "passo_min": PASSO, "potencia_kw": pot, "plugados_max": plug, "fila_max": fila,
            "nao_atendidos_min": perdas, "soc_retirada": soc}


def _fisicas(series: dict, contratos: int) -> dict:
    pot = series["potencia_kw"]
    nao = len(series["nao_atendidos_min"])
    ponta = sum(p * PASSO / 60 for k, p in enumerate(pot) if tempo.eh_ponta(series["inicio_min"] + PASSO * k))
    return {"contratos": contratos, "atendimento_pct": 100.0 * (contratos - nao) / contratos,
            "pico_kw": max(pot), "energia_kwh": sum(pot) * PASSO / 60, "energia_ponta_kwh": ponta}


def _obra(sub: dict, existente: str = "b3_45") -> int:
    total = sum(n * CUSTO_OBRA[k] for k, n in sub["carregadores"].items())
    return total + (0 if sub["entrada"] == existente else CUSTO_OBRA[sub["entrada"]])


def _pontos(m: dict) -> dict:
    itens = []
    for item, chave_m in (("certo", "certos"), ("upgrade", "upgrades"), ("nao_atendido", "nao_atendidos"),
                          ("demanda_contratada", "demanda_contratada_kw"),
                          ("energia_ponta_kwh", "energia_ponta_kwh"), ("infraestrutura", "custo_infra")):
        itens.append([item, m[chave_m], PESOS_REAIS[item], m[chave_m] * PESOS_REAIS[item]])
    return {"itens": itens, "nota": sum(i[3] for i in itens)}


def _candidato_a() -> tuple:
    """Resposta do juiz (fase Clara, com `pontos`) e saída do nosso motor para a submissão A."""
    contratos, nao, ret = 271, 13, 258
    s = _series(11, 90.0, 6, 6, 30.0, 0.78, True, nao, ret)
    fis = _fisicas(s, contratos)
    certos, upgrades = 236, ret - 236
    m = {**fis, "certos": certos, "upgrades": upgrades, "nao_atendidos": nao, "demanda_contratada_kw": 90.0,
         "custo_infra": _obra(SUB_A)}
    pontos = _pontos(m)
    metricas_juiz = {k: m[k] for k in ("contratos", "atendimento_pct", "pico_kw", "energia_kwh", "certos", "upgrades",
                                       "nao_atendidos", "energia_ponta_kwh", "demanda_contratada_kw", "custo_infra")}
    juiz = {"agencia": AGENCIA, "periodo": "publico", "valido": True, "erros": [], "violacoes": [],
            "nota": pontos["nota"], "metricas": metricas_juiz, "taxa": 20, "saldo": 980, "repetido": False,
            "series": s, "pontos": pontos, "custo_infra": m["custo_infra"]}
    meu_m = {**m, "energia_kwh": m["energia_kwh"] * 1.002}  # dentro da tolerância de 1% da energia
    sim = {"agencia": AGENCIA, "periodo": "publico", "valido": True, "erros": [], "violacoes": [],
           "metricas": meu_m, "pontos": pontos, "nota": pontos["nota"],
           "custo_infra": {"carregadores": _obra(SUB_A) - CUSTO_OBRA["a4_150"], "entrada": CUSTO_OBRA["a4_150"],
                           "total": m["custo_infra"]},
           "series": {"publico": s}}
    return juiz, sim, m


def _candidato_b() -> tuple:
    """Resposta do juiz (fase Neblina: sem `pontos`) e saída do nosso motor, com uma divergência."""
    contratos, nao, ret = 271, 66, 205
    s = _series(23, 40.5, 3, 6, 15.0, 1.25, False, nao, ret)
    fis = _fisicas(s, contratos)
    certos, upgrades = 190, ret - 190
    m = {**fis, "certos": certos, "upgrades": upgrades, "nao_atendidos": nao, "demanda_contratada_kw": 0.0,
         "custo_infra": _obra(SUB_B)}
    nota_oculta = _pontos(m)["nota"]
    juiz = {"agencia": AGENCIA, "periodo": "publico", "valido": True, "erros": [], "violacoes": [],
            "nota": nota_oculta,
            "metricas": {k: m[k] for k in ("contratos", "atendimento_pct", "pico_kw", "energia_kwh")},
            "taxa": 0, "saldo": 1000, "repetido": False, "series": s}
    s_meu = {**s, "potencia_kw": list(s["potencia_kw"])}
    s_meu["potencia_kw"][1500] += 0.8  # divergência pontual, para exercitar a tabela de fidelidade
    sim = {"agencia": AGENCIA, "periodo": "publico", "valido": True, "erros": [], "violacoes": [],
           "metricas": {**m, "pico_kw": m["pico_kw"] + 0.03}, "nota": None,
           "aviso": "nota não calculada: custos e pesos só saem em GET /catalogo depois de H4.",
           "series": {"publico": s_meu}}
    return juiz, sim, m


def _curva_demanda(nota_ref: float, base_b3: float) -> list:
    pontos = []
    for d in range(30, 140, 10):
        perdas_extra = max(0.0, (90 - d) / 10) ** 1.8 * 3.5
        ganho = 0.5 if d > 90 else 0.0
        nota = nota_ref + 3 * 90 - 3 * d - 12 * (perdas_extra - ganho)
        pontos.append({"demanda_kw": d, "entrada": "a4_150", "nota": round(nota, 2)})
    pontos.append({"demanda_kw": None, "entrada": "b3_75", "nota": round(base_b3, 2)})
    return pontos


def _semanas(nota: float, obra: float, semente: int) -> list:
    """Nota de cada semana: a obra entra inteira em todas (regulamento 8.1), o resto se divide."""
    rng = random.Random(semente)
    obra_pts = obra * -PESOS_REAIS["infraestrutura"]
    operacao = nota + obra_pts
    return [round((operacao / 4) * rng.uniform(0.94, 1.06) - obra_pts, 2) for _ in range(4)]


def _escrever(caminho: Path, obj) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def _escrever_jsonl(caminho: Path, linhas: list) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text("".join(json.dumps(ln, ensure_ascii=False) + "\n" for ln in linhas), encoding="utf-8")


def gerar(raiz: Path) -> None:
    """Escreve em `raiz` um conjunto de exemplo em todos os formatos de `resultados/` (spec 3.2)."""
    raiz = Path(raiz)
    juiz_a, sim_a, m_a = _candidato_a()
    juiz_b, sim_b, m_b = _candidato_b()
    h_a, h_b = hash_sub(SUB_A), hash_sub(SUB_B)
    h_outras = [hash_sub(s) for s in OUTRAS]

    for h, j, s in ((h_a, juiz_a, sim_a), (h_b, juiz_b, sim_b)):
        _escrever(raiz / "juiz" / AGENCIA / f"{h}.json", j)
        _escrever(raiz / "sim" / AGENCIA / f"{h}.json", s)

    ledger = [
        {"t": "2026-10-21T09:12:08", "rota": "teste:completo", "agencia": AGENCIA, "hash": h_b, "taxa": 0,
         "saldo": 1000, "autor": "ana"},
        {"t": "2026-10-21T09:48:31", "rota": "teste:completo", "agencia": AGENCIA, "hash": h_a, "taxa": 0,
         "saldo": 1000, "autor": "ana"},
        {"t": "2026-10-21T10:30:02", "rota": "teste:placar", "agencia": AGENCIA, "hash": h_outras[0], "taxa": 20,
         "saldo": 980, "autor": "caio"},
        {"t": "2026-10-21T11:05:44", "rota": "final", "agencia": AGENCIA, "hash": h_b, "taxa": 0, "saldo": 980,
         "autor": "ana"},
        {"t": "2026-10-21T12:20:17", "rota": "final", "agencia": AGENCIA, "hash": h_a, "taxa": 80, "saldo": 900,
         "autor": "ana"},
    ]
    _escrever_jsonl(raiz / "ledger.jsonl", ledger)
    _escrever_jsonl(raiz / "finais.jsonl", [
        {"t": ledger[3]["t"], "agencia": AGENCIA, "n": 1, "hash": h_b, "sub": SUB_B, "taxa": 0, "saldo": 980,
         "aceito": True, "custo_infra": "pendente"},
        {"t": ledger[4]["t"], "agencia": AGENCIA, "n": 2, "hash": h_a, "sub": SUB_A, "taxa": 80, "saldo": 900,
         "aceito": True, "custo_infra": "pendente"},
    ])

    equipes = ((3, "Volts", (310.0, 520.0, 610.0)), (7, "Recarga Inteligente", (0.0, juiz_b["nota"], juiz_a["nota"])),
               (12, "Carga Total", (150.0, 410.0, 470.0)))
    placar = []
    for i, hora in enumerate(("10:00", "11:00", "12:00")):
        lista = sorted(((n, nome, notas[i]) for n, nome, notas in equipes), key=lambda e: -e[2])
        placar.append({
            "fase": "neblina", "etapa": {"n": 3, "rotulo": "Neblina"}, "h0": "2026-10-21T09:00:00",
            "atualizado_em": f"2026-10-21T{hora}:00", "recalculando": False, "agencias": [AGENCIA], "a_liberar": 5,
            "cartas": [],
            "equipes": [{"posicao": p + 1, "numero": n, "nome": nome, "nota": nota, "agencias": {AGENCIA: nota},
                         "finais": 1, "saldo": 900, "nao_atendidos": None, "custo_infra": None}
                        for p, (n, nome, nota) in enumerate(lista)]})
    _escrever_jsonl(raiz / "placar.jsonl", placar)

    _escrever(raiz / "status.json", {
        "equipe": {"numero": 7, "nome": "Recarga Inteligente", "pode_renomear": False}, "fase": "neblina",
        "etapa": {"n": 3, "rotulo": "Neblina"}, "agora": "2026-10-21T12:25:00", "h0": "2026-10-21T09:00:00",
        "saldo": 900,
        "agencias": {AGENCIA: {"aberta": True, "cooldown_teste_ate": None, "cooldown_final_ate": None, "envios": 2,
                               "vigente": {"n": 2}}},
        "cartas": [], "eventos_ativos": []})
    _escrever(raiz / "eventos.json", {"eventos_ativos": []})

    dem = _curva_demanda(juiz_a["nota"], juiz_a["nota"] - 140)
    ranking = []
    for ordem, (h, sub, juiz) in enumerate(((h_a, SUB_A, juiz_a), (h_b, SUB_B, juiz_b))):
        sem = _semanas(juiz["nota"], _obra(sub), ordem)
        ranking.append({"hash": h, "sub": sub, "nota": juiz["nota"], "semanas": sem, "pior_semana": min(sem),
                        "media": round(sum(sem) / 4, 2)})
    for i, (h, sub) in enumerate(zip(h_outras, OUTRAS)):
        nota = juiz_a["nota"] - 90 * (i + 1) - 40
        sem = _semanas(nota, _obra(sub), 10 + i)
        ranking.append({"hash": h, "sub": sub, "nota": round(nota, 2), "semanas": sem, "pior_semana": min(sem),
                        "media": round(sum(sem) / 4, 2)})
    ranking.sort(key=lambda c: (-c["pior_semana"], c["hash"]))
    _escrever(raiz / "otimizador" / AGENCIA / "ranking.json", ranking)
    _escrever(raiz / "otimizador" / AGENCIA / "demanda.json", dem)

    _escrever(raiz / "pesos" / "estimativa.json", {
        "pesos": {"certo": 9.6, "upgrade": 6.3, "nao_atendido": 11.5, "demanda_contratada": 3.1,
                  "energia_ponta_kwh": 0.26},
        "custos": {"carregadores": {"ac_7": 4.2, "ac_11": 6.1, "ac_22x2": 13.6, "dc_30": 15.4, "dc_60x2": 37.1,
                                    "dc_120x2": 71.0},
                   "entradas": {"b3_75": 12.9, "a4_150": 27.4, "a4_225": 41.0}},
        "residuo_rms": 4.8, "n_testes": 17})


if __name__ == "__main__":
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("resultados_exemplo")
    gerar(destino)
    print(f"Exemplo gravado em {destino}")
