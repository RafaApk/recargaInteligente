"""Lisbon: busca com os pesos oficiais da agência (energia na ponta −5/kWh, 10× as outras). Não chama a API.

  PYTHONPATH=. python resultados/lisbon_ponta.py
Fase 1: carregadores × entradas (inclui A4) × {evitar_ponta, não evitar}. Fase 2: 12 políticas nas 20 melhores.
"""
import itertools, json, time
import recarga
from recarga import lote, objetivo, melhores

AG = "Lisbon"
SAIDAS = {"ac_7": 1, "ac_22x2": 2, "dc_30": 1, "dc_60x2": 2, "dc_120x2": 2}
MAX = {"ac_7": 8, "ac_22x2": 4, "dc_30": 4, "dc_60x2": 4, "dc_120x2": 2}
ENTRADAS = [("b3_45", None), ("b3_75", None), ("a4_150", 70), ("a4_150", 100), ("a4_150", 130),
            ("a4_225", 150), ("a4_225", 200)]
POLS = [{"prioridade": p, "evitar_ponta": e, "divisao": d} for p in ("proxima_retirada", "menor_soc", "chegada")
        for e in (False, True) for d in ("igual", "prioridade")]

if __name__ == "__main__":
    pes = melhores.pesos_agencia(AG); cen = lote.cenario(AG); ex = cen.agencia.entrada_existente
    nota = lambda r: objetivo.nota(r["metricas"], r["sub"], ex, pes)
    t0 = time.time()
    tipos = list(SAIDAS)
    combos = [{t: q for q, t in zip(qs, tipos) if q} for qs in itertools.product(*(range(MAX[t] + 1) for t in tipos))
              if sum(qs) and sum(q * SAIDAS[t] for q, t in zip(qs, tipos)) <= cen.agencia.vagas]
    base = {"prioridade": "proxima_retirada", "divisao": "igual"}
    subs = [{"agencia": AG, "carregadores": c, "entrada": e, **({"demanda_contratada_kw": d} if d else {}),
             "politica": {**base, "evitar_ponta": ep}}
            for c in combos for e, d in ENTRADAS for ep in (False, True)]
    rs = [r for r in lote.avaliar_lote(AG, subs) if r["valido"]]
    rs.sort(key=lambda r: -nota(r))
    print(f"fase 1: {len(subs)} simulações em {time.time() - t0:.0f}s; melhor {nota(rs[0]):.0f}", flush=True)
    top, vis = [], set()
    for r in rs:
        k = (json.dumps(r["sub"]["carregadores"], sort_keys=True), r["sub"]["entrada"], r["sub"]["demanda_contratada_kw"])
        if k not in vis:
            vis.add(k); top.append(k)
        if len(top) == 20:
            break
    subs2 = [{"agencia": AG, "carregadores": json.loads(c), "entrada": e, **({"demanda_contratada_kw": d} if d else {}), "politica": p}
             for c, e, d in top for p in POLS]
    todos = {r["hash"]: r for r in [x for x in lote.avaliar_lote(AG, subs2) if x["valido"]] + rs[:100]}.values()
    lst = sorted(todos, key=lambda r: -nota(r))[:12]
    out = [{"sub": {k: v for k, v in r["sub"].items() if v is not None}, "nota": round(nota(r), 1),
            "perdidos_por_semana": [s["nao_atendidos"] for s in r["semanas"]], "upgrades": r["metricas"]["upgrades"],
            "ponta_kwh": round(r["metricas"]["energia_ponta_kwh"], 1), "pico_kw": round(r["metricas"]["pico_kw"], 1)} for r in lst]
    json.dump(out, open("resultados/lisbon_ponta.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for o in out:
        print(f"nota {o['nota']:8.0f} perd/sem {o['perdidos_por_semana']} upg {o['upgrades']:3} ponta {o['ponta_kwh']:7.1f} pico {o['pico_kw']:6.1f} "
              f"{o['sub']['carregadores']} {o['sub']['entrada']} {o['sub'].get('demanda_contratada_kw')} {o['sub']['politica']}", flush=True)
    print(f"total {time.time() - t0:.0f}s")
