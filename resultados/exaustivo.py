"""Busca exaustiva por agência com os pesos oficiais (H4). Não chama a API.

  PYTHONPATH=. python resultados/exaustivo.py Istanbul Hanoi Zurich
"""
import itertools, json, sys, time
import recarga
from recarga import lote, objetivo, melhores

SAIDAS = {"ac_7": 1, "ac_11": 1, "ac_22x2": 2, "dc_30": 1, "dc_60x2": 2, "dc_120x2": 2}
TIPOS = list(SAIDAS)
POLITICAS = [{"prioridade": p, "evitar_ponta": e, "divisao": d}
             for p in ("proxima_retirada", "menor_soc", "chegada") for e in (False, True) for d in ("igual", "prioridade")]


def combinacoes(vagas, max_unid=6):
    for qs in itertools.product(range(max_unid + 1), repeat=len(TIPOS)):
        if sum(qs) and sum(q * SAIDAS[t] for q, t in zip(qs, TIPOS)) <= vagas:
            yield {t: q for q, t in zip(qs, TIPOS) if q}


def entradas(ex):
    ops = [(ex, None)]
    if ex == "b3_45":
        ops.append(("b3_75", None))
    ops += [("a4_150", d) for d in (60, 80, 100, 130)]
    return ops


def nota(r, ex, pes):
    return objetivo.nota(r["metricas"], r["sub"], ex, pes)


def robusta(r, ex, pes):
    """Nota pública penalizada como se as 4 semanas ocultas fossem iguais à pior semana pública."""
    sem = [objetivo.nota(s, r["sub"], ex, pes) for s in r["semanas"]]
    obra_dem = nota(r, ex, pes) - sum(sem)  # obra/demanda contadas 4x nas semanas; corrige p/ 1x
    return 4 * min(sem) + obra_dem


if __name__ == "__main__":
    pes = melhores.estimativa().pesos
    saida = {}
    for ag in sys.argv[1:]:
        t0 = time.time()
        cen = lote.cenario(ag); ex = cen.agencia.entrada_existente; vagas = cen.agencia.vagas
        base = {"prioridade": "proxima_retirada", "evitar_ponta": False, "divisao": "igual"}
        # fase 1: todas as combinações x entradas com 2 políticas
        subs = [{"agencia": ag, "carregadores": c, "entrada": e, **({"demanda_contratada_kw": d} if d else {}),
                 "politica": p}
                for c in combinacoes(vagas) for e, d in entradas(ex)
                for p in (base, {**base, "evitar_ponta": True})]
        rs = [r for r in lote.avaliar_lote(ag, subs) if r["valido"]]
        rs.sort(key=lambda r: -robusta(r, ex, pes))
        # fase 2: 12 políticas nas 25 melhores infraestruturas
        top = []
        for r in rs:
            k = (json.dumps(r["sub"]["carregadores"], sort_keys=True), r["sub"]["entrada"], r["sub"]["demanda_contratada_kw"])
            if k not in top:
                top.append(k)
            if len(top) == 25:
                break
        subs2 = [{"agencia": ag, "carregadores": json.loads(c), "entrada": e,
                  **({"demanda_contratada_kw": d} if d and e != ex and not e.startswith("b3") else {}), "politica": p}
                 for c, e, d in top for p in POLITICAS]
        rs2 = [r for r in lote.avaliar_lote(ag, subs2) if r["valido"]] + rs[:50]
        uniq = {r["hash"]: r for r in rs2}.values()
        lst = sorted(uniq, key=lambda r: -robusta(r, ex, pes))[:10]
        saida[ag] = [{"sub": {k: v for k, v in r["sub"].items() if v is not None},
                      "nota_publica": round(nota(r, ex, pes), 1), "nota_robusta": round(robusta(r, ex, pes), 1),
                      "perdidos_por_semana": [s["nao_atendidos"] for s in r["semanas"]],
                      "atendimento_pct": round(r["metricas"]["atendimento_pct"], 2)} for r in lst]
        print(f"== {ag} ({len(subs)}+{len(subs2)} simulações, {time.time() - t0:.0f}s)", flush=True)
        for x in saida[ag][:5]:
            print(f"  pub {x['nota_publica']:8.0f} rob {x['nota_robusta']:8.0f} perd/sem {x['perdidos_por_semana']} "
                  f"{x['sub']['carregadores']} {x['sub']['entrada']} {x['sub'].get('demanda_contratada_kw')} {x['sub']['politica']}", flush=True)
    json.dump(saida, open("resultados/exaustivo.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
