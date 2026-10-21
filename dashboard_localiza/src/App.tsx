import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { Bars, GroupedBars, LineChart, Waterfall, nf0, nf1 } from './charts'
import { AGENCIAS, AGENCIAS_PLACAR, DIAS, EQUIPE, useDados } from './data'
import type { Agencia, Dados, Envio, Serie } from './data'
import { Icon } from './icons'
import type { IconName } from './icons'

const ITEM: Record<string, [string, string]> = {
  certo: ['Certos', 'Atendidos na categoria certa'],
  upgrade: ['Upg.', 'Atendidos com upgrade'],
  nao_atendido: ['Perd.', 'Clientes perdidos'],
  demanda_contratada: ['Dem.', 'Demanda contratada'],
  energia_ponta_kwh: ['Ponta', 'Energia na ponta'],
  infraestrutura: ['Obra', 'Custo de obra'],
}
const NOME_PRIORIDADE: Record<string, string> = { proxima_retirada: 'próxima retirada', menor_soc: 'menor SOC', chegada: 'ordem de chegada' }
const PASSO_SEMANA = 672 // 15 minutos x 96 x 7

function Logo() {
  return (
    <div className="brand">
      <div className="brand-mark">
        <span />
        <span />
        <span />
      </div>
      <div>
        <strong>Caórdicos</strong>
        <small>recarga inteligente</small>
      </div>
    </div>
  )
}

function Card({ children, className = '', id }: { children: ReactNode; className?: string; id?: string }) {
  return (
    <section className={`card ${className}`} id={id}>
      {children}
    </section>
  )
}

function CardHeader({ title, subtitle, tag, hint }: { title: string; subtitle: string; tag?: string; hint?: string }) {
  return (
    <div className="card-header">
      <div>
        <div className="card-title-row">
          <h2>{title}</h2>
          {tag && <span className="status-tag">{tag}</span>}
        </div>
        <p>{subtitle}</p>
      </div>
      {hint && (
        <span className="icon-button" title={hint} role="img" aria-label={hint}>
          <Icon name="info" size={17} />
        </span>
      )}
    </div>
  )
}

function KpiCard({ label, value, meta, icon, tone }: { label: string; value: string; meta: string; icon: IconName; tone: string }) {
  return (
    <article className="kpi-card">
      <div className={`kpi-icon ${tone}`}>
        <Icon name={icon} size={19} />
      </div>
      <div className="kpi-copy">
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{meta}</small>
      </div>
    </article>
  )
}

function bandasDePonta(rows: Serie[]): [number, number][] {
  const out: [number, number][] = []
  let ini: number | null = null
  rows.forEach((r, i) => {
    if (r.ponta && ini === null) ini = i
    if (!r.ponta && ini !== null) {
      out.push([ini, i])
      ini = null
    }
  })
  if (ini !== null) out.push([ini, rows.length - 1])
  return out
}

/** Faixa absoluta (índice de 15 min na janela inteira) para índices relativos ao período mostrado. */
function faixaRelativa(a: number, b: number, inicio: number, tamanho: number): [number, number][] {
  const ini = Math.max(a - inicio, 0)
  const fim = Math.min(b - inicio, tamanho - 1)
  return fim > ini ? [[ini, fim]] : []
}

function marcasX(rows: Serie[], passo: number) {
  const out: { i: number; label: string }[] = []
  for (let i = 0; i < rows.length; i += passo) out.push({ i, label: rows[i].hora.slice(0, 9) })
  return out
}

