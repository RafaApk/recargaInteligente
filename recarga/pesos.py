"""Inferência dos pesos ocultos na Neblina (spec 5.1).

Modelo linear: nota = Σ w_i·quantidade_i + Σ k_car·qtd_car + k_entrada (entrada ampliada), sem intercepto
(certos + upgrades + nao_atendidos é constante na agência, então o peso de não atendido faz esse papel).

  python -m recarga.pesos coletar   # testes grátis em Bangkok via Juiz; grava resultados/pesos/amostras.json
  python -m recarga.pesos estimar   # mínimos quadrados; grava resultados/pesos/estimativa.json
"""
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from recarga import RESULTADOS, lote
from recarga.objetivo import ITENS_OPERACAO, METRICA, Pesos

ESTIMATIVA = RESULTADOS / "pesos" / "estimativa.json"
AMOSTRAS = RESULTADOS / "pesos" / "amostras.json"
FISICAS = ("atendimento_pct", "energia_kwh", "pico_kw")
TOL_REL, TOL_ABS = 1e-3, 0.05
CONFIANCA = 0.01  # resíduo RMS máximo, relativo à média de |nota|


@dataclass
class Estimativa:
    pesos: Pesos
    residuo_rms: float
    n: int
    confiavel: bool
    nao_identificados: list = field(default_factory=list)


def features(metricas: dict, sub_norm: dict, entrada_existente: str) -> dict:
    """Quantidades que multiplicam cada incógnita: itens de operação, `car:<id>` (qtd), `ent:<id>` (1 se ampliou)."""
    f = {i: metricas[METRICA[i]] or 0 for i in ITENS_OPERACAO}
    f.update({f"car:{k}": n for k, n in sub_norm["carregadores"].items() if n})
    if sub_norm["entrada"] != entrada_existente:
        f[f"ent:{sub_norm['entrada']}"] = 1
    return f


def _pesos_de(coefs: dict) -> Pesos:
    return Pesos(
        w={k: v for k, v in coefs.items() if k in ITENS_OPERACAO},
        k_carregador={k[4:]: v for k, v in coefs.items() if k.startswith("car:")},
        k_entrada={k[4:]: v for k, v in coefs.items() if k.startswith("ent:")},
    )


def estimar(amostras: list) -> Estimativa:
    """Mínimos quadrados sobre [(features, nota)].

    `confiavel` exige resíduo RMS <= 1% da média de |nota| e posto cheio nas colunas identificáveis
    (com posto deficiente o ajuste pode ser exato e os pesos, arbitrários).
    """
    colunas = sorted(set(ITENS_OPERACAO).union(*(f.keys() for f, _ in amostras)))
    n = len(amostras)
    if n == 0:
        return Estimativa(Pesos({}), math.inf, 0, False, colunas)
    X = np.array([[float(f.get(c, 0.0)) for c in colunas] for f, _ in amostras])
    y = np.array([float(nota) for _, nota in amostras])
    usadas = np.any(X != 0.0, axis=0)
    nao = [c for c, u in zip(colunas, usadas) if not u]
    Xu = X[:, usadas]
    coef, _, posto, _ = np.linalg.lstsq(Xu, y, rcond=None)
    rms = float(np.sqrt(np.mean((Xu @ coef - y) ** 2)))
    ref = float(np.mean(np.abs(y)))
    confiavel = bool(posto == Xu.shape[1] and rms <= CONFIANCA * ref)
    coefs = {c: float(v) for c, v in zip([c for c, u in zip(colunas, usadas) if u], coef)}
    return Estimativa(_pesos_de(coefs), rms, n, confiavel, nao)


def _partes(est: Estimativa, f: dict):
    """(parte operacional, parte de obra) da nota prevista."""
    p = est.pesos
    op = sum(p.w.get(k, 0.0) * f.get(k, 0.0) for k in ITENS_OPERACAO)
    obra = sum(v * p.k_carregador.get(k[4:], 0.0) for k, v in f.items() if k.startswith("car:"))
    obra += sum(v * p.k_entrada.get(k[4:], 0.0) for k, v in f.items() if k.startswith("ent:"))
    return op, obra


