"""Gráficos Plotly do dashboard. Cada função devolve uma `go.Figure` e aceita dados vazios.

Fundo transparente e cores de traço explícitas: as figuras ficam legíveis nos temas claro e escuro do
Streamlit (que aplica a cor do texto e da grade do tema). Rótulos em português.
"""
from datetime import datetime, timedelta

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from recarga import RAIZ  # noqa: F401  (garante `kickoff` no sys.path)
from kickoff import tempo

from .dados import ALIAS_PESOS, ITENS, ROTULOS, hora
from .dados import fmt as _n

COR = {
    "principal": "#2A9D8F",   # verde-azulado: operação normal, nosso modelo
    "azul": "#4C7BE0",        # totais, comparação
    "alerta": "#E5484D",      # limite, perdas, descontos
    "ponta": "#F2A33A",       # horário de ponta
    "neutra": "#8A94A6",      # grade, horário fechado, referências
    "roxo": "#8E6BD8",
}
PALETA = [COR["principal"], COR["azul"], COR["ponta"], COR["roxo"], COR["alerta"], COR["neutra"]]
GRADE = "rgba(128,128,128,0.18)"
DIAS_CURTOS = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")


def rgba(cor: str, alfa: float) -> str:
    h = cor.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{alfa})"


def _dt(t) -> datetime:
    return tempo.EPOCA + timedelta(minutes=float(t))


def _novo(altura: int = 340) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        height=altura,
        margin=dict(l=8, r=8, t=28, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0, bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(font_size=12),
    )
    fig.update_xaxes(gridcolor=GRADE, zeroline=False, linecolor=GRADE)
    fig.update_yaxes(gridcolor=GRADE, zeroline=False, linecolor=GRADE)
    return fig


def _vazio(fig: go.Figure, msg: str = "Sem dados ainda") -> go.Figure:
    fig.add_annotation(text=msg, xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
                       font=dict(size=14, color=COR["neutra"]))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def _linha_h(fig, y, cor, dash, texto=None, nome=None):
    fig.add_shape(type="line", xref="paper", x0=0, x1=1, yref="y", y0=y, y1=y,
                  line=dict(color=cor, width=2, dash=dash), name=nome)
    if texto:
        fig.add_annotation(xref="paper", x=0, xanchor="left", yref="y", y=y, yanchor="bottom", text=texto,
                           showarrow=False, font=dict(size=11, color=cor))


def _legenda(fig, nome, cor, simbolo="square", dash=None):
    """Entrada de legenda para formas (retângulos/linhas), que não aparecem na legenda sozinhas."""
    if dash:
        fig.add_trace(go.Scatter(x=[None], y=[None], mode="lines", name=nome, hoverinfo="skip",
                                 line=dict(color=cor, width=2, dash=dash)))
    else:
        fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", name=nome, hoverinfo="skip",
                                 marker=dict(symbol=simbolo, size=11, color=cor)))


# --- cascata ---------------------------------------------------------------------------------

def _trace_cascata(itens: list, nome: str, opacidade: float) -> go.Waterfall:
    pontos = [float(i[3]) for i in itens]
    total = sum(pontos)
    hover = [f"{ROTULOS.get(i[0], i[0])}<br>{_n(i[1], 1 if isinstance(i[1], float) else 0)} × {_n(i[2], 2)} = "
             f"{_n(float(i[3]), 1, sinal=True)} pontos" for i in itens] + [f"Nota: {_n(total, 1)}"]
    # A barra de total ignora o `y` (usa a soma acumulada); 0 mantém sum(y) == soma dos pontos.
    return go.Waterfall(
        name=nome, orientation="v", opacity=opacidade,
        measure=["relative"] * len(itens) + ["total"],
        x=[ROTULOS.get(i[0], i[0]) for i in itens] + ["Nota"],
        y=pontos + [0.0],
        text=[_n(p, 0, sinal=True) for p in pontos] + [_n(total, 0)], textposition="outside",
        hovertext=hover, hoverinfo="text", cliponaxis=False,
        increasing=dict(marker=dict(color=COR["principal"])),
        decreasing=dict(marker=dict(color=COR["alerta"])),
        totals=dict(marker=dict(color=COR["azul"])),
        connector=dict(line=dict(color=COR["neutra"], width=1, dash="dot")))


