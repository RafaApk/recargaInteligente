"""Gera os dados do dashboard (dashboard_localiza/public/data/*.json) com o motor local e o placar.

  python gerar_dados_dashboard.py [--saida DIR] [--finais ARQ.jsonl] [--ledger ARQ.jsonl] [--repo DIR] [--offline]

Precisa de dados/<Agencia>/ de cada agência e de dados/catalogo.json. Sem --offline, lê GET /placar
(GAMEDAY_URL e GAMEDAY_TOKEN). Os envios vigentes vêm de finais.jsonl do repositório da equipe.
Notas do placar são das semanas ocultas; todo o resto é simulado no motor nas 4 semanas públicas.
"""
import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

import simular  # noqa: E402
from kickoff import api, dados, medicao, motor, tempo, validar  # noqa: E402

ORDEM = ["Istanbul", "Hanoi", "Marrakech", "Zurich", "Vienna"]
ORDEM_PLACAR = ORDEM + ["Lisbon"]  # Lisbon: agência nova, ainda sem envio da equipe
DIAS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
EQUIPE = 14
JUSTIFICATIVA = {
    "Istanbul": "Três DC-30 e um AC-7 nas quatro vagas. O evento tira os dois maiores carregadores, e com carregadores de tamanho parecido ainda sobra capacidade. A fila segue a próxima reserva.",
    "Hanoi": "Seis saídas para seis vagas, com AC-7 e um DC-30. A próxima reserva decide quem carrega primeiro e a ponta fica liberada.",
    "Marrakech": "Entrada A4 com demanda contratada para dar folga ao corte da concessionária. A agência fecha às 18h, então evitar a ponta custa pouco.",
    "Zurich": "Poucas vagas e carga rápida em uma delas. A versão conservadora reduz o risco de perder clientes nas semanas ocultas, onde a anterior caiu muito.",
    "Vienna": "Agência grande (30 vagas) e A4 já existente, sem obra de entrada. Poucos AC-7 bastam e a demanda contratada fica baixa.",
}


def ler_jsonl(texto: str) -> list:
    return [json.loads(l) for l in texto.splitlines() if l.strip()]


def git_show(repo: Path, caminho: str) -> str:
    for ref in ("origin/design/recarga-inteligente", "HEAD"):
        r = subprocess.run(["git", "-C", str(repo), "show", f"{ref}:{caminho}"], capture_output=True, text=True, encoding="utf-8")
        if r.returncode == 0:
            return r.stdout
    return ""


