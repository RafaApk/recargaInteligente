"""Dados de exemplo de `resultados/` (spec 3.2) para desenvolver e testar o dashboard sem a API.

  python -m dashboard.exemplo PASTA      # grava os arquivos de exemplo em PASTA
  RESULTADOS_DIR=PASTA streamlit run dashboard/app.py

Os arquivos seguem os formatos reais dos escritores: `recarga.juiz` (`juiz/{ag}/{hash}_{detalhe}.json`,
`ledger.jsonl`, `finais.jsonl` com `sub`), `recarga.operacao` (`placar.jsonl` embrulhado, `eventos.json`),
`recarga.lote` (`sim/{ag}/{hash}.json`), `recarga.otimizador` (`ranking.json`, `demanda.json` com `demanda`/`valor`) e
`recarga.pesos` (`pesos/estimativa.json` com `pesos.w`, `k_carregador`, `k_entrada`). O `contrato` é conferido em
`testes/test_contrato.py` com os escritores de verdade. As respostas do juiz seguem o regulamento 12.3. As séries são sintéticas, mas coerentes
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

from . import dados

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


ESTIMATIVA = {
    "pesos": {
        "w": {"certo": 9.6, "upgrade": 6.3, "nao_atendido": -11.5, "demanda_contratada": -3.1,
              "energia_ponta_kwh": -0.26},
        "k_carregador": {"ac_7": -4.2, "dc_30": -15.4, "ac_22x2": -13.6, "dc_60x2": -37.1, "ac_11": -6.1},
        "k_entrada": {"b3_75": -12.9, "a4_150": -27.4},
    },
    "residuo_rms": 4.8, "n": 17, "confiavel": True, "nao_identificados": ["car:dc_120x2", "ent:a4_225"],
}
VERSAO_MOTOR = "exemplo0000000000"


def _metricas_semanas(m: dict, semente: int) -> list:
    """`semanas` de `recarga.lote`: métricas físicas de cada uma das 4 semanas públicas."""
    rng = random.Random(semente)
    saida = []
    for _ in range(4):
        f = 0.25 * rng.uniform(0.94, 1.06)
        certos, upgrades, nao = round(m["certos"] * f), round(m["upgrades"] * f), round(m["nao_atendidos"] * f)
        contratos = certos + upgrades + nao
        saida.append({"contratos": contratos, "certos": certos, "upgrades": upgrades, "nao_atendidos": nao,
                      "pico_kw": m["pico_kw"] * rng.uniform(0.93, 1.0), "energia_kwh": m["energia_kwh"] * f,
                      "energia_ponta_kwh": m["energia_ponta_kwh"] * f,
                      "atendimento_pct": 100.0 * (certos + upgrades) / contratos,
                      "demanda_contratada_kw": m["demanda_contratada_kw"]})
    return saida


def _fisicas_lote(m: dict) -> dict:
    """Métricas como o `lote` grava: sem `custo_infra` (o motor só conhece o custo com o catálogo)."""
    return {k: v for k, v in m.items() if k != "custo_infra"}


def _resultado_lote(sub: dict, m: dict, semente: int, series: dict | None = None) -> dict:
    """Arquivo `sim/{ag}/{hash}.json` de `recarga.lote`."""
    r = {"agencia": AGENCIA, "hash": hash_sub(sub), "sub": sub, "eventos": [], "valido": True, "erros": [],
         "violacoes": [], "metricas": _fisicas_lote(m), "semanas": _metricas_semanas(m, semente),
         "versao_motor": VERSAO_MOTOR}
    if series is not None:
        r["series"] = series
    return r


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
    meu = {**m, "energia_kwh": m["energia_kwh"] * 1.002}  # dentro da tolerância de 1% da energia
    return juiz, _resultado_lote(SUB_A, meu, 1, s), m


def _candidato_b() -> tuple:
    """Resposta do juiz (fase Neblina: sem `pontos`) e saída do nosso motor, com uma divergência."""
    contratos, nao, ret = 271, 66, 205
    s = _series(23, 40.5, 3, 6, 15.0, 1.25, False, nao, ret)
    fis = _fisicas(s, contratos)
    certos, upgrades = 190, ret - 190
    m = {**fis, "certos": certos, "upgrades": upgrades, "nao_atendidos": nao, "demanda_contratada_kw": 0.0,
         "custo_infra": _obra(SUB_B)}
    juiz = {"agencia": AGENCIA, "periodo": "publico", "valido": True, "erros": [], "violacoes": [],
            "nota": _pontos(m)["nota"],
            "metricas": {k: m[k] for k in ("contratos", "atendimento_pct", "pico_kw", "energia_kwh")},
            "taxa": 0, "saldo": 1000, "repetido": False, "series": s}
    s_meu = {**s, "potencia_kw": list(s["potencia_kw"])}
    s_meu["potencia_kw"][1500] += 0.8  # divergência pontual, para exercitar a tabela de fidelidade
    return juiz, _resultado_lote(SUB_B, {**m, "pico_kw": m["pico_kw"] + 0.03}, 2, s_meu), m


def _curva_demanda(nota_ref: float, base_b3: float) -> list:
    """`demanda.json` de `recarga.otimizador`: [{demanda, entrada, valor, hash, atendimento_pct}]."""
    linhas = []
    for d in range(30, 140, 10):
        perdas_extra = max(0.0, (90 - d) / 10) ** 1.8 * 3.5
        ganho = 0.5 if d > 90 else 0.0
        nota = nota_ref + 3 * 90 - 3 * d - 12 * (perdas_extra - ganho)
        sub = {**SUB_A, "demanda_contratada_kw": d}
        linhas.append({"demanda": d, "entrada": "a4_150", "valor": round(nota, 2), "hash": hash_sub(sub),
                       "atendimento_pct": round(95.2 - 1.2 * max(0.0, (90 - d) / 10) ** 1.8 + ganho, 2)})
    sub = {**SUB_A, "entrada": "b3_75", "demanda_contratada_kw": None}
    linhas.append({"demanda": None, "entrada": "b3_75", "valor": round(base_b3, 2), "hash": hash_sub(sub),
                   "atendimento_pct": 91.4})
    return linhas


def _escrever(caminho: Path, obj) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def _escrever_jsonl(caminho: Path, linhas: list) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text("".join(json.dumps(ln, ensure_ascii=False) + "\n" for ln in linhas), encoding="utf-8")


def _candidata(sub: dict, nota_ref: float, deslocamento: float, semente: int) -> dict:
    """Linha de `ranking.json`: resultado do lote + `valor`, `valor_semanas` e `envio` (nota estimada)."""
    rng = random.Random(semente)
    n = 271
    nao = round(13 + deslocamento / 12)
    m = {"contratos": n, "certos": n - nao - 20, "upgrades": 20, "nao_atendidos": nao,
         "atendimento_pct": 100.0 * (n - nao) / n, "pico_kw": rng.uniform(60, 90), "energia_kwh": 21700.0,
         "energia_ponta_kwh": 190.0 + 40 * semente, "demanda_contratada_kw": float(sub["demanda_contratada_kw"] or 0)}
    r = _resultado_lote(sub, m, semente)
    existente = "b3_45"
    est = dados.pontuar_estimado(m, ESTIMATIVA, sub, existente)
    semanas = [dados.pontuar_estimado(sm, ESTIMATIVA, sub, existente)["nota"] for sm in r["semanas"]]
    envio = {k: v for k, v in sub.items() if not (k == "demanda_contratada_kw" and v is None)}
    return {**r, "valor": est["nota"], "valor_semanas": semanas, "envio": envio}


def gerar(raiz: Path) -> None:
    """Escreve em `raiz` um conjunto de exemplo em todos os formatos de `resultados/` (spec 3.2)."""
    raiz = Path(raiz)
    juiz_a, sim_a, m_a = _candidato_a()
    juiz_b, sim_b, m_b = _candidato_b()
    h_a, h_b = hash_sub(SUB_A), hash_sub(SUB_B)
    h_outras = [hash_sub(s) for s in OUTRAS]

    # juiz.py: `{hash}_{detalhe}.json`. A só tem o teste completo; B tem placar e completo (o completo prevalece).
    _escrever(raiz / "juiz" / AGENCIA / f"{h_a}_completo.json", juiz_a)
    _escrever(raiz / "juiz" / AGENCIA / f"{h_b}_completo.json", juiz_b)
    _escrever(raiz / "juiz" / AGENCIA / f"{h_b}_placar.json",
              {k: v for k, v in juiz_b.items() if k != "series"})
    for h, r in ((h_a, sim_a), (h_b, sim_b)):
        _escrever(raiz / "sim" / AGENCIA / f"{h}.json", r)

    # ledger.jsonl: só chamadas com taxa cobrada
    ledger = [
        {"t": "2026-10-21T09:12:08Z", "rota": "teste", "agencia": AGENCIA, "hash": h_b, "taxa": 20, "saldo": 980,
         "autor": "ana"},
        {"t": "2026-10-21T09:48:31Z", "rota": "teste", "agencia": AGENCIA, "hash": h_a, "taxa": 50, "saldo": 930,
         "autor": "ana"},
        {"t": "2026-10-21T10:30:02Z", "rota": "teste", "agencia": AGENCIA, "hash": h_outras[0], "taxa": 30,
         "saldo": 900, "autor": "caio"},
        {"t": "2026-10-21T11:05:44Z", "rota": "final", "agencia": AGENCIA, "hash": h_b, "taxa": 20, "saldo": 880,
         "autor": "ana"},
        {"t": "2026-10-21T12:20:17Z", "rota": "final", "agencia": AGENCIA, "hash": h_a, "taxa": 80, "saldo": 800,
         "autor": "ana"},
    ]
    _escrever_jsonl(raiz / "ledger.jsonl", ledger)
    _escrever_jsonl(raiz / "finais.jsonl", [
        {"t": ledger[3]["t"], "agencia": AGENCIA, "hash": h_b, "hash_sub": h_b, "sub": SUB_B, "n": 1, "taxa": 20,
         "autor": "ana"},
        {"t": ledger[4]["t"], "agencia": AGENCIA, "hash": h_a, "hash_sub": h_a, "sub": SUB_A, "n": 2, "taxa": 80,
         "autor": "ana"},
    ])

    # operacao.py: `{t, agora, placar: GET /placar}`
    equipes = ((3, "Volts", (310.0, 520.0, 610.0)), (7, "Recarga Inteligente", (0.0, juiz_b["nota"], juiz_a["nota"])),
               (12, "Carga Total", (150.0, 410.0, 470.0)))
    linhas = []
    for i, hora in enumerate(("10:00", "11:00", "12:00")):
        lista = sorted(((n, nome, notas[i]) for n, nome, notas in equipes), key=lambda e: -e[2])
        linhas.append({"t": f"2026-10-21T{hora}:00Z", "agora": 3600.0 * (i + 1), "placar": {
            "fase": "neblina", "etapa": {"n": 3, "rotulo": "Neblina"}, "h0": "2026-10-21T09:00:00Z",
            "atualizado_em": f"2026-10-21T{hora}:00Z", "recalculando": False, "agencias": [AGENCIA], "a_liberar": 5,
            "cartas": [],
            "equipes": [{"posicao": p + 1, "numero": n, "nome": nome, "nota": nota, "agencias": {AGENCIA: nota},
                         "finais": 1, "saldo": 800, "nao_atendidos": None, "custo_infra": None}
                        for p, (n, nome, nota) in enumerate(lista)]}})
    _escrever_jsonl(raiz / "placar.jsonl", linhas)

    _escrever(raiz / "status.json", {
        "equipe": {"numero": 7, "nome": "Recarga Inteligente", "pode_renomear": False}, "fase": "neblina",
        "etapa": {"n": 3, "rotulo": "Neblina"}, "agora": "2026-10-21T12:25:00Z", "h0": "2026-10-21T09:00:00Z",
        "saldo": 800,
        "agencias": {AGENCIA: {"aberta": True, "cooldown_teste_ate": None, "cooldown_final_ate": None, "envios": 2,
                               "vigente": {"n": 2}}},
        "cartas": [], "eventos_ativos": []})
    _escrever(raiz / "eventos.json", [])

    # otimizador.py: ranking (melhor primeiro) e varredura de demanda
    ranking = [
        {**_candidata(SUB_A, juiz_a["nota"], 0, 3), "hash": h_a},
        {**_candidata(OUTRAS[0], juiz_a["nota"], 60, 4)},
        {**_candidata(OUTRAS[1], juiz_a["nota"], 90, 5)},
        {**_candidata(OUTRAS[2], juiz_a["nota"], 150, 6)},
        {**_candidata(SUB_B, juiz_a["nota"], 400, 7), "hash": h_b},
    ]
    ranking.sort(key=lambda r: -r["valor"])
    _escrever(raiz / "otimizador" / AGENCIA / "ranking.json", ranking)
    _escrever(raiz / "otimizador" / AGENCIA / "demanda.json", _curva_demanda(juiz_a["nota"], juiz_a["nota"] - 140))

    # pesos.py: `salvar`
    _escrever(raiz / "pesos" / "estimativa.json", ESTIMATIVA)


if __name__ == "__main__":
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("resultados_exemplo")
    gerar(destino)
    print(f"Exemplo gravado em {destino}")
