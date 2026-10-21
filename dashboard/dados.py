"""Leitura do contrato de dados `resultados/` (spec 3.2). Só lê; nunca chama a API.

Toda função recebe `raiz` (padrão: variável `RESULTADOS_DIR` ou `recarga.RESULTADOS`).
Arquivo ausente ou corrompido devolve lista/dict vazio, nunca exceção: o dashboard sobe mesmo no
início do dia, quando quase nada existe ainda.
"""
import contextlib
import io
import json
import math
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
    """Snapshots de `GET /placar`. O `operacao.py` grava `{t, agora, placar: {...}}`; devolve o conteúdo de
    `placar` com o `t` da linha (aceita também linhas já planas)."""
    saida = []
    for ln in _jsonl(_raiz(raiz) / "placar.jsonl"):
        interno = ln.get("placar") if isinstance(ln.get("placar"), dict) else ln
        saida.append({**interno, "t": ln.get("t")})
    return saida


def finais(raiz=None) -> list:
    return _jsonl(_raiz(raiz) / "finais.jsonl")


def status(raiz=None) -> dict:
    s = _json(_raiz(raiz) / "status.json", {})
    return s if isinstance(s, dict) else {}


DETALHES = ("placar", "completo")


def respostas_juiz(raiz, ag: str) -> dict:
    """{hash: resposta do juiz}. O `juiz.py` grava `juiz/{ag}/{hash}_{detalhe}.json`; por hash junta os detalhes,
    com o `completo` (traz `series`) sobrepondo o `placar`. Arquivos sem sufixo também são aceitos."""
    pasta = _raiz(raiz) / "juiz" / ag
    por_hash: dict = {}
    try:
        arquivos = sorted(pasta.glob("*.json"))
    except OSError:
        return {}
    for p in arquivos:
        conteudo = _json(p, None)
        if not isinstance(conteudo, dict):
            continue
        h, _, det = p.stem.rpartition("_")
        if det not in DETALHES:
            h, det = p.stem, "completo" if "series" in conteudo else "placar"
        por_hash.setdefault(h, {})[det] = conteudo
    return {h: {**d.get("placar", {}), **d.get("completo", {})} for h, d in por_hash.items()}


def simulacao(raiz, ag: str, h: str):
    """Saída do nosso motor (`sim/{ag}/{hash}.json`) de uma submissão, ou None. Lê um arquivo só."""
    r = _json(_raiz(raiz) / "sim" / ag / f"{h}.json", None)
    return r if isinstance(r, dict) else None


def simulacoes(raiz, ag: str) -> dict:
    """{hash: saída do nosso motor} de todo `sim/{ag}/`. Pode ser enorme depois da otimização: prefira `simulacao`."""
    return _dir_json(_raiz(raiz) / "sim" / ag)