def main() -> None:
    ap = argparse.ArgumentParser()
    pasta = AQUI / "dashboard_localiza" if (AQUI / "dashboard_localiza").exists() else AQUI.parent / "dashboard_localiza"
    ap.add_argument("--saida", type=Path, default=pasta / "public" / "data")
    ap.add_argument("--repo", type=Path, default=AQUI.parent if (AQUI.parent / ".git").exists() else AQUI.parent / "recargaInteligente")
    ap.add_argument("--finais", type=Path)
    ap.add_argument("--ledger", type=Path)
    ap.add_argument("--eventos", type=Path, default=AQUI / "eventos.json")
    ap.add_argument("--offline", action="store_true", help="não chama a API (usa o placar já salvo em --saida)")
    a = ap.parse_args()
    out = a.saida
    out.mkdir(parents=True, exist_ok=True)

    cat = json.loads((AQUI / "dados" / "catalogo.json").read_text(encoding="utf-8"))
    ev = simular.ler_eventos(str(a.eventos)) if a.eventos.exists() else []
    finais_txt = a.finais.read_text(encoding="utf-8") if a.finais else git_show(a.repo, "resultados/finais.jsonl")
    ledger_txt = a.ledger.read_text(encoding="utf-8") if a.ledger else git_show(a.repo, "resultados/ledger.jsonl")
    finais = {d["agencia"]: d for d in ler_jsonl(finais_txt)}
    faltam = [ag for ag in ORDEM if ag not in finais]
    if faltam:
        raise SystemExit(f"sem envio final registrado para {faltam}; passe --finais com o finais.jsonl da equipe")

    # placar (semanas ocultas)
    if a.offline:
        placar_json = json.loads((out / "placar.json").read_text(encoding="utf-8"))
        linhas, atualizado = placar_json["equipes"], placar_json.get("atualizado_em")
    else:
        p = api.Cliente()._json("GET", "/placar")
        atualizado = p.get("atualizado_em")
        linhas = []
        for e in p["equipes"]:
            ag = e.get("agencias", {})
            linhas.append({"posicao": e["posicao"], "numero": e["numero"], "equipe": e["nome"], "nota": round(e["nota"], 2),
                           **{x: (round(ag[x], 2) if ag.get(x) is not None else None) for x in ORDEM_PLACAR},
                           "finais": e["finais"], "saldo": e["saldo"], "nao_atendidos": e.get("nao_atendidos"),
                           "custo_obra": e.get("custo_infra")})
    nossa = next(l for l in linhas if l["numero"] == EQUIPE)

    envios, cascata, serie, soc, perd = [], [], [], [], []
    for ag in ORDEM:
        sub = {k: v for k, v in finais[ag]["sub"].items() if not (k == "demanda_contratada_kw" and v is None)}
        cen = dados.carregar(AQUI / "dados", ag, cat)
        r = simular.avaliar(sub, {ag: cen}, AQUI / "dados", cat, ev, False)
        s = validar.normalizar(sub, cen)
        res = motor.simular(cen, s, [e for e in ev if len(e) > 1 and e[1] == ag])
        ini, fim = tempo.JANELA_PUBLICA
        ser = medicao.series(res.bins, res.trace, res.retiradas, res.nao_atendidos, ini, fim)
        base = validar.limite_kw(s, cen)
        pol = s["politica"]
        saidas = sum(cen.carregadores[k].saidas * n for k, n in s["carregadores"].items())
        envios.append({
            "agencia": ag, "carregadores": " + ".join(f"{n}× {k}" for k, n in s["carregadores"].items()),
            "entrada": s["entrada"], "demanda_kw": s["demanda_contratada_kw"] or 0, "prioridade": pol["prioridade"],
            "divisao": pol["divisao"], "evitar_ponta": bool(pol["evitar_ponta"]), "vagas": cen.agencia.vagas, "saidas": saidas,
            "obra": r["custo_infra"]["total"], "limite_kw": base, "contratos": r["metricas"]["contratos"],
            "atendimento_pct": round(r["metricas"]["atendimento_pct"], 2), "nota_publica_motor": round(r["nota"], 1),
            "nota_oculta_placar": nossa.get(ag), "perdidos_publicos": r["metricas"]["nao_atendidos"],
            "justificativa": JUSTIFICATIVA[ag],
        })
        for i, (item, qtd, peso, pts) in enumerate(r["pontos"]["itens"]):
            cascata.append({"agencia": ag, "ordem": i, "item": item, "qtd": round(qtd, 1), "peso": peso, "pontos": round(pts, 1)})
        for k in range(len(ser["potencia_kw"])):
            t = ini + 15 * k
            lim = base * 0.7 if any(e[0] == "corte" and e[1] == ag and e[2] <= t < e[3] for e in ev) else base
            serie.append({"agencia": ag, "idx": k, "hora": tempo.texto(t), "potencia_kw": round(ser["potencia_kw"][k], 2),
                          "plugados": ser["plugados_max"][k], "fila": ser["fila_max"][k], "limite_kw": round(lim, 1),
                          "ponta": 1 if tempo.eh_ponta(t) else 0})
        for x in res.retiradas:
            soc.append({"agencia": ag, "soc": round(x.soc, 1), "upgrade": 1 if x.rank_entregue > x.rank_pedido else 0})
        c = Counter((tempo.dia_semana(t), int((t % 1440) // 60)) for t in res.nao_atendidos if ini <= t < fim)
        for (d, h), n in sorted(c.items()):
            perd.append({"agencia": ag, "dia": DIAS[d], "dia_idx": d, "hora": h, "perdidos": n})
        print(f"{ag:10s} motor {r['nota']:9.1f}  perdidos {r['metricas']['nao_atendidos']:3d}  obra {r['custo_infra']['total']:6.0f}", flush=True)

    ini_j, fim_j = tempo.JANELA_PUBLICA
    idx = lambda m: max(0, min(int((fim_j - ini_j) // 15), int((m - ini_j) // 15)))
    eventos = []
    for e in ev:
        if e[0] == "quebra_maiores":
            _, ag_, n, i0, i1 = e
            desc = f"{n} maiores carregadores fora de operação"
        elif e[0] == "corte":
            _, ag_, i0, i1, f = e
            desc = f"limite da agência reduzido para {int(round(f * 100))}% (suposição do motor)"
        else:
            continue
        eventos.append({"agencia": ag_, "tipo": e[0], "descricao": desc, "inicio_idx": idx(i0), "fim_idx": idx(i1),
                        "inicio_texto": tempo.texto(i0), "fim_texto": tempo.texto(i1)})

    # envios candidatos (envios/<Agencia>_candidata.json), simulados com os mesmos eventos
    refino = {}
    arq_refino = AQUI / "busca" / "Istanbul_evento_refino.json"
    if arq_refino.exists():
        for r_ in json.loads(arq_refino.read_text(encoding="utf-8")):
            refino[json.dumps(r_["submissao"], sort_keys=True)] = r_
    candidatas = []
    for arq in sorted((AQUI / "envios").glob("*_candidata.json")):
        sub = json.loads(arq.read_text(encoding="utf-8"))
        ag = sub["agencia"]
        if ag not in finais:
            continue
        cen = dados.carregar(AQUI / "dados", ag, cat)
        evs = [e for e in ev if len(e) > 1 and e[1] == ag]
        ra = simular.avaliar({k: v for k, v in finais[ag]["sub"].items() if not (k == "demanda_contratada_kw" and v is None)},
                             {ag: cen}, AQUI / "dados", cat, ev, False)
        rc = simular.avaliar(sub, {ag: cen}, AQUI / "dados", cat, ev, False)
        sn = validar.normalizar(sub, cen)
        vig = validar.normalizar({k: v for k, v in finais[ag]["sub"].items() if not (k == "demanda_contratada_kw" and v is None)}, cen)
        if sn == vig:
            continue  # já é o envio vigente
        n_env = finais[ag].get("n") or 1
        extra = refino.get(json.dumps(sub, sort_keys=True), {})
        candidatas.append({
            "agencia": ag,
            "carregadores": " + ".join(f"{n}× {k}" for k, n in sn["carregadores"].items()),
            "entrada": sn["entrada"], "demanda_kw": sn["demanda_contratada_kw"] or 0,
            "evitar_ponta": bool(sn["politica"]["evitar_ponta"]),
            "obra": rc["custo_infra"]["total"], "obra_atual": ra["custo_infra"]["total"],
            "nota_motor_atual": round(ra["nota"], 1), "nota_motor_candidata": round(rc["nota"], 1),
            "nota_placar_atual": nossa.get(ag),
            "media_8_momentos": round(extra["plugado"], 0) if extra.get("plugado") is not None else None,
            "pior_8_momentos": round(extra["pior"], 0) if extra.get("pior") is not None else None,
            "custo_reenvio": 80 * 2 ** (n_env - 1), "cabe_no_saldo": nossa["saldo"] >= 80 * 2 ** (n_env - 1),
            "tem_evento": bool(evs),
        })

    gastos = [{"hora_utc": d["t"][11:16], "rota": d["rota"], "agencia": d["agencia"], "taxa": d["taxa"], "saldo": d["saldo"]}
              for d in ler_jsonl(ledger_txt)]
    for d in finais.values():
        if d.get("taxa"):
            gastos.append({"hora_utc": d["t"][11:16], "rota": "final", "agencia": d["agencia"], "taxa": d["taxa"], "saldo": None})
    gastos.sort(key=lambda g: g["hora_utc"])

    evolucao_arq = out / "evolucao.json"
    evol = json.loads(evolucao_arq.read_text(encoding="utf-8")) if evolucao_arq.exists() else []
    hora = (atualizado or "")[11:16]
    if hora and (not evol or evol[-1]["hora_utc"] != hora):
        evol.append({"hora_utc": hora, "nota": nossa["nota"], "fonte": "GET /placar"})

    meta = {"gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"), "placar_atualizado_em": atualizado,
            "equipe": EQUIPE, "saldo_inicial": 1000, "saldo_atual": nossa["saldo"],
            "pendentes": [x for x in ORDEM_PLACAR if nossa.get(x) is None]}
    for nome, d in (("placar", {"atualizado_em": atualizado, "equipes": linhas}), ("envios", envios), ("cascata", cascata),
                    ("serie15", serie), ("soc_retirada", soc), ("perdidos", perd), ("gastos", gastos),
                    ("evolucao", evol), ("eventos", eventos), ("candidatas", candidatas), ("meta", meta)):
        (out / f"{nome}.json").write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("dados gravados em", out)


if __name__ == "__main__":
    main()
