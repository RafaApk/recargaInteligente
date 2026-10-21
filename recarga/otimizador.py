"""Otimizador por agência (spec 5.2): política -> busca local de carregadores -> varredura de demanda.

  python -m recarga.otimizador AG [--modo rapido|completo]

Grava `resultados/otimizador/{ag}/ranking.json` (top 20) e `demanda.json` e imprime a submissão escolhida.
"""
import itertools
import json
import math
import sys
from pathlib import Path

from recarga import RESULTADOS, lote, objetivo, pesos, robustez

from kickoff import validar  # noqa: E402

SAIDA = RESULTADOS / "otimizador"
ESCALA = RESULTADOS / "pesos" / "escala.json"  # {ag: fator} sobre os pesos operacionais estimados (opcional)
TOP_RANKING = 20
MAX_PASSOS = 50
# Saídas por modelo (regulamento 7.1); o catálogo de carregadores é o mesmo em todas as agências.
SAIDAS = {"ac_7": 1, "ac_11": 1, "ac_22x2": 2, "dc_30": 1, "dc_60x2": 2, "dc_120x2": 2}
MODOS = {"rapido": {"politicas": 2, "partidas": 1, "sementes": 3},
         "completo": {"politicas": 3, "partidas": 4, "sementes": 5}}


# ---------------- espaço de busca ----------------

def politicas() -> list:
    """As 12 combinações do menu (prioridade × divisao × evitar_ponta)."""
    return [{"prioridade": p, "evitar_ponta": e, "divisao": d}
            for p, d, e in itertools.product(validar.MENU["prioridade"], validar.MENU["divisao"],
                                             validar.MENU["evitar_ponta"])]


def _limpo(car: dict) -> dict:
    return {k: car[k] for k in sorted(car) if car[k] > 0}


def vizinhos(carregadores: dict, vagas: int, saidas: dict = None) -> list:
    """Adicionar 1, trocar o tipo de 1, remover 1; Σ saídas <= vagas e >= 1 carregador."""
    saidas = saidas or SAIDAS
    base = _limpo(carregadores)
    cand = []
    for k in saidas:
        cand.append({**base, k: base.get(k, 0) + 1})
    for k in base:
        cand.append({**base, k: base[k] - 1})
        for j in saidas:
            if j != k:
                cand.append({**base, k: base[k] - 1, j: base.get(j, 0) + 1})
    out, vistos = [], {json.dumps(base, sort_keys=True)}
    for c in map(_limpo, cand):
        chave = json.dumps(c, sort_keys=True)
        if c and chave not in vistos and sum(saidas[k] * n for k, n in c.items()) <= vagas:
            vistos.add(chave)
            out.append(c)
    return out


def entrada_para(demanda_kw, existente: str, cen):
    """Entrada A4/SE mais barata (ordem de kVA) que comporta a demanda e não fica abaixo da existente.

    `demanda_kw` None -> a existente. Nenhuma comporta -> None.
    """
    if demanda_kw is None:
        return existente
    piso = cen.entradas[existente].kw_util
    for e in sorted(cen.entradas.values(), key=lambda x: x.kva):
        if e.kva > validar.B3_KVA and e.kw_util >= piso and validar.teto_demanda(e) >= demanda_kw:
            return e.id
    return None


def para_envio(sub_norm: dict) -> dict:
    """Submissão normalizada pronta para o juiz (sem `demanda_contratada_kw: null` em B3)."""
    s = {k: v for k, v in sub_norm.items() if k != "demanda_contratada_kw"}
    if sub_norm.get("demanda_contratada_kw") is not None:
        s["demanda_contratada_kw"] = sub_norm["demanda_contratada_kw"]
    return s


def _sub(ag, car, entrada, demanda, pol) -> dict:
    s = {"agencia": ag, "carregadores": dict(car), "entrada": entrada, "politica": dict(pol)}
    if demanda is not None:
        s["demanda_contratada_kw"] = demanda
    return s


