"""Leitura do contrato de dados `resultados/` (spec 3.2). Só lê; nunca chama a API.

Toda função recebe `raiz` (padrão: variável `RESULTADOS_DIR` ou `recarga.RESULTADOS`).
Arquivo ausente ou corrompido devolve lista/dict vazio, nunca exceção: o dashboard sobe mesmo no
início do dia, quando quase nada existe ainda.
"""
import contextlib
import io
import json
import os
from datetime import datetime
from pathlib import Path

from recarga import RESULTADOS

# Itens da pontuação (regulamento 12.3), na ordem de `kickoff.nota.ITENS`, com o nome na tela.
ITENS = (
    ("certo", "Certos"),
    ("upgrade", "Upgrades"),
    ("nao_atendido", "Não atendidos"),
    ("demanda_contratada", "Demanda contratada"),
    ("energia_ponta_kwh", "Energia na ponta"),
    ("infraestrutura", "Obra (infraestrutura)"),
)
ROTULOS = dict(ITENS)
# Chave da métrica correspondente a cada item (`kickoff.nota.ITENS`).
METRICA_DO_ITEM = {
    "certo": "certos",
    "upgrade": "upgrades",
    "nao_atendido": "nao_atendidos",
    "demanda_contratada": "demanda_contratada_kw",
    "energia_ponta_kwh": "energia_ponta_kwh",
    "infraestrutura": "custo_infra",
}
ROTULOS_METRICA = {
    "contratos": "Contratos",
    "atendimento_pct": "Atendimento (%)",
    "pico_kw": "Pico de 15 min (kW)",
    "energia_kwh": "Energia total (kWh)",
    "certos": "Atendidos na categoria certa",
    "upgrades": "Atendidos com upgrade",
    "nao_atendidos": "Não atendidos",
    "energia_ponta_kwh": "Energia na ponta (kWh)",
    "demanda_contratada_kw": "Demanda contratada (kW)",
    "custo_infra": "Custo de obra (pontos)",
}
# Nomes a..e usados na spec 5.1 para os cinco pesos de operação.
ALIAS_PESOS = {"a": "certo", "b": "upgrade", "c": "nao_atendido", "d": "demanda_contratada",
               "e": "energia_ponta_kwh"}


def raiz_padrao() -> Path:
    return Path(os.environ.get("RESULTADOS_DIR", RESULTADOS))


def _raiz(raiz) -> Path:
    return Path(raiz) if raiz is not None else raiz_padrao()


