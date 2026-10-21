"""Zurich: busca exaustiva + estresse de potência para achar a opção mais conservadora. Não chama a API.

  PYTHONPATH=. python resultados/zurich_pesado.py
Estresse: limite da entrada × 0,9 e × 0,8 durante as 4 semanas (proxy de semanas ocultas mais apertadas).
"""
import itertools, json, time
import recarga
from recarga import lote, objetivo, melhores

import sys
AG = sys.argv[1] if len(sys.argv) > 1 else "Zurich"
SAIDAS = {"ac_7": 1, "ac_11": 1, "ac_22x2": 2, "dc_30": 1, "dc_60x2": 2, "dc_120x2": 2}
POLS = [{"prioridade": p, "evitar_ponta": e, "divisao": d} for p in ("proxima_retirada", "menor_soc", "chegada")
        for e in (False, True) for d in ("igual", "prioridade")]
FIM = 40 * 1440
ESTRESSE = {"normal": [], "pot90": [["corte", AG, 1080, FIM, 0.9]], "pot80": [["corte", AG, 1080, FIM, 0.8]]}

if __name__ == "__main__":
    pes = melhores.estimativa().pesos; cen = lote.cenario(AG); ex = cen.agencia.entrada_existente
    nota = lambda r: objetivo.nota(r["metricas"], r["sub"], ex, pes)
    t0 = time.time()
    combos = [{t: q for q, t in zip(qs, SAIDAS) if q} for qs in itertools.product(range(5), repeat=len(SAIDAS))
              if sum(qs) and sum(q * SAIDAS[t] for q, t in zip(qs, SAIDAS)) <= cen.agencia.vagas]
    entradas = [(ex, None)] + ([("b3_75", None)] if ex == "b3_45" else []) + [("a4_150", d) for d in (70, 90, 110)]
    subs = [{"agencia": AG, "carregadores": c, "entrada": e, **({"demanda_contratada_kw": d} if d else {}), "politica": p}
            for c in combos for e, d in entradas for p in POLS]
    rs = [r for r in lote.avaliar_lote(AG, subs) if r["valido"]]
    rs.sort(key=lambda r: -nota(r))
    print(f"fase 1: {len(subs)} simulações em {time.time() - t0:.0f}s", flush=True)
    linhas = []
    for r in rs[:40]:
        envio = {k: v for k, v in r["sub"].items() if v is not None}
        res = {k: lote.avaliar(AG, envio, eventos=ev) for k, ev in ESTRESSE.items()}
        n = {k: nota(x) for k, x in res.items()}
        linhas.append({"sub": envio, **{f"nota_{k}": round(v, 1) for k, v in n.items()},
                       "perdidos": {k: x["metricas"]["nao_atendidos"] for k, x in res.items()},
                       "pior": round(min(n.values()), 1)})
    linhas.sort(key=lambda l: -l["pior"])
    json.dump(linhas, open("resultados/pesado_" + AG.lower() + ".json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for l in linhas[:10]:
        print(f"pior {l['pior']:8.0f} | normal {l['nota_normal']:7.0f} pot90 {l['nota_pot90']:7.0f} pot80 {l['nota_pot80']:7.0f} "
              f"| perd {l['perdidos']} | {l['sub']['carregadores']} {l['sub']['entrada']} {l['sub'].get('demanda_contratada_kw')} {l['sub']['politica']}")
    print(f"total {time.time() - t0:.0f}s")