function Mapa({ perdidos }: { perdidos: Dados['perdidos'] }) {
  const grade = DIAS.map((_, d) => Array.from({ length: 24 }, (_, h) => perdidos.find((p) => p.dia_idx === d && p.hora === h)?.perdidos ?? 0))
  const max = Math.max(0, ...grade.flat())
  if (max === 0) return <p className="empty">Nenhum cliente perdido nas semanas públicas.</p>
  const nivel = (v: number) => (v === 0 ? 0 : Math.min(4, Math.max(1, Math.ceil((v / max) * 4))))
  return (
    <div className="heatmap-wrap">
      <div className="heatmap">
        <div />
        {Array.from({ length: 24 }, (_, h) => (
          <span className="hour-label" key={h}>
            {h % 3 === 0 ? `${String(h).padStart(2, '0')}h` : ''}
          </span>
        ))}
        {grade.map((linha, d) => (
          <div className="heatmap-row" key={d}>
            <span>{DIAS[d]}</span>
            {linha.map((v, h) => (
              <i className={`heat-${nivel(v)}`} key={h} title={`${DIAS[d]} ${String(h).padStart(2, '0')}h: ${v} perdidos`} />
            ))}
          </div>
        ))}
      </div>
      <div className="heatmap-legend">
        <span>Menos</span>
        {[0, 1, 2, 3, 4].map((v) => (
          <i className={`heat-${v}`} key={v} />
        ))}
        <span>Mais</span>
      </div>
    </div>
  )
}

