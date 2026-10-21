"""Busca bruta local em Vienna (30 vagas, 24h, entrada existente a4_150). Não chama a API."""
import itertools, json, time
import recarga
from recarga import lote, objetivo, melhores

AG = "Vienna"
if __name__ == "__main__":
    pes = melhores.estimativa().pesos; ex = lote.cenario(AG).agencia.entrada_existente
    nota = lambda r: objetivo.nota(r["metricas"], r["sub"], ex, pes)
    t0 = time.time(); subs = []
    for a7, d30, a22, d60 in itertools.product(range(0, 21, 2), range(0, 4), range(0, 4), range(0, 3)):
        car = {k: v for k, v in (("ac_7", a7), ("dc_30", d30), ("ac_22x2", a22), ("dc_60x2", d60)) if v}
        saidas = a7 + d30 + 2 * a22 + 2 * d60
        if not car or saidas > 30:
            continue
        for dem in (40, 60, 80, 100, 130):
            for ep in (False, True):
                subs.append({"agencia": AG, "carregadores": car, "entrada": "a4_150", "demanda_contratada_kw": dem,
                             "politica": {"prioridade": "proxima_retirada", "evitar_ponta": ep, "divisao": "igual"}})
    rs = [r for r in lote.avaliar_lote(AG, subs) if r["valido"]]
    rs.sort(key=lambda r: -nota(r))
    print(f"fase 1: {len(subs)} simulações em {time.time() - t0:.0f}s", flush=True)
    # fase 2: refina as 15 melhores infraestruturas (ac_7 de 1 em 1, 12 políticas)
    pols = [{"prioridade": p, "evitar_ponta": e, "divisao": d} for p in ("proxima_retirada", "menor_soc", "chegada")
            for e in (False, True) for d in ("igual", "prioridade")]
    subs2 = []
    for r in rs[:15]:
        car = dict(r["sub"]["carregadores"]); dem = r["sub"]["demanda_contratada_kw"]
        for delta in (-1, 0, 1):
            c = dict(car); c["ac_7"] = c.get("ac_7", 0) + delta
            c = {k: v for k, v in c.items() if v > 0}
            if not c:
                continue
            for d in (dem - 10, dem, dem + 10):
                if 30 <= d <= 130:
                    subs2 += [{"agencia": AG, "carregadores": c, "entrada": "a4_150", "demanda_contratada_kw": d, "politica": p} for p in pols]
    rs2 = {r["hash"]: r for r in [x for x in lote.avaliar_lote(AG, subs2) if x["valido"]] + rs[:100]}.values()
    top = sorted(rs2, key=lambda r: -nota(r))[:12]
    out = [{"sub": {k: v for k, v in r["sub"].items() if v is not None}, "nota": round(nota(r), 1),
            "perdidos_por_semana": [s["nao_atendidos"] for s in r["semanas"]], "upgrades": r["metricas"]["upgrades"],
            "ponta_kwh": round(r["metricas"]["energia_ponta_kwh"], 1)} for r in top]
    json.dump(out, open("resultados/vienna_bruto.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for o in out:
        print(f"nota {o['nota']:8.0f} perd/sem {o['perdidos_por_semana']} upg {o['upgrades']:3} ponta {o['ponta_kwh']:7.1f}  "
              f"{o['sub']['carregadores']} d={o['sub']['demanda_contratada_kw']} {o['sub']['politica']}")
    print(f"total {time.time() - t0:.0f}s")