def cascata(itens_meu: list, itens_juiz: list | None, estimado: bool = False) -> go.Figure:
    """Cascata de pontos ganhos e perdidos (`pontos.itens`: [item, qtd, peso, pontos]).

    `estimado=True` marca o modelo da equipe como calculado com pesos estimados (antes de H4).
    """
    fig = _novo(380)
    if not itens_meu and not itens_juiz:
        return _vazio(fig)
    duas = bool(itens_meu) and bool(itens_juiz)
    if itens_meu:
        fig.add_trace(_trace_cascata(itens_meu, "Modelo da equipe (estimado)" if estimado else "Modelo da equipe", 1.0))
    if itens_juiz:
        fig.add_trace(_trace_cascata(itens_juiz, "Juiz", 0.55 if duas else 1.0))
    fig.update_layout(waterfallmode="group", waterfallgap=0.25, showlegend=duas or estimado,
                      margin=dict(l=8, r=8, t=36, b=8))
    if estimado:
        fig.add_annotation(text="ESTIMADO: pesos estimados na Neblina", xref="paper", yref="paper", x=1, y=1.02,
                           xanchor="right", yanchor="bottom", showarrow=False,
                           font=dict(size=11, color=COR["ponta"]))
    fig.update_yaxes(title_text="Pontos")
    return fig


# --- potência e ocupação ---------------------------------------------------------------------