def _json(caminho: Path, padrao):
    try:
        return json.loads(caminho.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return padrao


def _jsonl(caminho: Path) -> list:
    try:
        linhas = caminho.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return []
    saida = []
    for ln in linhas:
        ln = ln.strip()
        if not ln:
            continue
        try:
            obj = json.loads(ln)
        except ValueError:
            continue
        if isinstance(obj, dict):
            saida.append(obj)
    return saida


def _dir_json(pasta: Path) -> dict:
    """{nome do arquivo sem extensão: conteúdo} de todos os .json válidos da pasta."""
    saida = {}
    try:
        arquivos = sorted(pasta.glob("*.json"))
    except OSError:
        return {}
    for p in arquivos:
        conteudo = _json(p, None)
        if isinstance(conteudo, dict):
            saida[p.stem] = conteudo
    return saida


def _lista(conteudo, *chaves) -> list:
    """Aceita lista pura ou objeto com a lista sob uma das `chaves`."""
    if isinstance(conteudo, list):
        return [x for x in conteudo if isinstance(x, dict)]
    if isinstance(conteudo, dict):
        for k in chaves:
            if isinstance(conteudo.get(k), list):
                return [x for x in conteudo[k] if isinstance(x, dict)]
    return []


# --- leitura direta dos arquivos -------------------------------------------------------------

def ledger(raiz=None) -> list:
    return _jsonl(_raiz(raiz) / "ledger.jsonl")


def gasto_por_agencia(raiz=None) -> dict:
    """m7Coins cobrados por agência (soma de `taxa` no ledger)."""
    gasto: dict = {}
    for ln in ledger(raiz):
        taxa = ln.get("taxa")
        if isinstance(taxa, bool) or not isinstance(taxa, (int, float)):
            continue
        ag = ln.get("agencia") or "-"
        gasto[ag] = gasto.get(ag, 0) + taxa
    return gasto


def placar(raiz=None) -> list:
    return _jsonl(_raiz(raiz) / "placar.jsonl")


def finais(raiz=None) -> list:
    return _jsonl(_raiz(raiz) / "finais.jsonl")


def status(raiz=None) -> dict:
    s = _json(_raiz(raiz) / "status.json", {})
    return s if isinstance(s, dict) else {}


def respostas_juiz(raiz, ag: str) -> dict:
    """{hash: resposta do juiz} de `juiz/{ag}/`."""
    return _dir_json(_raiz(raiz) / "juiz" / ag)


def simulacoes(raiz, ag: str) -> dict:
    """{hash: saída do nosso motor} de `sim/{ag}/`."""
    return _dir_json(_raiz(raiz) / "sim" / ag)


def ranking(raiz, ag: str) -> list:
    return _lista(_json(_raiz(raiz) / "otimizador" / ag / "ranking.json", []), "candidatos", "ranking", "top")


def demanda(raiz, ag: str) -> list:
    return _lista(_json(_raiz(raiz) / "otimizador" / ag / "demanda.json", []), "pontos", "curva", "demanda")


def pesos(raiz=None) -> dict:
    p = _json(_raiz(raiz) / "pesos" / "estimativa.json", {})
    return p if isinstance(p, dict) else {}


def eventos(raiz=None) -> list:
    return _lista(_json(_raiz(raiz) / "eventos.json", []), "eventos_ativos", "eventos")


# --- derivados -------------------------------------------------------------------------------

def vigentes(lista_finais: list) -> dict:
    """{agência: último envio final aceito}. O arquivo é cronológico."""
    saida = {}
    for f in lista_finais:
        if f.get("agencia"):
            saida[f["agencia"]] = f
    return saida


def agencias_conhecidas(raiz=None) -> list:
    """Agências com algum dado em `resultados/`, em ordem alfabética."""
    r = _raiz(raiz)
    nomes = set(vigentes(finais(r)))
    nomes.update(ln["agencia"] for ln in ledger(r) if ln.get("agencia"))
    for sub in ("juiz", "sim", "otimizador"):
        try:
            nomes.update(p.name for p in (r / sub).iterdir() if p.is_dir())
        except OSError:
            pass
    return sorted(nomes)


def normalizar_series(series) -> dict:
    """O juiz devolve as séries planas; `simular.avaliar` as devolve sob `publico`."""
    if not isinstance(series, dict):
        return {}
    if "potencia_kw" not in series and isinstance(series.get("publico"), dict):
        return series["publico"]
    return series


def hora(entrada: dict):
    """Instante de uma linha do ledger/placar como `datetime`, ou None se não houver/for ilegível."""
    for k in ("t", "horario", "hora", "ts", "timestamp", "atualizado_em", "registrado_em"):
        v = entrada.get(k)
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v.replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                continue
    return None


def rotulo_submissao(sub: dict) -> str:
    """Resumo curto de uma submissão para seletores. Ex.: `2× dc_60x2 + 1× ac_22x2 · b3_75 · próx. retirada`."""
    car = " + ".join(f"{n}× {k}" for k, n in sorted((sub.get("carregadores") or {}).items()) if n)
    ent = sub.get("entrada", "?")
    if sub.get("demanda_contratada_kw") is not None:
        ent += f" ({sub['demanda_contratada_kw']:g} kW)"
    pol = sub.get("politica") or {}
    nomes = {"menor_soc": "menor SOC", "chegada": "chegada", "proxima_retirada": "próx. retirada"}
    partes = [car or "sem carregadores", ent, nomes.get(pol.get("prioridade", "menor_soc"), "")]
    if pol.get("evitar_ponta"):
        partes.append("evita ponta")
    return " · ".join(p for p in partes if p)


def obra_estimada(estimativa: dict, sub: dict, entrada_existente: str | None = None) -> float:
    """Custo de obra em pontos de nota: Σ qtd × k_carregador + k_entrada (a entrada existente custa 0)."""
    custos = estimativa.get("custos") or {}
    ck, ce = custos.get("carregadores") or {}, custos.get("entradas") or {}
    obra = sum(n * ck.get(k, 0) for k, n in (sub.get("carregadores") or {}).items())
    if sub.get("entrada") != entrada_existente:
        obra += ce.get(sub.get("entrada"), 0)
    return obra


def pontuar_estimado(metricas: dict, estimativa: dict, sub: dict, entrada_existente: str | None = None):
    """Pontos no formato do juiz usando os pesos estimados (`pesos/estimativa.json`).

    `estimativa`: {"pesos": {certo, upgrade, nao_atendido, demanda_contratada, energia_ponta_kwh}
    (ou a..e), "custos": {"carregadores": {id: k}, "entradas": {id: k}}}. Os pesos são magnitudes; o sinal vem
    do tipo do item (os três últimos descontam). Devolve None se faltar peso ou métrica.
    """
    p = {ALIAS_PESOS.get(k, k): v for k, v in (estimativa.get("pesos") or {}).items()}
    sinais = {"certo": 1, "upgrade": 1, "nao_atendido": -1, "demanda_contratada": -1, "energia_ponta_kwh": -1}
    if not metricas or any(not isinstance(p.get(i), (int, float)) for i in sinais):
        return None
    if any(METRICA_DO_ITEM[i] not in metricas for i in sinais if i != "demanda_contratada"):
        return None
    itens = []
    for item, sinal in sinais.items():
        qtd = metricas.get(METRICA_DO_ITEM[item]) or 0
        peso = sinal * abs(p[item])
        itens.append([item, qtd, peso, qtd * peso])
    obra = obra_estimada(estimativa, sub, entrada_existente)
    itens.append(["infraestrutura", 1, -obra, -obra])
    return {"itens": itens, "nota": sum(i[3] for i in itens)}


# --- apresentação ----------------------------------------------------------------------------

def fmt(x, casas: int = 1, sinal: bool = False) -> str:
    """Número no formato brasileiro (1.234,5); '—' quando não é número."""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return "—"
    if round(x, casas) == 0:
        x = 0.0  # sem "-0" nem "+0"
        sinal = False
    s = f"{x:{'+' if sinal else ''},.{casas}f}"
    return s.replace(",", "#").replace(".", ",").replace("#", ".")


def total_obra(v):
    """Custo de obra em pontos: número, ou o `total` de {'carregadores', 'entrada', 'total'}; senão None."""
    if isinstance(v, dict):
        v = v.get("total")
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def fidelidade(meu_metricas: dict, juiz_metricas: dict, meu_series: dict, juiz_series: dict) -> dict:
    """Compara o nosso motor com o juiz reaproveitando `kit_kickoff/comparar.py` (a saída impressa é capturada).

    Devolve {"linhas": [{chave, metrica, meu, juiz, dif, ok}], "divergencias": [...], "series": texto, "ok": bool,
    "disponivel": bool}. As divergências usam os mesmos nomes do `comparar.py` (ex.: `pico_kw`,
    `series.potencia_kw@Seg 18/10 09:15`).
    """
    try:
        import comparar
    except ImportError:
        return {"linhas": [], "divergencias": [], "series": "", "ok": True, "disponivel": False}
    diverge: list = []
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        comparar.comparar_metricas(meu_metricas or {}, juiz_metricas or {}, diverge)
    linhas = []
    for ln in buf.getvalue().splitlines()[1:]:  # a primeira linha é o cabeçalho
        t = ln.split()
        if len(t) < 4:
            continue
        linhas.append({"chave": t[0], "metrica": ROTULOS_METRICA.get(t[0], t[0]), "meu": float(t[1]),
                       "juiz": float(t[2]), "dif": float(t[3]), "ok": "<--" not in t})
    texto_series = ""
    if meu_series and juiz_series:
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                comparar.comparar_series(meu_series, juiz_series, diverge)
            texto_series = buf.getvalue().strip()
        except (KeyError, TypeError):
            texto_series = "séries incompletas: não foi possível comparar"
    return {"linhas": linhas, "divergencias": diverge, "series": texto_series, "ok": not diverge,
            "disponivel": True}


def justificativa(sub: dict | None, curva: list, nota: float | None = None) -> str:
    """Texto curto (Markdown) que justifica a entrada e a demanda contratada, a partir da varredura nota × demanda."""
    if not sub or not sub.get("entrada"):
        return ""
    ent, dem = sub["entrada"], sub.get("demanda_contratada_kw")
    if dem is None:
        partes = [f"Entrada **{ent}** em baixa tensão, sem demanda contratada."]
    else:
        partes = [f"Entrada **{ent}** com demanda contratada de **{fmt(dem, 0)} kW**."]
    com = [d for d in curva or [] if isinstance(d.get("demanda_kw"), (int, float)) and isinstance(d.get("nota"), (int, float))]
    sem = [d for d in curva or [] if d.get("demanda_kw") is None and isinstance(d.get("nota"), (int, float))]
    atual = next((d for d in com if d["demanda_kw"] == dem), None)
    ref = atual["nota"] if atual else nota
    if com and atual:
        melhor = max(com, key=lambda d: d["nota"])
        faixa = f"{fmt(min(d['demanda_kw'] for d in com), 0)} a {fmt(max(d['demanda_kw'] for d in com), 0)} kW"
        base = f"Na varredura de {len(com)} valores ({faixa}), {fmt(dem, 0)} kW dá nota {fmt(atual['nota'], 1)}"
        if melhor["demanda_kw"] == dem or melhor["nota"] <= atual["nota"]:
            partes.append(base + ", o máximo da curva: menos demanda perde clientes e mais demanda custa por kW.")
        else:
            partes.append(base + f"; o máximo da curva é {fmt(melhor['demanda_kw'], 0)} kW "
                          f"(nota {fmt(melhor['nota'], 1)}, diferença de {fmt(melhor['nota'] - atual['nota'], 1)} pontos).")
    if sem and ref is not None:
        alt = max(sem, key=lambda d: d["nota"])
        dif = ref - alt["nota"]
        nome = (alt.get("entrada") or "B3").upper().replace("_", " ")
        partes.append(f"A alternativa sem demanda ({nome}) chega a {fmt(alt['nota'], 1)}, "
                      f"{fmt(abs(dif), 1)} pontos {'abaixo' if dif >= 0 else 'acima'} da escolha.")
    return " ".join(partes)