def _finito(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _lexicografico(linhas: list) -> bool:
    """O otimizador grava `valor` como lista quando o objetivo é lexicográfico (antes dos pesos estimados)."""
    return any(isinstance(ln.get("valor"), (list, tuple)) for ln in linhas)


def ranking(raiz, ag: str) -> list:
    """Candidatos do otimizador (formato de `otimizador.py`: `hash`, `sub`, `valor`, `valor_semanas`, `metricas`,
    `semanas`, `envio`), com `nota` (valor escalar), `pior_semana` e `medida` ('nota' ou 'atendimento') acrescentados.
    `valor` lexicográfico vira o atendimento (%); sem valor finito, `nota` fica None."""
    linhas = _lista(_json(_raiz(raiz) / "otimizador" / ag / "ranking.json", []), "candidatos", "ranking", "top")
    lex = _lexicografico(linhas)
    saida = []
    for ln in linhas:
        d = dict(ln)
        atend = (ln.get("metricas") or {}).get("atendimento_pct")
        if "nota" not in d:
            v = atend if lex else ln.get("valor")
            d["nota"] = v if _finito(v) else None
        if "pior_semana" not in d:
            vs = [(v[0] if isinstance(v, (list, tuple)) and v else v) for v in ln.get("valor_semanas") or []]
            vs = [v for v in vs if _finito(v)]
            if not vs:
                vs = [m.get("atendimento_pct") for m in ln.get("semanas") or [] if _finito(m.get("atendimento_pct"))]
            d["pior_semana"] = min(vs) if vs else None
        d["medida"] = "atendimento" if lex else "nota"
        saida.append(d)
    return saida


def demanda(raiz, ag: str) -> list:
    """Varredura de demanda do otimizador (`demanda`, `entrada`, `valor`, `hash`, `atendimento_pct`), com
    `demanda_kw`, `nota` e `medida` acrescentados. `demanda_kw` None é a alternativa B3. `valor` lista ou infinito
    (objetivo lexicográfico) usa o atendimento (%) no lugar da nota."""
    linhas = _lista(_json(_raiz(raiz) / "otimizador" / ag / "demanda.json", []), "pontos", "curva", "demanda")
    lex = _lexicografico(linhas)
    saida = []
    for ln in linhas:
        d = dict(ln)
        if "demanda_kw" not in d:
            d["demanda_kw"] = ln.get("demanda")
        if "nota" not in d:
            v = ln.get("atendimento_pct") if lex else ln.get("valor")
            d["nota"] = v if _finito(v) else None
        d["medida"] = "atendimento" if lex else "nota"
        saida.append(d)
    return saida


def pesos(raiz=None) -> dict:
    """`pesos/estimativa.json` como o `recarga.pesos.salvar` grava: `pesos: {w, k_carregador, k_entrada}` (com
    sinal), `residuo_rms`, `n`, `confiavel`, `nao_identificados`."""
    p = _json(_raiz(raiz) / "pesos" / "estimativa.json", {})
    return p if isinstance(p, dict) else {}


def eventos(raiz=None) -> list:
    """`eventos_ativos` de `GET /status`, como o `operacao.py` grava em `eventos.json`: [{agencia, params}]."""
    return _lista(_json(_raiz(raiz) / "eventos.json", []), "eventos_ativos", "eventos")


def eventos_da_agencia(raiz, ag: str) -> list:
    """Params dos eventos ativos da agência, no formato que `recarga.lote.avaliar(eventos=...)` espera."""
    return [list(e["params"]) for e in eventos(raiz) if e.get("agencia") == ag and isinstance(e.get("params"), list)]


def para_envio(sub: dict) -> dict:
    """Submissão normalizada sem `demanda_contratada_kw: null` (o validador rejeita a chave em B3)."""
    if not isinstance(sub, dict):
        return sub
    return {k: v for k, v in sub.items() if not (k == "demanda_contratada_kw" and v is None)}


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


def obra_estimada(estimativa: dict, sub: dict, entrada_existente: str | None = None):
    """Custo de obra em pontos de nota (negativo): Σ qtd × k_carregador + k_entrada, com os `k` de
    `pesos/estimativa.json` (a entrada existente custa 0). None se faltar algum `k` usado."""
    p = estimativa.get("pesos") or {}
    kc, ke = p.get("k_carregador") or {}, p.get("k_entrada") or {}
    nao = set(estimativa.get("nao_identificados") or [])
    total = 0.0
    for k, n in (sub.get("carregadores") or {}).items():
        if not n:
            continue
        if k not in kc or f"car:{k}" in nao:
            return None
        total += n * kc[k]
    e = sub.get("entrada")
    if e != entrada_existente:
        if e not in ke or f"ent:{e}" in nao:
            return None
        total += ke[e]
    return total


def pontuar_estimado(metricas: dict, estimativa: dict, sub: dict, entrada_existente: str | None = None):
    """Pontos no formato do juiz com os pesos estimados na Neblina (`pesos.w` e `k_*`, todos com sinal).

    Item sem peso estimado só passa se a quantidade for 0. Devolve None se faltar métrica, peso ou custo usado.
    """
    w = (estimativa.get("pesos") or {}).get("w") or {}
    if not metricas or not w:
        return None
    itens = []
    for item in ("certo", "upgrade", "nao_atendido", "demanda_contratada", "energia_ponta_kwh"):
        chave = METRICA_DO_ITEM[item]
        if chave not in metricas and item != "demanda_contratada":
            return None
        qtd = metricas.get(chave) or 0
        peso = w.get(item)
        if not _finito(peso):
            if qtd:
                return None
            peso = 0.0
        itens.append([item, qtd, peso, qtd * peso])
    obra = obra_estimada(estimativa, sub, entrada_existente)
    if obra is None:
        return None
    itens.append(["infraestrutura", 1, obra, obra])
    return {"itens": itens, "nota": sum(i[3] for i in itens)}


def pontuar_exato(metricas: dict, sub: dict, cen_catalogo, catalogo: dict, ag: str):
    """Pontos exatos pós-H4 (`kickoff.nota.custo_infra` + `kickoff.nota.pontuar`). `cen_catalogo` é o cenário
    carregado com o catálogo (custos preenchidos). Devolve {itens, nota, custo_infra: {...}} ou None."""
    from kickoff import nota, validar
    try:
        norm = validar.normalizar(para_envio(sub), cen_catalogo)
        custo = nota.custo_infra(norm, cen_catalogo)
        if custo is None:
            return None
        pontos = nota.pontuar({**metricas, "custo_infra": custo["total"]}, catalogo["pesos"][ag])
    except (KeyError, TypeError, ValueError):
        return None
    return {**pontos, "custo_infra": custo}


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
    atend = bool(com or sem) and (com or sem)[0].get("medida") == "atendimento"
    nome_v, un = ("atendimento", " %") if atend else ("nota", "")
    atual = next((d for d in com if d["demanda_kw"] == dem), None)
    ref = atual["nota"] if atual else nota
    if com and atual:
        melhor = max(com, key=lambda d: d["nota"])
        faixa = f"{fmt(min(d['demanda_kw'] for d in com), 0)} a {fmt(max(d['demanda_kw'] for d in com), 0)} kW"
        base = f"Na varredura de {len(com)} valores ({faixa}), {fmt(dem, 0)} kW dá {nome_v} {fmt(atual['nota'], 1)}{un}"
        if melhor["demanda_kw"] == dem or melhor["nota"] <= atual["nota"]:
            partes.append(base + ", o máximo da curva: menos demanda perde clientes e mais demanda custa por kW.")
        else:
            partes.append(base + f"; o máximo da curva é {fmt(melhor['demanda_kw'], 0)} kW "
                          f"({nome_v} {fmt(melhor['nota'], 1)}{un}, diferença de {fmt(melhor['nota'] - atual['nota'], 1)} "
                          f"{'p.p.' if atend else 'pontos'}).")
    if sem and ref is not None:
        alt = max(sem, key=lambda d: d["nota"])
        dif = ref - alt["nota"]
        nome = (alt.get("entrada") or "B3").upper().replace("_", " ")
        partes.append(f"A alternativa sem demanda ({nome}) chega a {fmt(alt['nota'], 1)}{un}, "
                      f"{fmt(abs(dif), 1)} {'p.p.' if atend else 'pontos'} {'abaixo' if dif >= 0 else 'acima'} da escolha.")
    return " ".join(partes)