def _kw_nominal(car: dict, cen) -> float:
    return sum(n * cen.carregadores[k].potencia_kw for k, n in car.items())


def _demandas(car: dict, cen) -> list:
    teto = max(validar.teto_demanda(e) for e in cen.entradas.values() if e.kva > validar.B3_KVA)
    alto = min(teto, max(validar.DEMANDA_MIN_KW, math.ceil(_kw_nominal(car, cen) / 10) * 10))
    return list(range(validar.DEMANDA_MIN_KW, alto + 1, validar.DEMANDA_PASSO_KW))


def _contextos(car: dict, cen) -> list:
    """(entrada, demanda) usados na busca local: manter a existente e uma A4/SE folgada (demanda = kW nominal)."""
    existente = cen.agencia.entrada_existente
    ctx = [(existente, None)]
    d = _demandas(car, cen)[-1]
    e = entrada_para(d, existente, cen)
    if e is not None and (e, d) not in ctx:
        ctx.append((e, d))
    return ctx


# ---------------- objetivos ----------------

def _escala(ag: str) -> float:
    try:
        return float(json.loads(Path(ESCALA).read_text(encoding="utf-8")).get(ag, 1.0))
    except (OSError, ValueError):
        return 1.0


def _estimativa():
    try:
        est = pesos.carregar(pesos.ESTIMATIVA)
    except (OSError, ValueError, KeyError):
        return None
    return est if est.confiavel else None


def _modo_objetivo(ag: str):
    """('exato', Pesos) | ('estimado', (est, fator)) | ('lexicografico', None)."""
    cat = lote.catalogo()
    if objetivo.tem_pesos(cat, ag):
        return "exato", objetivo.pesos_do_catalogo(cat, ag)
    est = _estimativa()
    if est is not None:
        return "estimado", (est, _escala(ag))
    return "lexicografico", None


def _nota_estimada(est, fator, metricas, sub, existente) -> float:
    f = pesos.features(metricas, sub, existente)
    proibidos = set(est.nao_identificados)
    if any(v and k in proibidos for k, v in f.items()):
        return -math.inf  # peso desconhecido: não arriscar
    return pesos.prever(est, f, fator)


def objetivo_padrao(ag: str):
    """Callable(resultado de lote.avaliar) -> valor (maior é melhor): nota exata, estimada ou lexicográfica."""
    cen = lote.cenario(ag)
    existente = cen.agencia.entrada_existente
    modo, dado = _modo_objetivo(ag)
    if modo == "exato":
        return lambda r: objetivo.nota(r["metricas"], r["sub"], existente, dado)
    if modo == "estimado":
        est, fator = dado
        return lambda r: _nota_estimada(est, fator, r["metricas"], r["sub"], existente)
    return lambda r: objetivo.chave_lexicografica(r["metricas"], r["sub"], cen)


def objetivo_semana_padrao(ag: str):
    """Callable(metricas_semana, sub_norm) -> float, para a robustez: nota da semana ou % de atendimento."""
    existente = lote.cenario(ag).agencia.entrada_existente
    modo, dado = _modo_objetivo(ag)
    if modo == "exato":
        return lambda m, s: objetivo.nota(m, s, existente, dado)
    if modo == "estimado":
        est, fator = dado
        return lambda m, s: _nota_estimada(est, fator, m, s, existente)
    return lambda m, s: float(m["atendimento_pct"])


# ---------------- busca ----------------

