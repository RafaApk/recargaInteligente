"""Leitura do contrato de dados `resultados/` (spec 3.2). Só lê; nunca chama a API.

Toda função recebe `raiz` (padrão: variável `RESULTADOS_DIR` ou `recarga.RESULTADOS`).
Arquivo ausente ou corrompido devolve lista/dict vazio, nunca exceção: o dashboard sobe mesmo no
início do dia, quando quase nada existe ainda.
"""
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
    custos = estimativa.get("custos") or {}
    ck, ce = custos.get("carregadores") or {}, custos.get("entradas") or {}
    obra = sum(n * ck.get(k, 0) for k, n in (sub.get("carregadores") or {}).items())
    if sub.get("entrada") != entrada_existente:
        obra += ce.get(sub.get("entrada"), 0)
    itens.append(["infraestrutura", 1, -obra, -obra])
    return {"itens": itens, "nota": sum(i[3] for i in itens)}
