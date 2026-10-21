"""Gera `melhores-resultados.json` na raiz: melhor config por agência nas semanas de teste e situação do final.

  python -m recarga.melhores

1. Sincroniza os kits baixados à mão em `data/<Ag>` (ou `data/<Ag>/<Ag>`) para `kit_kickoff/dados/<Ag>`.
2. Semanas de teste: melhor nota já devolvida pelo juiz (cache em `resultados/juiz/<Ag>`) e as candidatas
   do motor (configs em `configs/<ag>/*.json` + topo do ranking do otimizador), ordenadas pela nota estimada
   com os pesos inferidos de Bangkok (marcada como não confiável quando for o caso).
3. Final (semanas ocultas): envio vigente segundo `resultados/status.json` e `resultados/finais.jsonl`.
Não chama a API.
"""
import json
import shutil
from pathlib import Path

from recarga import DADOS, RAIZ, RESULTADOS, lote, objetivo, pesos

DATA = RAIZ / "data"
SAIDA = RAIZ / "melhores-resultados.json"
TOP_RANKING = 15


def sincronizar() -> list:
    """Copia `data/<Ag>` para `kit_kickoff/dados/<Ag>` quando o kit de lá estiver ausente ou mais velho."""
    agencias = []
    for d in sorted(p for p in DATA.iterdir() if p.is_dir()) if DATA.is_dir() else ():
        origem = d / d.name if (d / d.name / "agencias.md").is_file() else d
        if not (origem / "agencias.md").is_file():
            continue
        destino = DADOS / d.name
        novo = max(f.stat().st_mtime for f in origem.rglob("*") if f.is_file())
        if not (destino / "agencias.md").is_file() or novo > (destino / "agencias.md").stat().st_mtime:
            shutil.rmtree(destino, ignore_errors=True)
            shutil.copytree(origem, destino)
        agencias.append(d.name)
    return agencias


def _envio(sub: dict) -> dict:
    return {k: v for k, v in sub.items() if v is not None}


CONFIRMADOS = RAIZ / "pesos_estimados" / "pesos_bangkok_confirmados.json"


def estimativa():
    """Pesos confirmados (pesos_estimados/pesos_bangkok_confirmados.json) ou, sem eles, inferidos dos testes."""
    if CONFIRMADOS.is_file():
        P = json.loads(CONFIRMADOS.read_text(encoding="utf-8"))
        c = P["custo_obra_em_pontos"]
        p = objetivo.Pesos(w=P["pesos"], k_carregador={k: -v for k, v in c["carregadores"].items()},
                           k_entrada={k: -v for k, v in c["entradas"].items() if k != "existente"})
        return pesos.Estimativa(pesos=p, residuo_rms=0.0, n=0, confiavel=True, nao_identificados=[])
    p = RESULTADOS / "testes-juiz-bangkok.json"
    if not p.is_file():
        return None
    existente = lote.cenario("Bangkok").agencia.entrada_existente
    amostras = []
    for t in json.loads(p.read_text(encoding="utf-8"))["testes"]:
        r = lote.avaliar("Bangkok", _envio(t["sub"]))
        amostras.append((pesos.features(r["metricas"], r["sub"], existente), t["nota_juiz"]))
    return pesos.estimar(amostras) if amostras else None


def _testados_no_juiz(ag: str) -> list:
    pasta = RESULTADOS / "juiz" / ag
    out = []
    for f in sorted(pasta.glob("*.json")) if pasta.is_dir() else ():
        r = json.loads(f.read_text(encoding="utf-8"))
        if isinstance(r, dict) and r.get("nota") is not None:
            out.append({"hash": f.stem.rsplit("_", 1)[0], "nota_juiz": r["nota"], "metricas_juiz": r.get("metricas")})
    return out


def _candidatas(ag: str) -> list:
    subs = []
    for f in sorted((RAIZ / "configs" / ag.lower()).glob("*.json")):
        s = json.loads(f.read_text(encoding="utf-8"))
        for x in s if isinstance(s, list) else [s]:
            subs.append((f"configs/{ag.lower()}/{f.name}", x))
    rk = RESULTADOS / "otimizador" / ag / "ranking.json"
    if rk.is_file():
        for i, r in enumerate(json.loads(rk.read_text(encoding="utf-8"))[:TOP_RANKING]):
            subs.append((f"otimizador#{i + 1}", r.get("envio") or _envio(r["sub"])))
    return subs