class _Busca:
    def __init__(self, ag, obj, eventos=(), processos=None):
        self.ag, self.obj, self.eventos, self.processos = ag, obj, eventos, processos
        self.cen = lote.cenario(ag)
        self.vistos: dict = {}  # hash -> resultado com "valor"

    def avaliar(self, subs) -> list:
        """Resultados na ordem de `subs`; inválidos ou com violação ficam com valor None."""
        out = []
        for r in lote.avaliar_lote(self.ag, subs, self.eventos, self.processos):
            ok = r["valido"] and not r.get("violacoes")
            r["valor"] = self.obj(r) if ok else None
            if ok:
                self.vistos.setdefault(r["hash"], r)
            out.append(r)
        return out

    def melhor_contexto(self, configs, pol) -> list:
        """Para cada config de carregadores, o melhor resultado entre os contextos de entrada (ou None)."""
        subs, donos = [], []
        for i, car in enumerate(configs):
            for e, d in _contextos(car, self.cen):
                subs.append(_sub(self.ag, car, e, d, pol))
                donos.append(i)
        melhores = [None] * len(configs)
        for i, r in zip(donos, self.avaliar(subs)):
            if r["valor"] is not None and (melhores[i] is None or r["valor"] > melhores[i]["valor"]):
                melhores[i] = r
        return melhores

    def escolher_politicas(self, sementes, n) -> list:
        ps = politicas()
        posto = [0.0] * len(ps)
        for car in sementes:
            for e, d in _contextos(car, self.cen):
                rs = self.avaliar([_sub(self.ag, car, e, d, p) for p in ps])
                idx = [i for i, r in enumerate(rs) if r["valor"] is not None]
                idx.sort(key=lambda i: rs[i]["valor"], reverse=True)  # estável: empate fica na ordem do menu
                ordem = {i: k for k, i in enumerate(idx)}
                for i in range(len(ps)):
                    posto[i] += ordem.get(i, len(ps))
        melhores = sorted(range(len(ps)), key=lambda i: (posto[i], i))[:n]
        return [ps[i] for i in melhores]

    def busca_local(self, inicio, pol):
        atual = self.melhor_contexto([inicio], pol)[0]
        car = _limpo(inicio)
        for _ in range(MAX_PASSOS):
            viz = vizinhos(car, self.cen.agencia.vagas)
            rs = self.melhor_contexto(viz, pol)
            cand = [(r, c) for r, c in zip(rs, viz) if r is not None]
            if not cand:
                break
            r, c = max(cand, key=lambda x: x[0]["valor"])
            if atual is not None and not r["valor"] > atual["valor"]:
                break
            atual, car = r, c
        return car, atual

    def varrer(self, car, pol):
        existente = self.cen.agencia.entrada_existente
        opcoes = [(e.id, None) for e in sorted(self.cen.entradas.values(), key=lambda x: x.kva)
                  if e.kva <= validar.B3_KVA]
        opcoes += [(e, d) for d in _demandas(car, self.cen)
                   for e in [entrada_para(d, existente, self.cen)] if e is not None]
        subs = [_sub(self.ag, car, e, d, pol) for e, d in opcoes]
        linhas = []
        for (e, d), s, r in zip(opcoes, subs, self.avaliar(subs)):
            if not r["valido"]:
                continue  # ex.: B3 abaixo da existente
            linhas.append({"demanda": r["sub"]["demanda_contratada_kw"] if d is not None else None,
                           "entrada": e, "valor": r["valor"], "hash": r["hash"],
                           "atendimento_pct": r["metricas"]["atendimento_pct"] if "metricas" in r else None})
        return linhas


def varrer_demanda(ag: str, carregadores: dict, politica: dict, obj, eventos=()) -> list:
    """[{demanda, entrada, valor, hash, atendimento_pct}]: B3 (demanda None) e A4/SE de 30 kW até o kW nominal."""
    return _Busca(ag, obj, eventos).varrer(_limpo(carregadores), politica)