def _intervalos_fechados(horario: list, ini: float, fim: float) -> list:
    """Intervalos [a, b) em minutos em que a agência está fechada, já unidos entre dias seguidos."""
    if len(horario) != 7:
        return []
    brutos = []
    for d in range(int(ini // tempo.DIA), int(fim // tempo.DIA) + 1):
        base = d * tempo.DIA
        j = horario[tempo.dia_semana(base)]
        if j is None:
            brutos.append((base, base + tempo.DIA))
        else:
            if j[0] > 0:
                brutos.append((base, base + j[0]))
            if j[1] < tempo.DIA:
                brutos.append((base + j[1], base + tempo.DIA))
    unidos = []
    for a, b in brutos:
        a, b = max(a, ini), min(b, fim)
        if b <= a:
            continue
        if unidos and a <= unidos[-1][1]:
            unidos[-1][1] = max(unidos[-1][1], b)
        else:
            unidos.append([a, b])
    return unidos


def _intervalos_ponta(ini: float, fim: float) -> list:
    saida = []
    for d in range(int(ini // tempo.DIA), int(fim // tempo.DIA) + 1):
        base = d * tempo.DIA
        if tempo.dia_semana(base) >= 5:
            continue
        a, b = max(base + tempo.PONTA[0], ini), min(base + tempo.PONTA[1], fim)
        if b > a:
            saida.append((a, b))
    return saida


def _faixa(fig, a, b, cor, alfa, nome):
    fig.add_shape(type="rect", xref="x", x0=_dt(a), x1=_dt(b), yref="y domain", y0=0, y1=1,
                  fillcolor=rgba(cor, alfa), line_width=0, layer="below", name=nome)


def _eixo_tempo(fig, ini: float, n: int, passo: int, semana: int | None):
    fig.update_xaxes(type="date", tickformat="%d/%m", hoverformat="%d/%m %H:%M")
    if semana:
        a = ini + (semana - 1) * 7 * tempo.DIA
        fig.update_xaxes(range=[_dt(a), _dt(min(a + 7 * tempo.DIA, ini + n * passo))])


def potencia(series: dict, limite_kw: float | None, horario: list, semana: int | None = None) -> go.Figure:
    """Potência média em janelas de 15 min contra o limite, com ponta e horário fechado sombreados."""
    fig = _novo(380)
    pot = series.get("potencia_kw") or []
    if not pot:
        return _vazio(fig)
    ini, passo = series.get("inicio_min", tempo.T0), series.get("passo_min", 15)
    fim = ini + passo * len(pot)
    for a, b in _intervalos_fechados(horario, ini, fim):
        _faixa(fig, a, b, COR["neutra"], 0.16, "fechado")
    for a, b in _intervalos_ponta(ini, fim):
        _faixa(fig, a, b, COR["ponta"], 0.22, "ponta")
    ts = [ini + passo * k for k in range(len(pot))]
    fig.add_trace(go.Scatter(
        x=[_dt(t) for t in ts], y=pot, mode="lines", name="Potência (média em 15 min)",
        line=dict(color=COR["principal"], width=1.5, shape="hv"), fill="tozeroy",
        fillcolor=rgba(COR["principal"], 0.22),
        hovertext=[tempo.texto(t) for t in ts], hovertemplate="%{hovertext}<br>%{y:.1f} kW<extra></extra>"))
    topo = max(max(pot), limite_kw or 0)
    if limite_kw:
        _linha_h(fig, limite_kw, COR["alerta"], "dash", f"Limite {_n(limite_kw, 1)} kW", "limite")
        _legenda(fig, "Limite (entrada ou demanda)", COR["alerta"], dash="dash")
    _legenda(fig, "Ponta (seg–sex, 18h–21h)", rgba(COR["ponta"], 0.7))
    _legenda(fig, "Agência fechada", rgba(COR["neutra"], 0.6))
    fig.update_yaxes(title_text="kW", range=[0, (topo or 1) * 1.12])
    _eixo_tempo(fig, ini, len(pot), passo, semana)
    return fig


def ocupacao(series: dict, saidas: int | None, vagas: int | None, semana: int | None = None) -> go.Figure:
    """Carros plugados e fila (máximo em cada janela de 15 min) contra saídas e vagas."""
    fig = _novo(320)
    plug, fila = series.get("plugados_max") or [], series.get("fila_max") or []
    if not plug and not fila:
        return _vazio(fig)
    n = max(len(plug), len(fila))
    ini, passo = series.get("inicio_min", tempo.T0), series.get("passo_min", 15)
    ts = [ini + passo * k for k in range(n)]
    x = [_dt(t) for t in ts]
    texto = [tempo.texto(t) for t in ts]
    for nome, ys, cor in (("Plugados", plug, COR["principal"]), ("Na fila", fila, COR["ponta"])):
        fig.add_trace(go.Scatter(
            x=x[:len(ys)], y=ys, mode="lines", name=nome, stackgroup="ocupacao",
            line=dict(color=cor, width=1, shape="hv"), fillcolor=rgba(cor, 0.45),
            hovertext=texto[:len(ys)], hovertemplate="%{hovertext}<br>" + nome + ": %{y}<extra></extra>"))
    topo = max(vagas or 0, saidas or 0, max((a + b for a, b in zip(plug, fila)), default=0))
    if saidas and saidas == vagas:
        _linha_h(fig, vagas, COR["alerta"], "dash", f"Saídas dos carregadores = vagas do pátio ({vagas})")
    else:
        if saidas:
            _linha_h(fig, saidas, COR["azul"], "dot", f"Saídas dos carregadores ({saidas})")
        if vagas:
            _linha_h(fig, vagas, COR["alerta"], "dash", f"Vagas do pátio ({vagas})")
    fig.update_yaxes(title_text="Carros", range=[0, (topo or 1) * 1.2], dtick=1 if topo <= 12 else None)
    _eixo_tempo(fig, ini, n, passo, semana)
    return fig


# --- SOC e perdas ----------------------------------------------------------------------------

def soc_retirada(soc: list) -> go.Figure:
    """Histograma do SOC na retirada, com marca na meta de 80%."""
    fig = _novo(320)
    if not soc:
        return _vazio(fig)
    inicio = min(70.0, (min(soc) // 2) * 2)
    bins = dict(start=inicio, end=102, size=2)
    abaixo = [s for s in soc if s < 80]
    resto = [s for s in soc if s >= 80]
    fig.add_trace(go.Histogram(x=resto, xbins=bins, name="80% ou mais", marker_color=COR["principal"],
                               hovertemplate="SOC %{x}%<br>%{y} retiradas<extra></extra>"))
    fig.add_trace(go.Histogram(x=abaixo, xbins=bins, name="Abaixo de 80%", marker_color=COR["alerta"],
                               hovertemplate="SOC %{x}%<br>%{y} retiradas<extra></extra>"))
    fig.add_shape(type="line", xref="x", x0=80, x1=80, yref="y domain", y0=0, y1=1,
                  line=dict(color=COR["alerta"], width=2, dash="dash"), name="meta")
    fig.add_annotation(xref="x", x=80, yref="y domain", y=1, text="Meta 80%", showarrow=False, xanchor="right",
                       yanchor="top", xshift=-4, font=dict(size=11, color=COR["alerta"]))
    fig.update_layout(barmode="overlay", bargap=0.06)
    fig.update_traces(opacity=0.9, selector=dict(type="histogram"))
    fig.update_xaxes(title_text="SOC na retirada (%)", range=[inicio, 102])
    fig.update_yaxes(title_text="Retiradas")
    return fig


def matriz_perdas(nao_atendidos_min: list, inicio_min: float) -> list:
    """Contagem de clientes perdidos em 7 dias da semana (seg=0) × 24 horas."""
    z = [[0] * 24 for _ in range(7)]
    for v in nao_atendidos_min or []:
        t = inicio_min + v
        z[tempo.dia_semana(t)][int((t % tempo.DIA) // 60)] += 1
    return z


def perdas(nao_atendidos_min: list, inicio_min: float) -> go.Figure:
    """Mapa de calor de clientes não atendidos por dia da semana e hora."""
    z = matriz_perdas(nao_atendidos_min, inicio_min)
    fig = _novo(320)
    fig.add_trace(go.Heatmap(
        z=z, x=list(range(24)), y=list(DIAS_CURTOS), xgap=2, ygap=2, zmin=0,
        text=[["" if v == 0 else str(v) for v in linha] for linha in z], texttemplate="%{text}",
        textfont=dict(size=11),
        colorscale=[[0, rgba(COR["alerta"], 0.07)], [1, rgba(COR["alerta"], 1.0)]],
        colorbar=dict(title="Perdas", thickness=10, len=0.9),
        hovertemplate="%{y}, %{x}h<br>%{z} clientes perdidos<extra></extra>"))
    fig.update_xaxes(tickmode="array", tickvals=list(range(0, 24, 2)),
                     ticktext=[f"{h:02d}h" for h in range(0, 24, 2)], showgrid=False, side="bottom")
    fig.update_yaxes(autorange="reversed", showgrid=False)
    if not nao_atendidos_min:
        fig.add_annotation(text="Nenhum cliente perdido", xref="paper", yref="paper", x=0.5, y=0.5,
                           showarrow=False, font=dict(size=14, color=COR["neutra"]))
    return fig


# --- consolidado -----------------------------------------------------------------------------

def _num(v):
    return None if isinstance(v, bool) or not isinstance(v, (int, float)) else v


def gastos(ledger: list) -> go.Figure:
    """m7Coins cobrados por chamada (barras empilhadas por agência) e saldo ao longo do dia."""
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.update_layout(height=340, margin=dict(l=8, r=8, t=28, b=8), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", barmode="stack",
                      legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0,
                                  bgcolor="rgba(0,0,0,0)"))
    fig.update_xaxes(gridcolor=GRADE, zeroline=False)
    fig.update_yaxes(gridcolor=GRADE, zeroline=False)
    linhas = [ln for ln in ledger or [] if isinstance(ln, dict)]
    if not linhas:
        return _vazio(fig)
    horas = [hora(ln) for ln in linhas]
    usar_hora = all(h is not None for h in horas)
    xs = horas if usar_hora else list(range(1, len(linhas) + 1))
    largura = 12 * 60 * 1000 if usar_hora else 0.6
    por_ag: dict = {}
    for x, ln in zip(xs, linhas):
        taxa = _num(ln.get("taxa"))
        if taxa:
            por_ag.setdefault(ln.get("agencia") or "-", ([], []))
            por_ag[ln.get("agencia") or "-"][0].append(x)
            por_ag[ln.get("agencia") or "-"][1].append(taxa)
    for i, (ag, (bx, by)) in enumerate(sorted(por_ag.items())):
        fig.add_trace(go.Bar(x=bx, y=by, name=f"Gasto: {ag}", marker_color=PALETA[i % len(PALETA)], width=largura,
                             hovertemplate="%{y} m7Coins<extra>" + ag + "</extra>"), secondary_y=False)
    sx = [x for x, ln in zip(xs, linhas) if _num(ln.get("saldo")) is not None]
    sy = [ln["saldo"] for ln in linhas if _num(ln.get("saldo")) is not None]
    if sy:
        fig.add_trace(go.Scatter(x=sx, y=sy, mode="lines+markers", name="Saldo", line=dict(
            color=COR["azul"], width=2, shape="hv"), marker=dict(size=6),
            hovertemplate="Saldo: %{y} m7Coins<extra></extra>"), secondary_y=True)
    fig.update_yaxes(title_text="Taxa por chamada", secondary_y=False, rangemode="tozero")
    fig.update_yaxes(title_text="Saldo", secondary_y=True, showgrid=False, rangemode="tozero")
    if usar_hora:
        fig.update_xaxes(tickformat="%H:%M")
    else:
        fig.update_xaxes(title_text="Chamada nº", dtick=1)
    return fig


def evolucao(placar: list, numero_equipe: int | None) -> go.Figure:
    """Nota de cada equipe ao longo do dia (snapshots de `GET /placar`); a nossa em destaque."""
    fig = _novo(340)
    snaps = [p for p in placar or [] if isinstance(p, dict)]
    equipes: dict = {}
    horas = [hora(p) for p in snaps]
    usar_hora = bool(snaps) and all(h is not None for h in horas)
    for i, (p, h) in enumerate(zip(snaps, horas)):
        for e in p.get("equipes") or []:
            n = e.get("numero")
            if n is None or _num(e.get("nota")) is None:
                continue
            d = equipes.setdefault(n, {"nome": e.get("nome", ""), "x": [], "y": [], "pos": []})
            d["x"].append(h if usar_hora else i + 1)
            d["y"].append(e["nota"])
            d["pos"].append(e.get("posicao"))
    if not equipes:
        return _vazio(fig)
    for n, d in sorted(equipes.items(), key=lambda kv: kv[0] == numero_equipe):
        nossa = n == numero_equipe
        fig.add_trace(go.Scatter(
            x=d["x"], y=d["y"], customdata=d["pos"], mode="lines+markers" if nossa or numero_equipe is None else "lines",
            name="Nossa equipe" if nossa else f"#{n} {d['nome']}".strip(),
            line=dict(color=COR["principal"] if nossa else rgba(COR["neutra"], 0.75), width=3.5 if nossa else 1.5),
            marker=dict(size=7),
            hovertemplate=f"#{n} {d['nome']}<br>Nota %{{y:,.1f}}<br>Posição %{{customdata}}<extra></extra>"))
    fig.update_yaxes(title_text="Nota")
    if usar_hora:
        fig.update_xaxes(tickformat="%H:%M")
    else:
        fig.update_xaxes(title_text="Atualização nº", dtick=1)
    return fig


def curva_demanda(demanda: list, escolhida: int | None) -> go.Figure:
    """Nota pública × demanda contratada, com a escolhida em destaque e a alternativa sem demanda (B3)."""
    fig = _novo(340)
    itens = [d for d in demanda or [] if isinstance(d, dict) and _num(d.get("nota")) is not None]
    com = sorted((d for d in itens if _num(d.get("demanda_kw")) is not None), key=lambda d: d["demanda_kw"])
    sem = [d for d in itens if _num(d.get("demanda_kw")) is None]
    if not com and not sem:
        return _vazio(fig)
    if com:
        fig.add_trace(go.Scatter(
            x=[d["demanda_kw"] for d in com], y=[d["nota"] for d in com], mode="lines+markers", name="Nota pública",
            line=dict(color=COR["azul"], width=2.5), marker=dict(size=7),
            hovertemplate="%{x} kW<br>Nota %{y:,.1f}<extra></extra>"))
        marca = [d for d in com if d["demanda_kw"] == escolhida]
        if marca:
            fig.add_trace(go.Scatter(
                x=[marca[0]["demanda_kw"]], y=[marca[0]["nota"]], mode="markers", name="Escolhida",
                marker=dict(symbol="star", size=18, color=COR["principal"], line=dict(color="white", width=1.5)),
                hovertemplate="Escolhida: %{x} kW<br>Nota %{y:,.1f}<extra></extra>"))
    if sem:
        melhor = max(d["nota"] for d in sem)
        rot = (sem[0].get("entrada") or "B3").upper().replace("_", " ")
        _linha_h(fig, melhor, COR["neutra"], "dash", f"Sem demanda contratada ({rot}): {_n(melhor, 0)}")
    fig.update_xaxes(title_text="Demanda contratada (kW)")
    fig.update_yaxes(title_text="Nota")
    return fig


def pesos_vs_reais(estimados: dict, reais: dict | None) -> go.Figure:
    """Pesos estimados na Neblina × pesos do catálogo (em módulo; o sinal vem do tipo do item)."""
    fig = _novo(320)

    def norm(d):
        return {ALIAS_PESOS.get(k, k): abs(v) for k, v in (d or {}).items() if _num(v) is not None}

    est, real = norm(estimados), norm(reais)
    ordem = [(i, r) for i, r in ITENS if i in est or i in real]
    if not ordem:
        return _vazio(fig)
    fig.add_trace(go.Bar(x=[r for _, r in ordem], y=[est.get(i) for i, _ in ordem], name="Estimado",
                         marker_color=COR["azul"], hovertemplate="%{x}<br>Estimado: %{y:.2f}<extra></extra>"))
    if real:
        fig.add_trace(go.Bar(x=[r for _, r in ordem], y=[real.get(i) for i, _ in ordem], name="Real (catálogo)",
                             marker_color=COR["principal"], hovertemplate="%{x}<br>Real: %{y:.2f}<extra></extra>"))
    fig.update_layout(barmode="group", bargap=0.25, showlegend=True)
    fig.update_yaxes(title_text="Peso (módulo)")
    return fig


def obra_por_agencia(custos: dict) -> go.Figure:
    """Custo de obra (pontos) por agência. `custos`: {agência: (pontos, origem)}, origem 'juiz', 'modelo' ou 'estimado'."""
    fig = _novo(320)
    itens = [(ag, v) for ag, v in sorted((custos or {}).items()) if _num(v[0]) is not None]
    if not itens:
        return _vazio(fig)
    cor = {"juiz": COR["principal"], "modelo": COR["azul"], "estimado": COR["ponta"]}
    nomes = {"juiz": "juiz", "modelo": "modelo da equipe", "estimado": "estimado"}
    fig.add_trace(go.Bar(
        name="Obra", showlegend=False, width=0.45,
        x=[ag for ag, _ in itens], y=[v[0] for _, v in itens], marker_color=[cor.get(v[1], COR["neutra"]) for _, v in itens],
        text=[_n(v[0], 0) for _, v in itens], textposition="outside", cliponaxis=False,
        customdata=[nomes.get(v[1], v[1]) for _, v in itens],
        hovertemplate="%{x}<br>%{y:,.1f} pontos<br>Origem: %{customdata}<extra></extra>"))
    for origem in dict.fromkeys(v[1] for _, v in itens):
        _legenda(fig, nomes.get(origem, origem).capitalize(), cor.get(origem, COR["neutra"]))
    fig.update_layout(bargap=0.4)
    fig.update_yaxes(title_text="Pontos de obra", rangemode="tozero")
    return fig
