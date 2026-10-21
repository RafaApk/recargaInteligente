"""Vienna: busca bruta fina nas combinações com obra até 1.500 (onde pode haver nota > 11.900). Não chama a API."""
import itertools
import recarga
from recarga import lote, objetivo, melhores

if __name__ == "__main__":
    est = melhores.estimativa(); AG = "Vienna"; ex = "a4_150"
    CUSTO = {"ac_7": 250, "ac_11": 1100, "ac_22x2": 1500}
    combos = []
    for a7, a11, a22 in itertools.product(range(0, 7), range(0, 2), range(0, 2)):
        c = {k: v for k, v in (("ac_7", a7), ("ac_11", a11), ("ac_22x2", a22)) if v}
        if c and sum(CUSTO[k] * v for k, v in c.items()) <= 1500:
            combos.append(c)
    pols = [{"prioridade": p, "evitar_ponta": e, "divisao": d} for p in ("proxima_retirada", "menor_soc", "chegada")
            for e in (False, True) for d in ("igual", "prioridade")]
    subs = [{"agencia": AG, "carregadores": c, "entrada": ex, "demanda_contratada_kw": dm, "politica": p}
            for c in combos for dm in (30, 40) for p in pols]
    rs = [r for r in lote.avaliar_lote(AG, subs) if r["valido"]]
    nota = lambda r: objetivo.nota(r["metricas"], r["sub"], ex, est.pesos)
    rs.sort(key=lambda r: -nota(r))
    print(len(subs), "simulações;", len(combos), "combinações com obra <= 1500")
    vis = set()
    for r in rs:
        k = (str(r["sub"]["carregadores"]), r["sub"]["demanda_contratada_kw"])
        if k in vis:
            continue
        vis.add(k); m = r["metricas"]
        print(f"nota {nota(r):7.0f} perd {m['nao_atendidos']:3} upg {m['upgrades']:3} {r['sub']['carregadores']} "
              f"d={r['sub']['demanda_contratada_kw']} {r['sub']['politica']}")
        if len(vis) == 8:
            break