def _sementes(vagas: int, n: int) -> list:
    cands = [{"dc_30": max(1, vagas // 2)}, {"dc_60x2": max(1, vagas // 4)}, {"ac_22x2": max(1, vagas // 2)},
             {"dc_120x2": max(1, vagas // 4)}, {"ac_11": vagas}]
    ok = [c for c in cands if sum(SAIDAS[k] * q for k, q in c.items()) <= vagas]
    return ok[:n] or [{"ac_7": 1}]


def _obra_aproximada(sub: dict, cen) -> tuple:
    """Desempate entre valores iguais (ex.: lexicográfico ignora obra): sem ampliar a entrada, menos demanda,
    menos kW instalado; por fim o hash, para ser determinístico."""
    ampliou = sub["entrada"] != cen.agencia.entrada_existente
    return (cen.entradas[sub["entrada"]].kva if ampliou else 0.0, sub["demanda_contratada_kw"] or 0,
            objetivo.kw_instalado(sub, cen), json.dumps(sub, sort_keys=True))


PARTIDAS = ({"ac_7": 1}, {"dc_30": 1}, {"ac_22x2": 1}, {"dc_60x2": 1})


def buscar(ag: str, modo: str = "rapido", obj=None, eventos=(), processos=None) -> list:
    """Ranking (melhor primeiro) de resultados de lote.avaliar com `valor` e `envio`; grava ranking/demanda."""
    cfg = MODOS[modo]
    obj = obj or objetivo_padrao(ag)
    b = _Busca(ag, obj, eventos, processos)
    vagas = b.cen.agencia.vagas
    pols = b.escolher_politicas(_sementes(vagas, cfg["sementes"]), cfg["politicas"])
    partidas = [p for p in PARTIDAS if sum(SAIDAS[k] * q for k, q in p.items()) <= vagas][:cfg["partidas"]]
    finais = []
    for pol in pols:
        for ini in partidas:
            car, r = b.busca_local(ini, pol)
            if r is not None:
                finais.append((r["valor"], car, pol))
    finais.sort(key=lambda x: x[0], reverse=True)
    vistos, varreduras = set(), []
    for _, car, pol in finais:
        k = json.dumps([car, pol], sort_keys=True)
        if k not in vistos:
            vistos.add(k)
            varreduras.append(b.varrer(car, pol))
    ranking = sorted(sorted(b.vistos.values(), key=lambda r: _obra_aproximada(r["sub"], b.cen)),
                     key=lambda r: r["valor"], reverse=True)
    for r in ranking:
        r["envio"] = para_envio(r["sub"])
    # demanda.json: a varredura que contém o melhor candidato (senão, a da melhor configuração)
    topo = ranking[0]["hash"] if ranking else None
    demanda = next((v for v in varreduras if any(l["hash"] == topo for l in v)), varreduras[0] if varreduras else [])
    _gravar(ag, ranking, demanda)
    return ranking


def _gravar(ag: str, ranking: list, demanda: list) -> None:
    pasta = Path(SAIDA) / ag
    pasta.mkdir(parents=True, exist_ok=True)
    sem = objetivo_semana_padrao(ag)
    top = [{**r, "valor_semanas": [sem(m, r["sub"]) for m in r["semanas"]]} for r in ranking[:TOP_RANKING]]
    (pasta / "ranking.json").write_text(json.dumps(top, ensure_ascii=False, indent=1), encoding="utf-8")
    (pasta / "demanda.json").write_text(json.dumps(demanda, ensure_ascii=False, indent=1), encoding="utf-8")


def main(argv=None) -> None:
    import argparse
    import time

    ap = argparse.ArgumentParser(prog="python -m recarga.otimizador")
    ap.add_argument("agencia")
    ap.add_argument("--modo", choices=tuple(MODOS), default="rapido")
    ap.add_argument("--top", type=int, default=10, help="candidatos considerados na escolha robusta")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    t = time.time()
    ranking = buscar(a.agencia, a.modo)
    if not ranking:
        raise SystemExit("nenhuma submissão válida encontrada")
    escolhida = robustez.escolher(ranking, objetivo_semana_padrao(a.agencia), a.top)
    pos = next(i for i, r in enumerate(ranking) if r is escolhida) + 1
    print(f"# {len(ranking)} candidatos em {time.time() - t:.1f} s; escolhida a {pos}ª do ranking "
          f"(valor = {escolhida['valor']})", file=sys.stderr)
    print(json.dumps(escolhida["envio"], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
