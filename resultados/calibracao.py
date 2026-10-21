"""Calibra variantes do motor contra todas as notas do juiz que já temos (fora Bangkok). Não chama a API.

  PYTHONPATH=. python resultados/calibracao.py
"""
import json
import recarga
from recarga import lote, objetivo, melhores
from kickoff import motor, validar, medicao, tempo

P = lambda pr, ep, dv: {"prioridade": pr, "evitar_ponta": ep, "divisao": dv}
CORTE = [["corte", "Marrakech", 31680, 34560, 0.7]]
# (agência, carregadores, entrada, demanda, política, eventos ativos no teste, nota do juiz)
JUIZ = [
    ("Istanbul", {"dc_60x2": 1}, "b3_75", None, P("proxima_retirada", True, "igual"), [], 7095.0),
    ("Istanbul", {"ac_7": 3, "dc_30": 1}, "b3_75", None, P("proxima_retirada", False, "prioridade"), [], 8826.28),
    ("Hanoi", {"ac_7": 2, "dc_60x2": 1}, "b3_75", None, P("proxima_retirada", False, "igual"), [], 3519.26),
    ("Hanoi", {"ac_7": 5, "dc_30": 1}, "b3_75", None, P("proxima_retirada", False, "igual"), [], 6211.02),
    ("Zurich", {"ac_7": 1, "dc_60x2": 1}, "b3_75", None, P("proxima_retirada", False, "prioridade"), [], 3003.48),
    ("Marrakech", {"ac_22x2": 5}, "a4_150", 110, P("proxima_retirada", True, "igual"), CORTE, -3759.0),
    ("Marrakech", {"ac_7": 7, "ac_22x2": 1, "dc_30": 1}, "a4_150", 130, P("proxima_retirada", True, "igual"), CORTE, 4842.0),
    ("Marrakech", {"ac_7": 9, "dc_30": 1}, "a4_150", 100, P("proxima_retirada", True, "prioridade"), CORTE, 5152.0),
    ("Vienna", {"ac_7": 5}, "a4_150", 40, P("proxima_retirada", True, "igual"), [], 11630.0),
]


def nota_motor(classe, ag, car, ent, dem, pol, ev, pes):
    cen = lote.cenario(ag)
    sub = {"agencia": ag, "carregadores": car, "entrada": ent, "politica": pol, **({"demanda_contratada_kw": dem} if dem else {})}
    n = validar.normalizar(sub, cen)
    res = classe(cen, n, ev).rodar()
    m = medicao.metricas(res.retiradas, res.nao_atendidos, res.bins, *tempo.JANELA_PUBLICA)
    m["demanda_contratada_kw"] = n["demanda_contratada_kw"] or 0.0
    return objetivo.nota(m, n, cen.agencia.entrada_existente, pes), m["nao_atendidos"]


def avaliar(nome, classe, pes, lote_t0=True):
    motor.PLUG_T0_EM_LOTE = lote_t0
    erros = []
    for ag, car, ent, dem, pol, ev, juiz in JUIZ:
        n, perd = nota_motor(classe, ag, car, ent, dem, pol, ev, pes)
        erros.append(abs(n - juiz))
        print(f"  {ag:9} {str(car):38} juiz {juiz:9.1f} motor {n:9.1f} dif {n - juiz:8.1f} perd {perd}", flush=True)
    print(f"== {nome}: erro absoluto total {sum(erros):.0f}, máximo {max(erros):.0f}\n", flush=True)


if __name__ == "__main__":
    pes = melhores.estimativa().pesos
    avaliar("T0 em lote (atual)", motor.Motor, pes, True)
    avaliar("T0 carro a carro", motor.Motor, pes, False)
