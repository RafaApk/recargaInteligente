"""Marrakech: escolhe a config com a melhor nota no pior cenário de corte (regra exata do evento desconhecida).

  PYTHONPATH=. python resultados/marrakech_robusto.py
Cenários: sem evento + corte do limite (×0,3 e ×0,5) por 2 dias, começando seg/qua/sex das semanas 2 e 3.
Não chama a API.
"""
import itertools, json, time
import recarga
from recarga import lote, objetivo, melhores

AG = "Marrakech"
SAIDAS = {"ac_7": 1, "ac_11": 1, "ac_22x2": 2, "dc_30": 1, "dc_60x2": 2}
DIA = 1440
INICIOS = [d * DIA for d in (8, 10, 12, 15, 17, 19)]  # seg/qua/sex 25/10..05/11
CENARIOS = [[]] + [[["corte", AG, i, i + 2 * DIA, f]] for f in (0.3, 0.5) for i in INICIOS]


def combinacoes(vagas, max_unid=5):
    tipos = list(SAIDAS)
    for qs in itertools.product(range(max_unid + 1), repeat=len(tipos)):
        if sum(qs) and sum(q * SAIDAS[t] for q, t in zip(qs, tipos)) <= vagas:
            yield {t: q for q, t in zip(qs, tipos) if q}


if __name__ == "__main__":
    pes = melhores.estimativa().pesos
    cen = lote.cenario(AG); ex = cen.agencia.entrada_existente
    nota = lambda r: objetivo.nota(r["metricas"], r["sub"], ex, pes)
    pol = {"prioridade": "proxima_retirada", "evitar_ponta": True, "divisao": "igual"}
    t0 = time.time()
    subs = [{"agencia": AG, "carregadores": c, "entrada": e, **({"demanda_contratada_kw": d} if d else {}), "politica": p}
            for c in combinacoes(cen.agencia.vagas)
            for e, d in (("b3_45", None), ("b3_75", None), ("a4_150", 80), ("a4_150", 110))
            for p in (pol, {**pol, "evitar_ponta": False})]
    base = [r for r in lote.avaliar_lote(AG, subs) if r["valido"]]
    base.sort(key=lambda r: -nota(r))
    top = base[:30]
    print(f"fase 1: {len(subs)} simulações em {time.time() - t0:.0f}s; melhor sem evento {nota(top[0]):.0f}", flush=True)
    linhas = []
    for r in top:
        envio = {k: v for k, v in r["sub"].items() if v is not None}
        notas = [nota(x) for x in (lote.avaliar(AG, envio, eventos=ev) for ev in CENARIOS)]
        linhas.append({"sub": envio, "sem_evento": round(notas[0], 1), "pior_cenario": round(min(notas), 1),
                       "media_cenarios": round(sum(notas) / len(notas), 1)})
    linhas.sort(key=lambda l: -l["pior_cenario"])
    json.dump(linhas, open("resultados/marrakech_robusto.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for l in linhas[:8]:
        print(f"pior {l['pior_cenario']:8.0f} média {l['media_cenarios']:8.0f} sem evento {l['sem_evento']:8.0f}  "
              f"{l['sub']['carregadores']} {l['sub']['entrada']} {l['sub'].get('demanda_contratada_kw')} {l['sub']['politica']}")
    print(f"total {time.time() - t0:.0f}s")