function Painel({ dados }: { dados: Dados }) {
  const [agencia, setAgencia] = useState<Agencia>(AGENCIAS[0])
  const [semana, setSemana] = useState(1)
  const [menu, setMenu] = useState(false)
  const [ativo, setAtivo] = useState('visao-geral')

  const envio = dados.envios.find((e) => e.agencia === agencia) as Envio
  const equipes = dados.placar.equipes
  const nossa = equipes.find((e) => e.numero === EQUIPE)
  const lider = equipes[0]

  const serieAg = useMemo(() => dados.serie.filter((s) => s.agencia === agencia), [dados, agencia])
  const rows = semana === 0 ? serieAg : serieAg.slice((semana - 1) * PASSO_SEMANA, semana * PASSO_SEMANA)
  const pico = Math.max(...rows.map((r) => r.potencia_kw))
  const maxPlug = Math.max(...rows.map((r) => r.plugados))
  const maxFila = Math.max(...rows.map((r) => r.fila))
  const inicioPeriodo = semana === 0 ? 0 : (semana - 1) * PASSO_SEMANA
  const eventosAg = dados.eventos.filter((e) => e.agencia === agencia)
  const faixasEvento = eventosAg.flatMap((e) => faixaRelativa(e.inicio_idx, e.fim_idx, inicioPeriodo, rows.length))
  const socs = useMemo(() => dados.soc.filter((s) => s.agencia === agencia), [dados, agencia])
  const socMedio = socs.length ? socs.reduce((a, s) => a + s.soc, 0) / socs.length : 0
  const upgradePct = socs.length ? (socs.filter((s) => s.upgrade).length / socs.length) * 100 : 0
  const cascata = dados.cascata.filter((c) => c.agencia === agencia).sort((a, b) => a.ordem - b.ordem)
  const gastoPorAg = useMemo(() => {
    const t: Record<string, number> = {}
    dados.gastos.forEach((g) => (t[g.agencia] = (t[g.agencia] ?? 0) + g.taxa))
    return t
  }, [dados])
  const gastoTotal = nossa ? dados.meta.saldo_inicial - nossa.saldo : 0
  const maxCoins = Math.max(1, ...AGENCIAS.map((a) => gastoPorAg[a] ?? 0))
  const maxObra = Math.max(1, ...dados.envios.map((e) => e.obra))

  const histograma = useMemo(() => {
    // a maioria sai exatamente no alvo (80%): uma barra só para ela, o resto em faixas de 5 pontos
    const faixas = [
      { label: '80', ate: 80.5, value: 0 },
      { label: '80–85', ate: 85, value: 0 },
      { label: '85–90', ate: 90, value: 0 },
      { label: '90–95', ate: 95, value: 0 },
      { label: '95–100', ate: 101, value: 0 },
    ]
    socs.forEach((s) => {
      const f = faixas.find((x) => s.soc < x.ate)
      if (f) f.value += 1
    })
    return faixas.map(({ label, value }) => ({ label, value }))
  }, [socs])

  function ir(id: string) {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    setAtivo(id)
    setMenu(false)
  }

  function exportar() {
    const payload = {
      exportadoEm: new Date().toISOString(),
      agencia,
      envio,
      cascata,
      perdidosPorDiaHora: dados.perdidos.filter((p) => p.agencia === agencia),
      placar: nossa,
      observacao: 'Notas do placar: semanas ocultas. Demais números: motor local, semanas públicas.',
    }
    const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `relatorio-${agencia}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  const quando = (iso: string | null) => (iso ? new Date(iso).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' }) : '—')
  const atras = nossa && lider && nossa.posicao > 1 ? `, ${nf0.format(lider.nota - nossa.nota)} pontos atrás do 1º (${lider.equipe})` : ''
  const NAV: [string, string, IconName][] = [
    ['visao-geral', 'Visão geral', 'grid'],
    ['agencias', 'Agências', 'building'],
    ['potencia', 'Potência', 'bolt'],
    ['operacao', 'Operação', 'car'],
  ]
  const NAV2: [string, string, IconName][] = [
    ['consolidado', 'Investimentos', 'wallet'],
    ['placar', 'Placar', 'trophy'],
    ['pendencias', 'Pendências', 'info'],
    ['estrategia', 'Estratégia', 'chart'],
  ]

  return (
    <div className="app-shell">
      <aside className={menu ? 'sidebar open' : 'sidebar'}>
        <Logo />
        <nav aria-label="Navegação principal">
          <span>Monitoramento</span>
          {NAV.map(([id, nome, icone]) => (
            <button className={ativo === id ? 'nav-item active' : 'nav-item'} key={id} onClick={() => ir(id)}>
              <Icon name={icone} />
              {nome}
              {id === 'agencias' && <span className="nav-badge">{AGENCIAS.length}</span>}
            </button>
          ))}
          <span>Performance</span>
          {NAV2.map(([id, nome, icone]) => (
            <button className={ativo === id ? 'nav-item active' : 'nav-item'} key={id} onClick={() => ir(id)}>
              <Icon name={icone} />
              {nome}
            </button>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="challenge">
            <div className="challenge-icon">
              <Icon name="bolt" size={17} />
            </div>
            <div>
              <span>Hackathon</span>
              <strong>Recarga Inteligente</strong>
            </div>
          </div>
          <div className="user">
            <div className="avatar">OC</div>
            <div>
              <strong>Os Caórdicos</strong>
              <span>Equipe #{EQUIPE}</span>
            </div>
          </div>
        </div>
      </aside>

      <div className="main-shell">
        <header className="topbar">
          <button className="mobile-menu icon-button" onClick={() => setMenu(!menu)} aria-label="Abrir menu">
            <Icon name="menu" size={20} />
          </button>
          <div className="breadcrumb">
            <span>Recarga Inteligente</span>
            <Icon name="chevron" size={14} />
            <strong>Visão geral</strong>
          </div>
          <div className="top-actions">
            <div className="live-status">
              <i />
              Placar de {quando(dados.placar.atualizado_em)}
            </div>
            <button className="export-button" onClick={exportar}>
              <Icon name="download" size={17} />
              Exportar relatório
            </button>
          </div>
        </header>

        <main>
          <section className="hero" id="visao-geral">
            <div>
              <span className="eyebrow">Central de decisão</span>
              <h1>Os Caórdicos · equipe {EQUIPE}</h1>
              {nossa && (
                <p>
                  {nossa.posicao}º no placar com {nf0.format(nossa.nota)} pontos{atras}. Notas do placar são das semanas ocultas; os gráficos vêm do nosso motor nas 4 semanas públicas.
                </p>
              )}
            </div>
            <div className="period-filter" role="group" aria-label="Período dos gráficos de potência e ocupação">
              <Icon name="clock" size={16} />
              {[0, 1, 2, 3, 4].map((s) => (
                <button className={semana === s ? 'selected' : ''} key={s} onClick={() => setSemana(s)}>
                  {s === 0 ? '4 semanas' : `Sem ${s}`}
                </button>
              ))}
            </div>
          </section>

          <section className="agency-filter" id="agencias">
            <div>
              <span>Agência em análise</span>
              <div className="agency-tabs">
                {AGENCIAS.map((a) => (
                  <button className={agencia === a ? 'active' : ''} key={a} onClick={() => setAgencia(a)}>
                    {a}
                  </button>
                ))}
              </div>
            </div>
            <div className="model-chip">
              <i />
              Motor local · semanas públicas
            </div>
          </section>

          <section className="kpi-grid">
            <KpiCard label="Nota no placar" value={envio.nota_oculta_placar === null ? '—' : nf0.format(envio.nota_oculta_placar)} meta="semanas ocultas" icon="trophy" tone="green-tone" />
            <KpiCard label="Nota no motor" value={nf0.format(envio.nota_publica_motor)} meta="semanas públicas" icon="trend" tone="dark-tone" />
            <KpiCard label="Clientes perdidos" value={nf0.format(envio.perdidos_publicos)} meta={`${nf1.format(envio.atendimento_pct)}% de ${nf0.format(envio.contratos)} atendidos`} icon="car" tone="yellow-tone" />
            <KpiCard label="Pico de 15 min" value={`${nf1.format(pico)} kW`} meta={`limite de ${nf1.format(envio.limite_kw)} kW`} icon="bolt" tone="dark-tone" />
          </section>

          <section className="primary-grid">
            <Card className="power-card" id="potencia">
              <CardHeader
                title="Curva de potência"
                subtitle="Média a cada 15 minutos contra o limite da agência"
                tag={`${Math.round((pico / envio.limite_kw) * 100)}% do limite no pico`}
                hint="Limite = kW útil da entrada (B3) ou demanda contratada (A4). Em Marrakech, o corte da concessionária reduz o limite a 70% no motor."
              />
              {eventosAg.map((e) => (
                <p className="event-note" key={e.tipo}>
                  <b>Evento em {e.agencia}:</b> {e.descricao}, de {e.inicio_texto} a {e.fim_texto}.
                </p>
              ))}
              <LineChart
                id={`pot-${agencia}-${semana}`}
                height={230}
                yMax={Math.max(pico, ...rows.map((r) => r.limite_kw))}
                yFormat={(v) => `${nf0.format(v)} kW`}
                xTicks={marcasX(rows, semana === 0 ? PASSO_SEMANA : 96)}
                bands={bandasDePonta(rows)}
                eventBands={faixasEvento}
                series={[
                  { values: rows.map((r) => r.limite_kw), color: 'var(--danger)', step: true, width: 1.4, dash: '6 5' },
                  { values: rows.map((r) => r.potencia_kw), color: 'var(--green-dark)', area: true },
                ]}
                tip={(i) => ({
                  title: rows[i].hora,
                  lines: [
                    { color: 'var(--green-dark)', label: 'Potência', value: `${nf1.format(rows[i].potencia_kw)} kW` },
                    { color: 'var(--danger)', label: 'Limite', value: `${nf1.format(rows[i].limite_kw)} kW` },
                    { label: 'Plugados', value: nf0.format(rows[i].plugados) },
                    { label: 'Fila', value: nf0.format(rows[i].fila) },
                  ],
                })}
              />
              <div className="chart-legend">
                <span>
                  <i className="legend-line green" /> Potência média
                </span>
                <span>
                  <i className="legend-line dashed" /> Limite da agência
                </span>
                <span>
                  <i className="legend-block" /> Ponta (seg–sex, 18h–21h)
                </span>
                {eventosAg.length > 0 && (
                  <span>
                    <i className="legend-block event" /> Evento
                  </span>
                )}
              </div>
            </Card>
            <Card className="waterfall-card">
              <CardHeader title="Cascata de pontos" subtitle="De onde vem a nota da agência" tag="semanas públicas" hint="Pesos do catálogo: +15 certo, +8 upgrade, −200 perdido, −2 por kW contratado, −0,5 por kWh na ponta, −1 por ponto de obra." />
              <Waterfall height={250} items={cascata.map((c) => ({ label: ITEM[c.item]?.[0] ?? c.item, full: ITEM[c.item]?.[1], value: c.pontos }))} />
            </Card>
          </section>

          <section className="secondary-grid" id="operacao">
            <Card className="occupancy-card">
              <CardHeader title="Ocupação & fila" subtitle="Carros plugados e carros esperando" />
              <div className="occupancy-layout">
                <div>
                  <LineChart
                    id={`oc-${agencia}-${semana}`}
                    height={170}
                    yMax={Math.max(envio.vagas, maxPlug, maxFila)}
                    yFormat={(v) => nf0.format(v)}
                    xTicks={marcasX(rows, semana === 0 ? PASSO_SEMANA : 96)}
                    eventBands={faixasEvento}
                    refs={[{ v: envio.saidas, label: 'Saídas instaladas', color: 'var(--green-dark)' }]}
                    series={[
                      { values: rows.map((r) => r.fila), color: 'var(--yellow)', step: true, width: 1.6 },
                      { values: rows.map((r) => r.plugados), color: 'var(--green-dark)', width: 1.6 },
                    ]}
                    tip={(i) => ({
                      title: rows[i].hora,
                      lines: [
                        { color: 'var(--green-dark)', label: 'Plugados', value: nf0.format(rows[i].plugados) },
                        { color: 'var(--yellow)', label: 'Na fila', value: nf0.format(rows[i].fila) },
                      ],
                    })}
                  />
                  <div className="chart-legend">
                    <span>
                      <i className="legend-line green" /> Plugados
                    </span>
                    <span>
                      <i className="legend-line yellow" /> Fila
                    </span>
                  </div>
                </div>
                <div className="live-metrics">
                  <div>
                    <span>Máx. plugados</span>
                    <strong>{nf0.format(maxPlug)}</strong>
                    <small>
                      <i className="dot green-dot" /> de {envio.saidas} saídas e {envio.vagas} vagas
                    </small>
                  </div>
                  <div>
                    <span>Máx. na fila</span>
                    <strong>{nf0.format(maxFila)}</strong>
                    <small>
                      <i className="dot yellow-dot" /> no período escolhido
                    </small>
                  </div>
                </div>
              </div>
            </Card>
            <Card className="soc-card">
              <CardHeader title="SOC na retirada" subtitle="Carros entregues por faixa de carga (%)" hint="Só sai carro com 80% ou mais. Upgrades: cliente atendido com categoria acima da pedida." />
              <div className="soc-layout">
                <Bars height={190} items={histograma} format={(v) => nf0.format(v)} />
                <div className="soc-summary">
                  <div className="donut" style={{ ['--value' as string]: `${socMedio}%` }}>
                    <div>
                      <strong>{nf1.format(socMedio)}%</strong>
                      <span>SOC médio</span>
                    </div>
                  </div>
                  <p>
                    {nf1.format(upgradePct)}% das retiradas com upgrade. Alvo de recarga: 80%.
                  </p>
                </div>
              </div>
            </Card>
            <Card className="lost-card">
              <CardHeader title="Clientes perdidos" subtitle="Por dia da semana e hora, nas 4 semanas" tag={`${nf0.format(envio.perdidos_publicos)} no total`} />
              <Mapa perdidos={dados.perdidos.filter((p) => p.agencia === agencia)} />
            </Card>
          </section>

          <div className="section-heading" id="consolidado">
            <div>
              <span className="eyebrow">Visão consolidada</span>
              <h2>Performance da operação</h2>
            </div>
            <span className="updated">
              <i /> Dados gerados em {quando(dados.meta.gerado_em)}
            </span>
          </div>

          <div className="consolidated-grid">
            <Card className="cost-card">
              <CardHeader title="Investimento por agência" subtitle="m7Coins gastos e custo de obra em pontos" hint="m7Coins vêm do registro de chamadas do repositório da equipe e dos reenvios; testes feitos pelo site não aparecem." />
              <div className="cost-list">
                {AGENCIAS.map((a) => {
                  const e = dados.envios.find((x) => x.agencia === a) as Envio
                  const coins = gastoPorAg[a] ?? 0
                  return (
                    <div className="cost-row" key={a}>
                      <div className="cost-label">
                        <strong>{a}</strong>
                        <span>{nf0.format(coins)} m7C</span>
                      </div>
                      <div className="cost-bars">
                        <div className="stacked-track">
                          <i className="coin-bar" style={{ width: `${(coins / maxCoins) * 100}%` }} />
                        </div>
                        <div className="stacked-track">
                          <i className="work-bar" style={{ width: `${(e.obra / maxObra) * 100}%` }} />
                        </div>
                      </div>
                      <span className="work-cost">{nf0.format(e.obra)} pts</span>
                    </div>
                  )
                })}
              </div>
              <div className="chart-legend">
                <span>
                  <i className="legend-dot yellow-dot" /> m7Coins
                </span>
                <span>
                  <i className="legend-dot dark-dot" /> Custo de obra
                </span>
                <span>m7Coins gastos pela equipe: {nf0.format(gastoTotal)}</span>
              </div>
            </Card>
            <Card className="score-card">
              <CardHeader title="Evolução da nota" subtitle="Capturas do placar, em horário UTC" tag={nossa ? `${nossa.posicao}º lugar` : undefined} />
              <LineChart
                id="evolucao"
                height={200}
                yMax={Math.max(...dados.evolucao.map((e) => e.nota))}
                yFormat={(v) => nf0.format(v)}
                xTicks={dados.evolucao.map((e, i) => ({ i, label: e.hora_utc }))}
                series={[{ values: dados.evolucao.map((e) => e.nota), color: 'var(--green-dark)', area: true, width: 2.4 }]}
                tip={(i) => ({ title: `${dados.evolucao[i].hora_utc} UTC`, lines: [{ label: 'Nota', value: nf0.format(dados.evolucao[i].nota) }, { label: 'Fonte', value: dados.evolucao[i].fonte }] })}
              />
            </Card>
          </div>

          <div className="consolidated-grid">
            <Card className="notes-card">
              <CardHeader title="Nota por agência" subtitle="Placar (semanas ocultas) e motor (semanas públicas), envios vigentes" />
              <GroupedBars
                height={240}
                colors={['var(--green-dark)', 'var(--green)']}
                names={['Placar, semanas ocultas', 'Motor, semanas públicas']}
                groups={dados.envios.map((e) => ({ label: e.agencia, values: [e.nota_oculta_placar, e.nota_publica_motor] }))}
              />
              <div className="chart-legend">
                <span>
                  <i className="legend-dot dark-dot" /> Placar, semanas ocultas
                </span>
                <span>
                  <i className="legend-dot green-dot" /> Motor, semanas públicas
                </span>
              </div>
            </Card>
            <Card className="ranking-card" id="placar">
              <CardHeader title="Placar" subtitle="Nota por agência nas semanas ocultas" tag={`${equipes.length} equipes`} />
              <div className="table-scroll">
                <table className="ranking">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th className="left">Equipe</th>
                      <th>Nota</th>
                      {AGENCIAS_PLACAR.map((a) => (
                        <th key={a}>{a}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {equipes.map((e) => (
                      <tr className={e.numero === EQUIPE ? 'me' : ''} key={e.numero}>
                        <td>{e.posicao}</td>
                        <td className="left">{e.equipe}</td>
                        <td>{nf0.format(e.nota)}</td>
                        {AGENCIAS_PLACAR.map((a) => (
                          <td key={a}>{e[a] === null ? '—' : nf0.format(e[a] as number)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>

          <Card className="pending-card" id="pendencias">
            <CardHeader title="Pendências e próximos envios" subtitle="O que ainda pode aumentar a nota" tag={`saldo ${nf0.format(dados.meta.saldo_atual)} m7C`} hint="O 1º envio final de cada agência é grátis; o reenvio custa 80, 160, 320... m7Coins." />
            <ul className="pending-list">
              {dados.meta.pendentes.map((a) => (
                <li key={a}>
                  <strong>{a}</strong>
                  <span>Agência sem envio da equipe: vale 0 até o 1º envio, que é grátis.</span>
                  <em className="chip ok">1º envio grátis</em>
                </li>
              ))}
              {dados.candidatas.map((c) => (
                <li key={c.agencia}>
                  <strong>{c.agencia}</strong>
                  <span>
                    Alternativa: {c.carregadores}, {c.entrada}
                    {c.demanda_kw > 0 ? `, ${nf0.format(c.demanda_kw)} kW` : ''}
                    {c.evitar_ponta ? ', evita a ponta' : ''}. Motor: {nf0.format(c.nota_motor_atual)} → {nf0.format(c.nota_motor_candidata)} nas semanas públicas
                    {c.media_8_momentos !== null ? `; média de ${nf0.format(c.media_8_momentos)} com o evento em 8 horários` : ''}.
                  </span>
                  <em className={c.cabe_no_saldo ? 'chip ok' : 'chip no'}>
                    {nf0.format(c.custo_reenvio)} m7C{c.cabe_no_saldo ? '' : ' · sem saldo'}
                  </em>
                </li>
              ))}
              {dados.meta.pendentes.length === 0 && dados.candidatas.length === 0 && <li className="empty-row">Nenhuma pendência no momento.</li>}
            </ul>
          </Card>

          <Card className="strategy-card" id="estrategia">
            <div className="strategy-heading">
              <div className="strategy-icon">
                <Icon name="trend" size={21} />
              </div>
              <div>
                <h2>Racional da estratégia · {agencia}</h2>
                <p>Justificativa da escolha de carregadores, entrada e demanda contratada</p>
              </div>
              <span className="reviewed">Envio vigente</span>
            </div>
            <div className="strategy-columns">
              <div>
                <span className="strategy-number">Entrada e demanda</span>
                <h3>Entrada escolhida</h3>
                <strong>
                  {envio.entrada} • {envio.demanda_kw > 0 ? `${nf0.format(envio.demanda_kw)} kW contratados` : 'sem demanda (B3)'}
                </strong>
                <p>Limite da agência: {nf1.format(envio.limite_kw)} kW. {envio.justificativa}</p>
              </div>
              <div>
                <span className="strategy-number">Carregadores e política</span>
                <h3>Configuração enviada</h3>
                <strong>{envio.carregadores}</strong>
                <p>
                  Fila por {NOME_PRIORIDADE[envio.prioridade] ?? envio.prioridade}, divisão {envio.divisao}, {envio.evitar_ponta ? 'evita a ponta' : 'sem evitar a ponta'}. {envio.saidas} saídas para {envio.vagas} vagas, obra de {nf0.format(envio.obra)} pontos.
                </p>
              </div>
              <div className="strategy-highlight">
                <Icon name="leaf" size={22} />
                <span>Nota no placar</span>
                <strong>{envio.nota_oculta_placar === null ? '—' : nf0.format(envio.nota_oculta_placar)}</strong>
                <p>semanas ocultas; motor: {nf0.format(envio.nota_publica_motor)} nas públicas</p>
              </div>
            </div>
          </Card>
          <p className="footnote">
            Os gráficos operacionais são simulados no motor da equipe nas 4 semanas públicas, com os eventos ativos. O corte de Marrakech entra como 70% do limite da agência e a quebra de Istanbul como os 2 maiores carregadores fora de operação; nenhuma das duas regras foi confirmada pelo juiz.
          </p>
        </main>
      </div>
      {menu && <button className="sidebar-overlay" aria-label="Fechar menu" onClick={() => setMenu(false)} />}
    </div>
  )
}

export default function App() {
  const { dados, erro } = useDados()
  if (erro)
    return (
      <div className="estado erro">
        <strong>Não foi possível carregar os dados.</strong>
        <p>{erro}</p>
        <p>Gere os arquivos com <code>python gerar_dados_dashboard.py</code>, na pasta do kit.</p>
      </div>
    )
  if (!dados) return <div className="estado">Carregando dados…</div>
  return <Painel dados={dados} />
}
