"""Matriz de fidelidade: 24 submissões de Bangkok (teste grátis) comparadas com o nosso motor.

  python -m recarga.fidelidade

Cada submissão é enviada ao juiz com `detalhe="completo"` e a resposta é comparada (métricas e
séries) com `simular.avaliar`. Meta: 24/24 OK. Divergências viram issues para a Frente A.
"""
import contextlib
import io
import itertools
import json
import sys

from recarga import DADOS, RESULTADOS
from recarga.juiz import Juiz, carregar_env

import comparar
import simular
from kickoff import validar

AGENCIA = "Bangkok"
CARREGADORES = {"dc_60x2": 1, "ac_22x2": 1, "ac_7": 2}  # 6 saídas = as 6 vagas de Bangkok
LIMITES = (("b3_45", None), ("a4_150", 130))


def matriz() -> list:
    """As 24 submissões: 3 prioridades x 2 divisões x 2 evitar_ponta x 2 limites de entrada."""
    subs = []
    for prioridade, divisao, evitar_ponta, (entrada, demanda) in itertools.product(
            validar.MENU["prioridade"], validar.MENU["divisao"], validar.MENU["evitar_ponta"], LIMITES):
        sub = {"agencia": AGENCIA, "carregadores": dict(CARREGADORES), "entrada": entrada,
               "politica": {"prioridade": prioridade, "evitar_ponta": evitar_ponta, "divisao": divisao}}
        if demanda is not None:
            sub["demanda_contratada_kw"] = demanda
        subs.append(sub)
    return subs


def rotulo(sub: dict) -> str:
    p = sub["politica"]
    lim = sub["entrada"] + (f"/{sub['demanda_contratada_kw']}kW" if "demanda_contratada_kw" in sub else "")
    return f"{p['prioridade']:<16}{p['divisao']:<11}{'ponta' if p['evitar_ponta'] else 'livre':<6}{lim}"


def _catalogo():
    p = DADOS / "catalogo.json"
    return json.loads(p.read_text(encoding="utf-8-sig")) if p.exists() else None


def _comparar(sub: dict, resp: dict, cenarios: dict, cat, eventos: list):
    """Devolve (divergências, relatório impresso por `comparar`)."""
    out = simular.avaliar(sub, cenarios, DADOS, cat, eventos, True)
    if not out["valido"]:
        return ["invalido: " + "; ".join(out["erros"])], ""
    if resp.get("valido") is False:
        return ["juiz.invalido"], "juiz recusou a submissão: " + "; ".join(map(str, resp.get("erros") or []))
    diverge: list = []
    if not resp.get("metricas"):
        diverge.append("juiz.sem_metricas")
    if not resp.get("series"):
        diverge.append("juiz.sem_series")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        comparar.comparar_metricas(out["metricas"], resp.get("metricas") or {}, diverge)
        series = resp.get("series")
        if series:
            if "potencia_kw" not in series and "publico" in series:
                series = series["publico"]
            comparar.comparar_series(out["series"]["publico"], series, diverge)
    if bool(out["violacoes"]) != bool(resp.get("violacoes")):
        diverge.append("violacoes")
    return diverge, buf.getvalue()


def rodar(juiz, subs=None, ao_terminar=None) -> list:
    """Testa cada submissão no juiz e compara com o nosso motor.

    `ao_terminar(i, n, resultado)` (opcional) é chamado após cada uma, para mostrar progresso.
    """
    subs = matriz() if subs is None else subs
    cat, cenarios, resultados = _catalogo(), {}, []
    for i, sub in enumerate(subs, 1):
        try:
            resp = juiz.teste(sub.get("agencia", AGENCIA), sub, detalhe="completo")
            diverge, relatorio = _comparar(sub, resp, cenarios, cat, juiz.eventos(sub.get("agencia", AGENCIA)))
        except Exception as e:  # um erro numa rodada não derruba as outras
            diverge, relatorio = [f"erro: {type(e).__name__}: {e}"], ""
        r = {"sub": sub, "ok": not diverge, "diverge": diverge, "relatorio": relatorio}
        resultados.append(r)
        if ao_terminar:
            ao_terminar(i, len(subs), r)
    return resultados


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    carregar_env()
    juiz = Juiz()
    print(f"{'#':>3}  {'prioridade':<16}{'divisão':<11}{'ponta':<6}{'limite':<14}resultado")

    def linha(i, n, r):
        estado = "OK" if r["ok"] else "DIVERGE em " + ", ".join(r["diverge"])
        print(f"{i:>3}  {rotulo(r['sub'])}  {estado}", flush=True)

    resultados = rodar(juiz, ao_terminar=linha)
    RESULTADOS.mkdir(parents=True, exist_ok=True)
    (RESULTADOS / "fidelidade.json").write_text(json.dumps(resultados, ensure_ascii=False, indent=1),
                                                encoding="utf-8")
    for r in resultados:
        if not r["ok"]:
            print(f"\n--- {rotulo(r['sub'])}\n{r['relatorio']}")
    print(f"\n{sum(r['ok'] for r in resultados)}/{len(resultados)} OK")


if __name__ == "__main__":
    main()
