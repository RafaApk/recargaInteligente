"""Dashboard da equipe (regulamento 13.1). Só lê `resultados/`; nunca chama a API.

  streamlit run dashboard/app.py
  RESULTADOS_DIR=PASTA streamlit run dashboard/app.py      # outra pasta de resultados
  python -m dashboard.exemplo PASTA                        # gera dados de exemplo em PASTA
"""
import json
import sys
from datetime import datetime
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
if str(RAIZ_PROJETO) not in sys.path:
    sys.path.insert(0, str(RAIZ_PROJETO))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from recarga import DADOS, RAIZ  # noqa: E402
from kickoff import dados as kit_dados  # noqa: E402
from kickoff import validar  # noqa: E402
from dashboard import dados, graficos  # noqa: E402

try:  # construído em paralelo por outra frente; sem ele o dashboard só mostra o que já está em resultados/
    from recarga import lote
except ImportError:
    lote = None

ATUALIZAR_A_CADA = 60  # segundos
AGENCIAS_PONTUADAS = 6
FONTE_MODELO, FONTE_JUIZ = "Modelo da equipe", "Juiz"

st.set_page_config(page_title="Recarga Inteligente", page_icon=":material/ev_station:", layout="wide")
st.markdown(
    """
    <style>
    .block-container { padding-top: 2.2rem; max-width: 1480px; }
    [data-testid="stMetricValue"] { font-size: 1.65rem; }
    [data-testid="stMetricLabel"] p { font-size: 0.85rem; opacity: 0.75; }
    h1 { padding-bottom: 0.2rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


# --- leitura (com cache de 60 s, igual ao intervalo de atualização) ---------------------------

def _raiz() -> str:
    return str(dados.raiz_padrao())


@st.cache_data(ttl=ATUALIZAR_A_CADA, show_spinner=False)
def ler_global(raiz: str) -> dict:
    r = Path(raiz)
    return {"ledger": dados.ledger(r), "gastos": dados.gasto_por_agencia(r), "placar": dados.placar(r),
            "finais": dados.finais(r), "status": dados.status(r), "pesos": dados.pesos(r),
            "agencias": dados.agencias_conhecidas(r)}


@st.cache_data(ttl=ATUALIZAR_A_CADA, show_spinner=False)
def ler_agencia(raiz: str, ag: str) -> dict:
    r = Path(raiz)
    return {"juiz": dados.respostas_juiz(r, ag), "sim": dados.simulacoes(r, ag), "ranking": dados.ranking(r, ag),
            "demanda": dados.demanda(r, ag)}


@st.cache_data(ttl=ATUALIZAR_A_CADA, show_spinner=False)
def ler_catalogo() -> dict:
    """`GET /catalogo` salvo em kit_kickoff/dados/catalogo.json (a partir de H4)."""
    try:
        return json.loads((DADOS / "catalogo.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}


@st.cache_resource(ttl=300, show_spinner=False)
def cenario(ag: str):
    """Cenário do kit da agência (vagas, horário, carregadores), ou None se o kit não estiver baixado."""
    for pasta in (DADOS, RAIZ):  # Bangkok fica na raiz do repositório
        try:
            return kit_dados.carregar(pasta, ag)
        except (SystemExit, Exception):
            continue
    return None


@st.cache_data(show_spinner="Rodando o motor da equipe...")
def motor_ao_vivo(ag: str, sub_json: str) -> dict:
    return lote.avaliar(ag, json.loads(sub_json), series=True)


# --- derivados --------------------------------------------------------------------------------

def hash_da(sub: dict, ag: str, cen) -> str | None:
    from recarga import chave
    try:
        return chave.chave(validar.normalizar(sub, cen), []) if cen else None
    except Exception:
        return None


def opcoes_submissao(ag: str, glob: dict, loc: dict, cen) -> list:
    """Vigente (de `finais`), candidatas (do `ranking`) e testes avulsos do juiz, sem repetir hash."""
    ops, vistos = [], set()

    def add(rotulo, h, sub, origem):
        h = h or hash_da(sub, ag, cen) or f"{origem}:{len(ops)}"
        if h not in vistos:
            vistos.add(h)
            ops.append({"id": h, "hash": h, "sub": sub, "rotulo": rotulo, "origem": origem})

    vig = dados.vigentes(glob["finais"]).get(ag)
    if vig and isinstance(vig.get("sub"), dict):
        add(f"Vigente · final nº {vig.get('n', '?')}", vig.get("hash"), vig["sub"], "vigente")
    for i, c in enumerate(loc["ranking"], 1):
        if isinstance(c.get("sub"), dict):
            extra = f" · pior semana {dados.fmt(c['pior_semana'], 0)}" if "pior_semana" in c else ""
            add(f"Candidata {i}{extra}", c.get("hash"), c["sub"], "candidata")
    for h in {**loc["juiz"], **loc["sim"]}:
        add(f"Teste avulso · {h[:8]}", h, None, "avulso")
    return ops


def limites_da_agencia(sub: dict | None, cen) -> dict:
    """Limite de potência, saídas, vagas e horário; None/[] quando faltar o kit da agência ou a submissão."""
    vazio = {"limite": None, "saidas": None, "vagas": None, "horario": [], "existente": None}
    if not sub:
        return vazio
    if cen is None:
        return {**vazio, "limite": sub.get("demanda_contratada_kw")}
    try:
        norm = validar.normalizar(sub, cen)
        saidas = sum(n * cen.carregadores[k].saidas for k, n in norm["carregadores"].items())
        return {"limite": validar.limite_kw(norm, cen), "saidas": saidas, "vagas": cen.agencia.vagas,
                "horario": cen.agencia.horario, "existente": cen.agencia.entrada_existente}
    except Exception:
        return {**vazio, "vagas": cen.agencia.vagas, "horario": cen.agencia.horario}


def obra_da_agencia(ag: str, glob: dict, est: dict) -> tuple | None:
    """(pontos de obra, origem) da submissão vigente: juiz > modelo > estimado."""
    vig = dados.vigentes(glob["finais"]).get(ag)
    if not vig:
        return None
    loc = ler_agencia(_raiz(), ag)
    h, sub = vig.get("hash"), vig.get("sub") or {}
    juiz, sim = loc["juiz"].get(h) or {}, loc["sim"].get(h) or {}
    for origem, valores in (("juiz", (vig.get("custo_infra"), juiz.get("custo_infra"),
                                       (juiz.get("metricas") or {}).get("custo_infra"))),
                            ("modelo", (sim.get("custo_infra"), (sim.get("metricas") or {}).get("custo_infra")))):
        for v in valores:
            if dados.total_obra(v) is not None:
                return dados.total_obra(v), origem
    if est.get("custos") and sub:
        cen = cenario(ag)
        return dados.obra_estimada(est, sub, cen.agencia.entrada_existente if cen else None), "estimado"
    return None


# --- componentes ------------------------------------------------------------------------------

def cartao(titulo: str, legenda: str | None = None):
    c = st.container(border=True)
    c.markdown(f"**{titulo}**")
    if legenda:
        c.caption(legenda)
    return c


def mostrar(fig, chave: str, barra: bool = False) -> None:
    st.plotly_chart(fig, key=chave, config={"displayModeBar": "hover" if barra else False, "displaylogo": False})


def tabela_fidelidade(f: dict) -> pd.DataFrame:
    return pd.DataFrame([{"Métrica": ln["metrica"], "Meu": dados.fmt(ln["meu"], 4), "Juiz": dados.fmt(ln["juiz"], 4),
                          "Diferença": dados.fmt(ln["dif"], 4, sinal=True), "Situação": "OK" if ln["ok"] else "Diverge"}
                         for ln in f["linhas"]])


def destacar_divergencias(linha: pd.Series) -> list:
    cor = "background-color: rgba(229, 72, 77, 0.22)" if linha["Situação"] == "Diverge" else ""
    return [cor] * len(linha)


def cabecalho(glob: dict) -> None:
    st.title("Recarga Inteligente")
    s = glob["status"]
    partes = []
    if s.get("fase"):
        etapa = (s.get("etapa") or {}).get("rotulo")
        partes.append(f"Fase {str(s['fase']).capitalize()}" + (f" · {etapa}" if etapa else ""))
    if s.get("equipe"):
        partes.append(f"Equipe #{s['equipe'].get('numero')} {s['equipe'].get('nome', '')}".strip())
    partes.append(f"Atualizado às {datetime.now():%H:%M:%S}")
    st.caption(" · ".join(partes))


# --- página Agência ---------------------------------------------------------------------------

@st.fragment(run_every=ATUALIZAR_A_CADA)
def corpo_agencia(raiz: str, ag: str, op: dict) -> None:
    glob, loc, cen = ler_global(raiz), ler_agencia(raiz, ag), cenario(ag)
    sub, h = op["sub"], op["hash"]
    juiz, sim = loc["juiz"].get(h), loc["sim"].get(h)
    if sim is None and lote is not None and sub:
        try:
            sim = motor_ao_vivo(ag, json.dumps(sub, sort_keys=True))
        except Exception as e:  # o motor é de outra frente; o dashboard não pode cair por causa dele
            st.warning(f"Não foi possível rodar o motor da equipe para esta submissão: {e}")
    lim = limites_da_agencia(sub, cen)

    if sub:
        st.markdown(f"**{dados.rotulo_submissao(sub)}**  \n:gray[hash `{h[:12]}`]")
    if not juiz and not sim:
        st.info("Ainda não há resposta do juiz nem simulação da equipe para esta submissão em `resultados/`."
                + ("" if lote is not None else " O motor ao vivo (`recarga.lote`) não está disponível."))
        return
    if cen is None:
        st.caption("Kit da agência não encontrado em `kit_kickoff/dados/`: limite de potência, vagas e horário "
                   "ficam sem referência.")

    m_meu = (sim or {}).get("metricas") or {}
    m_juiz = (juiz or {}).get("metricas") or {}
    pontos_meu = (sim or {}).get("pontos")
    estimado = False
    if not pontos_meu and m_meu:
        pontos_meu = dados.pontuar_estimado(m_meu, glob["pesos"], sub or {}, lim["existente"])
        estimado = pontos_meu is not None
    pontos_juiz = (juiz or {}).get("pontos")
    nota_juiz = (juiz or {}).get("nota")
    nota_meu = (pontos_meu or {}).get("nota")

    base = {**m_juiz, **{k: v for k, v in m_meu.items() if k not in m_juiz}}
    series_meu = dados.normalizar_series((sim or {}).get("series"))
    series_juiz = dados.normalizar_series((juiz or {}).get("series"))
    nao = base.get("nao_atendidos")
    if nao is None:
        nao = len((series_juiz or series_meu).get("nao_atendidos_min") or []) or None
    obra = next((dados.total_obra(v) for v in ((juiz or {}).get("custo_infra"), m_juiz.get("custo_infra"),
                                              (sim or {}).get("custo_infra"), m_meu.get("custo_infra"))
                 if dados.total_obra(v) is not None), None)
    obra_estimada_ = False
    if obra is None and pontos_meu and estimado:
        obra, obra_estimada_ = -next(i[3] for i in pontos_meu["itens"] if i[0] == "infraestrutura"), True

    k = st.columns(5)
    k[0].metric("Nota do juiz", dados.fmt(nota_juiz, 1), help="Janela pública (semanas 1 a 4).", border=True)
    delta = (dados.fmt(nota_meu - nota_juiz, 1, sinal=True) + " vs juiz") if None not in (nota_meu, nota_juiz) else None
    k[1].metric("Nota estimada" if estimado else "Nota do modelo", dados.fmt(nota_meu, 1), delta,
                delta_color="off", delta_arrow="off", border=True,
                help="Calculada pelo nosso motor." + (" Pesos estimados na Neblina." if estimado else ""))
    atend = base.get("atendimento_pct")
    k[2].metric("Atendimento", "—" if atend is None else f"{dados.fmt(atend, 1)} %",
                None if nao is None else f"{dados.fmt(nao, 0)} não atendidos", delta_color="off", delta_arrow="off",
                border=True)
    pico = base.get("pico_kw")
    k[3].metric("Pico de 15 min", "—" if pico is None else f"{dados.fmt(pico, 1)} kW",
                None if lim["limite"] is None else f"limite {dados.fmt(lim['limite'], 1)} kW",
                delta_color="off", delta_arrow="off", border=True)
    k[4].metric("Custo de obra" + (" (estimado)" if obra_estimada_ else ""),
                "—" if obra is None else f"{dados.fmt(obra, 0)} pts", border=True,
                help="Carregadores instalados mais ampliação de entrada. Sai do juiz a partir de H4.")

    esquerda, direita = st.columns([3, 2])
    with esquerda:
        with cartao("Cascata de pontos", "Pontos ganhos e perdidos por item, no modelo da equipe e no juiz."
                    + (" Modelo com pesos estimados (marcado como estimado até H4)." if estimado else "")):
            if pontos_meu or pontos_juiz:
                mostrar(graficos.cascata((pontos_meu or {}).get("itens") or [], (pontos_juiz or {}).get("itens"),
                                         estimado), "g_cascata")
            else:
                st.info("Sem pontos ainda: o juiz só informa `pontos` na fase Clara e faltam pesos estimados "
                        "(`resultados/pesos/estimativa.json`) para calcular no modelo.")
    fontes = ([FONTE_MODELO] if series_meu else []) + ([FONTE_JUIZ] if series_juiz else [])
    with direita:
        with cartao("SOC na retirada", "Distribuição do nível de bateria na entrega. Meta: 80% ou mais."):
            fonte_soc = (series_meu if FONTE_MODELO in fontes else series_juiz)
            mostrar(graficos.soc_retirada(fonte_soc.get("soc_retirada") or []), "g_soc")

    with cartao("Potência em 15 minutos", "Média por janela contra o limite (kW útil da entrada ou demanda "
                "contratada). Faixas: ponta e agência fechada."):
        c1, c2 = st.columns([1, 2])
        fonte = c1.radio("Fonte das séries", fontes, horizontal=True, key="fonte") if len(fontes) > 1 else (
            fontes[0] if fontes else None)
        semana = c2.radio("Período", ["Todas as semanas", "Semana 1", "Semana 2", "Semana 3", "Semana 4"],
                          horizontal=True, key="semana")
        s = series_meu if fonte == FONTE_MODELO else series_juiz
        n_semana = None if semana.startswith("Todas") else int(semana[-1])
        if s:
            mostrar(graficos.potencia(s, lim["limite"], lim["horario"], n_semana), "g_potencia", barra=True)
        else:
            st.info("Sem séries para esta submissão. Peça ao juiz um teste com `detalhe=completo`.")

    s = (series_meu if fonte == FONTE_MODELO else series_juiz) if fontes else {}
    esq, dir_ = st.columns(2)
    with esq:
        with cartao("Ocupação do pátio", "Máximo de carros plugados e na fila em cada janela, contra as saídas "
                    "dos carregadores e as vagas."):
            mostrar(graficos.ocupacao(s, lim["saidas"], lim["vagas"], n_semana if s else None), "g_ocupacao")
    with dir_:
        with cartao("Clientes perdidos", "Contratos não atendidos por dia da semana e hora (soma das 4 semanas)."):
            mostrar(graficos.perdas(s.get("nao_atendidos_min") or [], s.get("inicio_min", 1080)), "g_perdas")

    with cartao("Fidelidade do motor", "Nosso motor contra a resposta do juiz para a mesma submissão."):
        if sim and juiz:
            f = dados.fidelidade(m_meu, m_juiz, series_meu, series_juiz)
            if not f["disponivel"]:
                st.info("`kit_kickoff/comparar.py` não está disponível.")
            else:
                if f["ok"]:
                    st.success("Bate com o juiz.")
                else:
                    st.warning("Diverge em: " + ", ".join(f["divergencias"]))
                if f["linhas"]:
                    df = tabela_fidelidade(f)
                    st.dataframe(df.style.apply(destacar_divergencias, axis=1), hide_index=True)
                if f["series"]:
                    with st.expander("Séries (janelas de 15 min)"):
                        st.code(f["series"], language=None)
        elif juiz:
            st.info("Falta a simulação da equipe para esta submissão (`resultados/sim/`).")
        else:
            st.info("Falta a resposta do juiz para esta submissão: faça um teste para comparar.")


def pagina_agencia(glob: dict) -> None:
    raiz = _raiz()
    ags = sorted(glob["agencias"], key=lambda a: (a == "Bangkok", a))
    with st.sidebar:
        if not ags:
            st.info("Nenhuma agência com dados em `resultados/`.")
            return
        ag = st.selectbox("Agência", ags, key="agencia")
        loc = ler_agencia(raiz, ag)
        ops = opcoes_submissao(ag, glob, loc, cenario(ag))
        if not ops:
            st.info("Sem submissões para esta agência.")
            return
        if st.session_state.get("submissao") not in {o["id"] for o in ops}:
            st.session_state.pop("submissao", None)
        escolhida = st.selectbox("Submissão", [o["id"] for o in ops], key="submissao",
                                 format_func=lambda i: next(o["rotulo"] for o in ops if o["id"] == i),
                                 help="Vigente: último envio final aceito. Candidatas: ranking do otimizador.")
    corpo_agencia(raiz, ag, next(o for o in ops if o["id"] == escolhida))


# --- página Consolidado -----------------------------------------------------------------------

@st.fragment(run_every=ATUALIZAR_A_CADA)
def corpo_consolidado(raiz: str) -> None:
    glob = ler_global(raiz)
    s, ledger, placar = glob["status"], glob["ledger"], glob["placar"]
    est = glob["pesos"]
    numero = (s.get("equipe") or {}).get("numero")
    vigentes = dados.vigentes(glob["finais"])
    gasto_total = sum(glob["gastos"].values())
    saldo = s.get("saldo")
    if saldo is None:
        saldo = next((ln["saldo"] for ln in reversed(ledger) if isinstance(ln.get("saldo"), (int, float))), None)
    liberadas = len(s.get("agencias") or {}) or len(glob["agencias"])

    nossa = None
    if placar and numero is not None:
        nossa = next((e for e in placar[-1].get("equipes") or [] if e.get("numero") == numero), None)
    k = st.columns(4)
    k[0].metric("Saldo", f"{dados.fmt(saldo, 0)} m7Coins", border=True)
    k[1].metric("Gasto no juiz", f"{dados.fmt(gasto_total, 0)} m7Coins", f"{len(ledger)} chamadas", delta_color="off",
                delta_arrow="off", border=True)
    k[2].metric("Envios finais vigentes", f"{len(vigentes)} de {liberadas}",
                f"meta: {AGENCIAS_PONTUADAS} agências pontuadas", delta_color="off", delta_arrow="off", border=True)
    k[3].metric("Nota no placar", dados.fmt((nossa or {}).get("nota"), 1),
                f"{nossa['posicao']}º lugar" if nossa and nossa.get("posicao") else None, delta_color="off",
                delta_arrow="off", border=True)

    a, b = st.columns([3, 2])
    with a:
        with cartao("m7Coins ao longo do dia", "Taxa cobrada em cada chamada paga (barras) e saldo (linha)."):
            mostrar(graficos.gastos(ledger), "g_gastos")
    with b:
        with cartao("Gasto por agência"):
            if glob["gastos"]:
                chamadas: dict = {}
                for ln in ledger:
                    chamadas[ln.get("agencia") or "-"] = chamadas.get(ln.get("agencia") or "-", 0) + 1
                st.dataframe(pd.DataFrame([{"Agência": ag, "Gasto (m7Coins)": dados.fmt(v, 0),
                                            "Chamadas": chamadas.get(ag, 0)}
                                           for ag, v in sorted(glob["gastos"].items())]), hide_index=True)
            else:
                st.info("Nenhuma chamada registrada no ledger ainda.")
        with cartao("Custo de obra por agência", "Submissão vigente de cada agência."):
            custos = {ag: o for ag in vigentes if (o := obra_da_agencia(ag, glob, est)) is not None}
            mostrar(graficos.obra_por_agencia(custos), "g_obra")

    with cartao("Evolução da nota", "Nota de cada equipe a cada atualização do placar; a nossa em destaque."):
        mostrar(graficos.evolucao(placar, numero), "g_evolucao")

    ags = sorted(glob["agencias"], key=lambda a_: (a_ == "Bangkok", a_))
    with cartao("Escolha de entrada e demanda contratada", "Nota pública em função da demanda varrida pelo "
                "otimizador, com a escolha da submissão vigente em destaque."):
        if ags:
            ag = st.selectbox("Agência", ags, key="agencia_consolidado")
            curva = ler_agencia(raiz, ag)["demanda"]
            sub = (vigentes.get(ag) or {}).get("sub")
            esc = (sub or {}).get("demanda_contratada_kw")
            c1, c2 = st.columns([3, 2])
            with c1:
                mostrar(graficos.curva_demanda(curva, esc), "g_demanda")
            with c2:
                texto = dados.justificativa(sub, curva)
                st.markdown(texto or "Sem submissão vigente ou varredura de demanda para esta agência.")
        else:
            st.info("Sem agências com dados ainda.")

    with cartao("Pesos estimados × reais", "Estimativa da Neblina contra os pesos do catálogo (módulos). "
                "Os reais só saem em H4."):
        reais = None
        if ags:
            ag_p = st.session_state.get("agencia_consolidado", ags[0])
            reais = (ler_catalogo().get("pesos") or {}).get(ag_p)
        mostrar(graficos.pesos_vs_reais(est.get("pesos") or {}, reais), "g_pesos")
        if est:
            st.caption(f"{est.get('n_testes', '?')} testes usados · resíduo RMS {dados.fmt(est.get('residuo_rms'), 2)}.")

    if placar and placar[-1].get("equipes"):
        with cartao("Placar", f"Última atualização: {placar[-1].get('atualizado_em', '—')}"):
            st.dataframe(pd.DataFrame([{"Posição": e.get("posicao"), "Equipe": f"#{e.get('numero')} {e.get('nome', '')}"
                                        + (" (nossa)" if e.get("numero") == numero else ""),
                                        "Nota": dados.fmt(e.get("nota"), 1), "Envios finais": e.get("finais"),
                                        "Saldo": e.get("saldo")} for e in placar[-1]["equipes"]]), hide_index=True)


def pagina_consolidado() -> None:
    corpo_consolidado(_raiz())


# --- aplicação --------------------------------------------------------------------------------

def principal() -> None:
    glob = ler_global(_raiz())
    with st.sidebar:
        st.markdown("### Recarga Inteligente")
        pagina = st.radio("Página", ["Agência", "Consolidado"], key="pagina")
        st.divider()
    cabecalho(glob)
    if pagina == "Agência":
        pagina_agencia(glob)
    else:
        pagina_consolidado()
    with st.sidebar:
        st.divider()
        if lote is None:
            st.info("Motor ao vivo (`recarga.lote`) indisponível: mostrando só os dados já salvos em `resultados/`.")
        st.caption(f"Dados: `{_raiz()}`  \nAtualiza a cada {ATUALIZAR_A_CADA} s.")
        if st.button("Atualizar agora", icon=":material/refresh:"):
            st.cache_data.clear()
            st.rerun()
    if not glob["agencias"] and not glob["ledger"] and not glob["placar"]:
        st.info(f"Nenhum resultado em `{_raiz()}` ainda. Para ver o painel com dados de exemplo: "
                f"`python -m dashboard.exemplo PASTA` e `RESULTADOS_DIR=PASTA streamlit run dashboard/app.py`.")


principal()