def prever(est: Estimativa, f: dict, fator: float = 1.0) -> float:
    op, obra = _partes(est, f)
    return fator * op + obra


def escala(est: Estimativa, amostras_ag: list) -> float:
    """Fator único sobre os pesos operacionais que minimiza o erro quadrático nas amostras da agência."""
    num = den = 0.0
    for f, nota in amostras_ag:
        op, obra = _partes(est, f)
        num += op * (nota - obra)
        den += op * op
    return num / den if den else 1.0


def para_dict(est: Estimativa) -> dict:
    return {
        "pesos": {"w": est.pesos.w, "k_carregador": est.pesos.k_carregador, "k_entrada": est.pesos.k_entrada},
        "residuo_rms": est.residuo_rms,
        "n": est.n,
        "confiavel": est.confiavel,
        "nao_identificados": list(est.nao_identificados),
    }


def salvar(est: Estimativa, path=ESTIMATIVA) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(para_dict(est), ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def carregar(path=ESTIMATIVA) -> Estimativa:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    p = d["pesos"]
    return Estimativa(Pesos(dict(p["w"]), dict(p["k_carregador"]), dict(p["k_entrada"])),
                      float(d["residuo_rms"]), int(d["n"]), bool(d["confiavel"]), list(d["nao_identificados"]))


# ---------------- desenho de experimentos (Bangkok, grátis) ----------------

P_PADRAO = {"prioridade": "menor_soc", "evitar_ponta": False, "divisao": "igual"}
P_PROX = {"prioridade": "proxima_retirada", "evitar_ponta": False, "divisao": "prioridade"}
P_CHEG = {"prioridade": "chegada", "evitar_ponta": False, "divisao": "igual"}


def experimentos_bangkok() -> list:
    """Submissões válidas em Bangkok cobrindo os blocos da spec 5.1 (sem repetição)."""
    ag = "Bangkok"
    cen = lote.cenario(ag)
    existente = cen.agencia.entrada_existente

    def sub(car, ent, dem=None, pol=P_PADRAO):
        s = {"agencia": ag, "carregadores": dict(car), "entrada": ent, "politica": dict(pol)}
        if dem is not None:
            s["demanda_contratada_kw"] = dem
        return s

    out = []
    # Demanda: 52 kW nominais (< menor demanda testada): operação idêntica, isola o peso por kW contratado.
    out += [sub({"dc_30": 1, "ac_22x2": 1}, "a4_150", d) for d in range(60, 131, 10)]
    out += [sub({"dc_30": 1, "ac_22x2": 1}, "a4_225", d) for d in (140, 200)]
    # Ponta: pares que só diferem em evitar_ponta.
    for car, ent, dem in (({"dc_60x2": 2, "ac_22x2": 1}, "b3_75", None),
                          ({"ac_22x2": 2, "ac_11": 2}, existente, None),
                          ({"dc_60x2": 1, "dc_30": 2, "ac_7": 2}, "a4_150", 100)):
        out += [sub(car, ent, dem, {**P_PROX, "evitar_ponta": ep}) for ep in (False, True)]
    # Carregadores: entrada existente (custa 0), variando quantidade e tipo.
    for car in ({"ac_7": 1}, {"ac_7": 2}, {"ac_7": 3}, {"ac_11": 2}, {"ac_11": 4}, {"ac_22x2": 1}, {"ac_22x2": 3},
                {"dc_30": 1}, {"dc_30": 3}, {"dc_60x2": 1}, {"dc_60x2": 2}, {"dc_120x2": 1}, {"dc_120x2": 2},
                {"ac_7": 2, "dc_30": 2}, {"ac_11": 1, "dc_60x2": 1, "ac_22x2": 1}):
        out.append(sub(car, existente))
    # Entradas: mesma operação (14 e 22 kW nominais, abaixo da demanda mínima de 30 kW) em cada nível.
    for e in sorted(cen.entradas.values(), key=lambda x: x.kva):
        if e.id == existente:
            continue
        dem = 30 if e.kva > 75 else None
        out += [sub({"ac_7": 2}, e.id, dem), sub({"ac_11": 2}, e.id, dem)]
    # Operação: infra fraca (muitas perdas) e forte.
    out += [sub({"ac_7": 1}, existente, pol=P_PROX),
            sub({"dc_120x2": 3}, "se_500", 450, P_PROX),
            sub({"dc_60x2": 3}, "a4_300", 270, P_PROX),
            sub({"dc_120x2": 2, "dc_60x2": 1}, "a4_225", 200, P_CHEG)]

    vistos, unicos = set(), []
    from kickoff import validar
    for s in out:
        k = json.dumps(validar.normalizar(s, cen), sort_keys=True)
        if k not in vistos:
            vistos.add(k)
            unicos.append(s)
    return unicos


# ---------------- coleta com o juiz ----------------

def _bate(a, b) -> bool:
    return a is not None and b is not None and math.isclose(float(a), float(b), rel_tol=TOL_REL, abs_tol=TOL_ABS)


def coletar(juiz, ag: str, subs) -> list:
    """[(features do nosso motor, nota do juiz)] das subs em que as métricas físicas batem com o juiz."""
    eventos = juiz.eventos(ag) if callable(getattr(juiz, "eventos", None)) else ()
    cen = lote.cenario(ag)
    amostras = []
    for i, sub in enumerate(subs):
        r = juiz.teste(ag, sub, detalhe="placar", confirmar=False)
        if not r or not r.get("valido") or r.get("violacoes") or r.get("nota") is None:
            print(f"[pesos] {i}: ignorada (inválida, violação ou sem nota)", file=sys.stderr)
            continue
        nosso = lote.avaliar(ag, sub, eventos)
        if not nosso["valido"] or nosso["violacoes"]:
            print(f"[pesos] {i}: ignorada (nosso motor: inválida ou violação)", file=sys.stderr)
            continue
        mj, mn = r.get("metricas") or {}, nosso["metricas"]
        difs = [k for k in FISICAS if not _bate(mj.get(k), mn.get(k))]
        if difs:
            print(f"[pesos] {i}: ignorada, métricas físicas divergem do juiz em {difs}", file=sys.stderr)
            continue
        amostras.append((features(mn, nosso["sub"], cen.agencia.entrada_existente), float(r["nota"])))
    return amostras


def _gravar_amostras(amostras, path=AMOSTRAS) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([{"features": f, "nota": y} for f, y in amostras], ensure_ascii=False, indent=1),
                    encoding="utf-8")


def _ler_amostras(path=AMOSTRAS) -> list:
    return [(d["features"], d["nota"]) for d in json.loads(Path(path).read_text(encoding="utf-8"))]


def main(argv=None) -> None:
    import argparse

    ap = argparse.ArgumentParser(prog="python -m recarga.pesos")
    ap.add_argument("acao", choices=("coletar", "estimar"))
    ap.add_argument("--amostras", type=Path, default=AMOSTRAS)
    ap.add_argument("--saida", type=Path, default=ESTIMATIVA)
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    if a.acao == "coletar":
        from recarga.juiz import Juiz, carregar_env

        carregar_env()
        subs = experimentos_bangkok()
        amostras = coletar(Juiz(), "Bangkok", subs)
        _gravar_amostras(amostras, a.amostras)
        print(f"{len(amostras)}/{len(subs)} amostras gravadas em {a.amostras}")
    else:
        est = estimar(_ler_amostras(a.amostras))
        salvar(est, a.saida)
        print(json.dumps(para_dict(est), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
