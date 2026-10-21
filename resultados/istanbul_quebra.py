"""Istanbul: busca de config resistente ao evento 'quebra_maiores' (2 maiores carregadores fora por 2 dias).

  PYTHONPATH=. python resultados/istanbul_quebra.py
Cenários: evento na janela real (21600–24480) e deslocado para começar em cada dia das semanas 1–4
(horário desconhecido nas semanas ocultas). Não chama a API.
"""
import itertools, json, time
import recarga
from recarga import lote, objetivo, melhores

AG = "Istanbul"
SAIDAS = {"ac_7": 1, "ac_11": 1, "ac_22x2": 2, "dc_30": 1, "dc_60x2": 2, "dc_120x2": 2}
DIA = 1440
REAL = [["quebra_maiores", AG, 2, 21600, 24480]]
DESLOC = [[["quebra_maiores", AG, 2, d * DIA, (d + 2) * DIA]] for d in range(2, 26, 2)]

if __name__ == "__main__":
    pes = melhores.estimativa().pesos; cen = lote.cenario(AG); ex = cen.agencia.entrada_existente
    nota = lambda r: objetivo.nota(r["metricas"], r["sub"], ex, pes)
    t0 = time.time()
    combos = [{t: q for q, t in zip(qs, SAIDAS) if q} for qs in itertools.product(range(5), repeat=len(SAIDAS))
              if sum(qs) and sum(q * SAIDAS[t] for q, t in zip(qs, SAIDAS)) <= cen.agencia.vagas]
    pols = [{"prioridade": p, "evitar_ponta": False, "divisao": d} for p in ("proxima_retirada", "chegada", "menor_soc")
            for d in ("igual", "prioridade")]
    entradas = [(ex, None), ("b3_75", None), ("a4_150", 80), ("a4_150", 110)]
    subs = [{"agencia": AG, "carregadores": c, "entrada": e, **({"demanda_contratada_kw": d} if d else {}), "politica": p}
            for c in combos for e, d in entradas for p in pols]
    rs = [r for r in lote.avaliar_lote(AG, subs, eventos=REAL) if r["valido"]]
    rs.sort(key=lambda r: -nota(r))
    print(f"fase 1 (com o evento real): {len(subs)} simulações em {time.time() - t0:.0f}s", flush=True)
    linhas = []
    for r in rs[:25]:
        envio = {k: v for k, v in r["sub"].items() if v is not None}
        ns = [nota(lote.avaliar(AG, envio, eventos=ev)) for ev in DESLOC]
        sem = nota(lote.avaliar(AG, envio))
        linhas.append({"sub": envio, "com_evento_real": round(nota(r), 1), "sem_evento": round(sem, 1),
                       "deslocado_min": round(min(ns), 1), "deslocado_media": round(sum(ns) / len(ns), 1),
                       "perdidos_evento_real": r["metricas"]["nao_atendidos"]})
    linhas.sort(key=lambda l: -l["deslocado_media"])
    json.dump(linhas, open("resultados/istanbul_quebra.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for l in linhas[:10]:
        print(f"real {l['com_evento_real']:7.0f} | desloc média {l['deslocado_media']:7.0f} min {l['deslocado_min']:7.0f} | sem ev {l['sem_evento']:7.0f} "
              f"| perd {l['perdidos_evento_real']:2} | {l['sub']['carregadores']} {l['sub']['entrada']} {l['sub'].get('demanda_contratada_kw')} {l['sub']['politica']}")
    print(f"total {time.time() - t0:.0f}s")