def avaliar_agencia(ag: str, est) -> dict:
    cen = lote.cenario(ag)
    existente = cen.agencia.entrada_existente
    juiz = {t["hash"]: t for t in _testados_no_juiz(ag)}
    vistos, linhas = set(), []
    for origem, sub in _candidatas(ag):
        r = lote.avaliar(ag, {**sub, "agencia": ag})
        if not r["valido"] or r["hash"] in vistos:
            continue
        vistos.add(r["hash"])
        m = r["metricas"]
        sem_custo = [] if est is None else (
            [k for k in r["sub"]["carregadores"] if k not in est.pesos.k_carregador]
            + ([r["sub"]["entrada"]] if r["sub"]["entrada"] != existente
               and r["sub"]["entrada"] not in est.pesos.k_entrada else []))
        linhas.append({
            "origem": origem,
            "sub": _envio(r["sub"]),
            "itens_sem_custo_estimado": sem_custo,
            "nota_estimada": round(objetivo.nota(m, r["sub"], existente, est.pesos), 1) if est else None,
            "nota_juiz": juiz.get(r["hash"], {}).get("nota_juiz"),
            "metricas_motor": {k: m[k] for k in ("atendimento_pct", "certos", "upgrades", "nao_atendidos",
                                                 "energia_ponta_kwh", "pico_kw", "demanda_contratada_kw")},
            "perdidos_pior_semana": max(s["nao_atendidos"] for s in r["semanas"]),
        })
    linhas.sort(key=lambda l: (l["nota_juiz"] is None, bool(l["itens_sem_custo_estimado"]),
                               -(l["nota_juiz"] if l["nota_juiz"] is not None
                                                          else (l["nota_estimada"] or float("-inf")))))
    melhor_juiz = max(juiz.values(), key=lambda t: t["nota_juiz"], default=None)
    return {"melhor_testada_no_juiz": melhor_juiz, "candidatas": linhas}


def _final(ag: str, status: dict) -> dict:
    a = (status.get("agencias") or {}).get(ag, {})
    finais = RESULTADOS / "finais.jsonl"
    vig = None
    if finais.is_file():
        for linha in finais.read_text(encoding="utf-8").splitlines():
            l = json.loads(linha)
            if l.get("agencia") == ag:
                vig = l
    return {"liberado": ag != "Bangkok" and bool(a.get("aberta")), "envios": a.get("envios"),
            "vigente": a.get("vigente"), "sub_vigente": (vig or {}).get("sub"), "nota_oculta": None}


def gerar() -> dict:
    agencias = sincronizar()
    est = estimativa()
    st_path = RESULTADOS / "status.json"
    status = json.loads(st_path.read_text(encoding="utf-8")) if st_path.is_file() else {}
    out = {
        "atualizado_por": "python -m recarga.melhores",
        "fase": status.get("fase"),
        "pesos_estimados": None if est is None else {
            "confiavel": est.confiavel, "n_testes": est.n, "residuo_rms": est.residuo_rms,
            "nao_identificados": est.nao_identificados, "w": est.pesos.w,
            "k_carregador": est.pesos.k_carregador, "k_entrada": est.pesos.k_entrada,
            "observacao": "ponta, demanda e ac_7 são exatos; certo × dc_30 confundidos até haver mais testes com perdas",
        },
        "agencias": {},
    }
    for ag in agencias:
        out["agencias"][ag] = {"semanas_teste": avaliar_agencia(ag, est), "final": _final(ag, status)}
    SAIDA.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    o = gerar()
    for ag, a in o["agencias"].items():
        c = a["semanas_teste"]["candidatas"][:1]
        print(ag, "->", c[0]["sub"] if c else None, "| nota juiz", c[0]["nota_juiz"] if c else None,
              "| estimada", c[0]["nota_estimada"] if c else None)
    print(f"escrito {SAIDA}")
