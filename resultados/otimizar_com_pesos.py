"""Otimiza cada agência com os pesos confirmados de Bangkok (nota estimada). Não chama a API."""
import json, sys, time
import recarga
from recarga import lote, objetivo, otimizador, robustez

def pesos():
    P = json.load(open("pesos_estimados/pesos_bangkok_confirmados.json", encoding="utf-8"))
    c = P["custo_obra_em_pontos"]
    return objetivo.Pesos(w=P["pesos"], k_carregador={k: -v for k, v in c["carregadores"].items()},
                          k_entrada={k: -v for k, v in c["entradas"].items() if k != "existente"})

if __name__ == "__main__":
    pes = pesos(); out = {}
    for ag in sys.argv[1:]:
        ex = lote.cenario(ag).agencia.entrada_existente
        obj = lambda r, ex=ex: objetivo.nota(r["metricas"], r["sub"], ex, pes)
        sem = lambda m, s, ex=ex: objetivo.nota(m, s, ex, pes)
        t = time.time(); rk = otimizador.buscar(ag, "completo", obj=obj)
        esc = robustez.escolher(rk, sem, top=10)
        m = esc["metricas"]
        out[ag] = {"sub": esc.get("envio") or {k: v for k, v in esc["sub"].items() if v is not None},
                   "nota_estimada_publica": round(obj(esc), 1),
                   "notas_por_semana": [round(sem(s, esc["sub"]), 1) for s in esc["semanas"]],
                   "melhor_nota_publica_do_ranking": round(rk[0]["valor"], 1),
                   "metricas": {k: m[k] for k in ("atendimento_pct", "certos", "upgrades", "nao_atendidos", "energia_ponta_kwh", "pico_kw", "demanda_contratada_kw")},
                   "candidatos": len(rk), "segundos": round(time.time() - t, 1)}
        print(ag, json.dumps(out[ag], ensure_ascii=False), flush=True)
    json.dump(out, open("resultados/otimizacao_com_pesos.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
