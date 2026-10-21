import { useEffect, useMemo, useRef, useState } from 'react'

export const nf0 = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 })
export const nf1 = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 1 })
export const signed = (v: number) => (v > 0 ? '+' : v < 0 ? '−' : '') + nf0.format(Math.abs(v))

export function useWidth<T extends HTMLElement>() {
  const ref = useRef<T | null>(null)
  const [w, setW] = useState(600)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    setW(el.clientWidth || 600)
    const ro = new ResizeObserver(() => setW(el.clientWidth || 600))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return [ref, w] as const
}

/** Marcas "redondas" entre lo e hi, no máximo ~count. */
export function ticksBetween(lo: number, hi: number, count = 4): number[] {
  if (hi <= lo) return [lo]
  const raw = (hi - lo) / count
  const mag = Math.pow(10, Math.floor(Math.log10(raw)))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw
  const out: number[] = []
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-6; v += step) out.push(Math.round(v * 1e6) / 1e6)
  return out
}

const CHAR = 6.4 // largura média de um caractere a 11px
const leftMargin = (labels: string[]) => 10 + CHAR * Math.max(...labels.map((l) => l.length), 2)

type Tip = { title: string; lines: { color?: string; label: string; value: string }[] }

function TipBox({ tip, x, width }: { tip: Tip; x: number; width: number }) {
  return (
    <div className="chart-tip" style={{ left: Math.max(4, Math.min(width - 190, x + 12)) }}>
      <span className="tip-title">{tip.title}</span>
      {tip.lines.map((l) => (
        <div key={l.label}>
          {l.color && <i style={{ background: l.color }} />}
          {l.label}: <b>{l.value}</b>
        </div>
      ))}
    </div>
  )
}

// ---------- gráfico de linhas ----------
export type LineSeries = { values: number[]; color: string; area?: boolean; step?: boolean; width?: number; dash?: string }

export function LineChart(p: {
  height: number
  series: LineSeries[]
  yMax: number
  yFormat: (v: number) => string
  xTicks: { i: number; label: string }[]
  bands?: [number, number][]
  eventBands?: [number, number][]
  refs?: { v: number; label: string; color: string }[]
  tip: (i: number) => Tip
  id: string
}) {
  const [ref, w] = useWidth<HTMLDivElement>()
  const [hover, setHover] = useState<number | null>(null)
  const n = p.series[0]?.values.length ?? 0
  const H = p.height
  const yTicks = ticksBetween(0, p.yMax * 1.08, 4)
  const m = { l: leftMargin(yTicks.map(p.yFormat)), r: 14, t: 10, b: 26 }
  const x = (i: number) => m.l + (n <= 1 ? 0 : (i / (n - 1)) * (w - m.l - m.r))
  const y = (v: number) => H - m.b - (v / (p.yMax * 1.08)) * (H - m.b - m.t)

  // afina os rótulos do eixo X para não se sobreporem em gráficos estreitos
  const xMostrados: typeof p.xTicks = []
  let ultimoX = -Infinity
  p.xTicks.forEach((t) => {
    if (x(t.i) - ultimoX >= 68) {
      xMostrados.push(t)
      ultimoX = x(t.i)
    }
  })

  const paths = useMemo(
    () =>
      p.series.map((s) => {
        const pts = s.values.map((v, i) => [x(i), y(v)] as const)
        let d = ''
        pts.forEach(([px, py], i) => {
          if (i === 0) d = `M${px.toFixed(1)},${py.toFixed(1)}`
          else if (s.step) d += `H${px.toFixed(1)}V${py.toFixed(1)}`
          else d += `L${px.toFixed(1)},${py.toFixed(1)}`
        })
        const area = s.area ? `${d}L${x(n - 1).toFixed(1)},${y(0)}L${x(0).toFixed(1)},${y(0)}Z` : ''
        return { d, area }
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [p.series, w, p.yMax],
  )

  return (
    <div className="chart-box" ref={ref} style={{ height: H }}>
      <svg width={w} height={H} role="img">
        <defs>
          {p.series.map((s, k) => (
            <linearGradient key={k} id={`${p.id}-g${k}`} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor={s.color} stopOpacity=".28" />
              <stop offset="100%" stopColor={s.color} stopOpacity="0" />
            </linearGradient>
          ))}
        </defs>
        {yTicks.map((v) => (
          <g key={v}>
            <line className="grid-line" x1={m.l} x2={w - m.r} y1={y(v)} y2={y(v)} />
            <text className="axis-text" x={m.l - 6} y={y(v)} dy="0.32em" textAnchor="end">
              {p.yFormat(v)}
            </text>
          </g>
        ))}
        {(p.eventBands ?? []).map(([a, b], k) => (
          <rect key={`e${k}`} className="event-window" x={x(a)} y={m.t} width={Math.max(1, x(b) - x(a))} height={H - m.b - m.t} />
        ))}
        {(p.bands ?? []).map(([a, b], k) => (
          <rect key={k} className="peak-window" x={x(a)} y={m.t} width={Math.max(1, x(b) - x(a))} height={H - m.b - m.t} />
        ))}
        {xMostrados.map((t, k) => (
          <text key={t.i} className="axis-text" x={x(t.i)} y={H - 8} textAnchor={k === 0 ? 'start' : 'middle'}>
            {t.label}
          </text>
        ))}
        <line className="axis-line" x1={m.l} x2={w - m.r} y1={y(0)} y2={y(0)} />
        {p.series.map((s, k) => (
          <g key={k}>
            {s.area && <path d={paths[k].area} fill={`url(#${p.id}-g${k})`} />}
            <path d={paths[k].d} fill="none" stroke={s.color} strokeWidth={s.width ?? 2} strokeLinecap="round" strokeLinejoin="round" strokeDasharray={s.dash} />
          </g>
        ))}
        {(p.refs ?? []).map((r) => (
          <g key={r.label}>
            <line x1={m.l} x2={w - m.r} y1={y(r.v)} y2={y(r.v)} stroke={r.color} strokeDasharray="6 5" strokeWidth={1.4} />
            <text className="axis-text" x={w - m.r - 2} y={y(r.v) - 5} textAnchor="end">
              {r.label}
            </text>
          </g>
        ))}
        {hover !== null && <line className="axis-line" x1={x(hover)} x2={x(hover)} y1={m.t} y2={H - m.b} />}
        {hover !== null &&
          p.series.map((s, k) => <circle key={k} cx={x(hover)} cy={y(s.values[hover])} r={3.5} fill="var(--surface)" stroke={s.color} strokeWidth={2} />)}
        <rect
          x={m.l}
          y={m.t}
          width={Math.max(0, w - m.l - m.r)}
          height={H - m.t - m.b}
          fill="transparent"
          onPointerMove={(e) => {
            const r = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect()
            const i = Math.round(((e.clientX - r.left - m.l) / (w - m.l - m.r)) * (n - 1))
            setHover(Math.max(0, Math.min(n - 1, i)))
          }}
          onPointerLeave={() => setHover(null)}
        />
      </svg>
      {hover !== null && <TipBox tip={p.tip(hover)} x={x(hover)} width={w} />}
    </div>
  )
}

// ---------- barras ----------
export function Bars(p: { items: { label: string; value: number; color?: string }[]; height: number; format?: (v: number) => string; name?: string }) {
  const [ref, w] = useWidth<HTMLDivElement>()
  const [hover, setHover] = useState<number | null>(null)
  const fmt = p.format ?? nf0.format
  const H = p.height
  const max = Math.max(1, ...p.items.map((d) => d.value))
  const yTicks = ticksBetween(0, max * 1.12, 4)
  const m = { l: leftMargin(yTicks.map(fmt)), r: 8, t: 16, b: 28 }
  const band = (w - m.l - m.r) / p.items.length
  const bw = Math.min(band * 0.62, 44)
  const y = (v: number) => H - m.b - (v / (max * 1.12)) * (H - m.b - m.t)
  return (
    <div className="chart-box" ref={ref} style={{ height: H }}>
      <svg width={w} height={H}>
        {yTicks.map((v) => (
          <g key={v}>
            <line className="grid-line" x1={m.l} x2={w - m.r} y1={y(v)} y2={y(v)} />
            <text className="axis-text" x={m.l - 6} y={y(v)} dy="0.32em" textAnchor="end">
              {fmt(v)}
            </text>
          </g>
        ))}
        {p.items.map((d, i) => {
          const cx = m.l + band * i + band / 2
          return (
            <g key={d.label} onPointerEnter={() => setHover(i)} onPointerLeave={() => setHover(null)}>
              <rect x={cx - bw / 2} y={y(d.value)} width={bw} height={Math.max(0, y(0) - y(d.value))} rx={4} fill={d.color ?? 'var(--green-dark)'} opacity={hover === null || hover === i ? 1 : 0.55} />
              <text className="value-text" x={cx} y={y(d.value) - 5} textAnchor="middle">
                {fmt(d.value)}
              </text>
              <text className="axis-text" x={cx} y={H - 9} textAnchor="middle">
                {d.label}
              </text>
            </g>
          )
        })}
        <line className="axis-line" x1={m.l} x2={w - m.r} y1={y(0)} y2={y(0)} />
      </svg>
    </div>
  )
}

export function GroupedBars(p: { groups: { label: string; values: (number | null)[] }[]; colors: string[]; names: string[]; height: number }) {
  const [ref, w] = useWidth<HTMLDivElement>()
  const [hover, setHover] = useState<{ g: number; k: number } | null>(null)
  const H = p.height
  const all = p.groups.flatMap((g) => g.values).filter((v): v is number => v !== null)
  const lo = Math.min(0, ...all) * 1.1
  const hi = Math.max(1, ...all) * 1.15
  const yTicks = ticksBetween(lo, hi, 5)
  const m = { l: leftMargin(yTicks.map(nf0.format)), r: 8, t: 16, b: 28 }
  const band = (w - m.l - m.r) / p.groups.length
  const bw = Math.min((band * 0.8) / p.colors.length, 34)
  const y = (v: number) => H - m.b - ((v - lo) / (hi - lo)) * (H - m.b - m.t)
  return (
    <div className="chart-box" ref={ref} style={{ height: H }}>
      <svg width={w} height={H}>
        {yTicks.map((v) => (
          <g key={v}>
            <line className="grid-line" x1={m.l} x2={w - m.r} y1={y(v)} y2={y(v)} />
            <text className="axis-text" x={m.l - 6} y={y(v)} dy="0.32em" textAnchor="end">
              {nf0.format(v)}
            </text>
          </g>
        ))}
        {p.groups.map((g, gi) => {
          const x0 = m.l + band * gi + band / 2 - (bw * p.colors.length) / 2
          return (
            <g key={g.label}>
              {g.values.map((v, k) =>
                v === null ? null : (
                  <g key={k} onPointerEnter={() => setHover({ g: gi, k })} onPointerLeave={() => setHover(null)}>
                    <rect x={x0 + bw * k + 1} y={Math.min(y(0), y(v))} width={bw - 2} height={Math.abs(y(v) - y(0))} rx={4} fill={p.colors[k]} opacity={!hover || (hover.g === gi && hover.k === k) ? 1 : 0.55} />
                    <text className="value-text" x={x0 + bw * k + bw / 2} y={v >= 0 ? y(v) - 5 : y(v) + 13} textAnchor="middle">
                      {nf0.format(v)}
                    </text>
                  </g>
                ),
              )}
              <text className="axis-text" x={m.l + band * gi + band / 2} y={H - 9} textAnchor="middle">
                {g.label}
              </text>
            </g>
          )
        })}
        <line className="axis-line" x1={m.l} x2={w - m.r} y1={y(0)} y2={y(0)} />
      </svg>
      {hover && (
        <div className="chart-tip" style={{ left: Math.max(4, Math.min(w - 190, m.l + band * hover.g + band / 2)), top: 6 }}>
          <span className="tip-title">{p.groups[hover.g].label}</span>
          <div>
            <i style={{ background: p.colors[hover.k] }} />
            {p.names[hover.k]}: <b>{nf0.format(p.groups[hover.g].values[hover.k] ?? 0)}</b>
          </div>
        </div>
      )}
    </div>
  )
}

// ---------- cascata ----------
export function Waterfall(p: { items: { label: string; full?: string; value: number }[]; height: number }) {
  const [ref, w] = useWidth<HTMLDivElement>()
  const H = p.height
  let run = 0
  const bars = p.items.map((d) => {
    const s = run
    run += d.value
    return { label: d.label, full: d.full ?? d.label, s, e: run, v: d.value, total: false }
  })
  bars.push({ label: 'Nota', full: 'Nota da agência', s: 0, e: run, v: run, total: true })
  const lo = Math.min(0, ...bars.flatMap((b) => [b.s, b.e]))
  const hi = Math.max(0, ...bars.flatMap((b) => [b.s, b.e]))
  const pad = (hi - lo) * 0.12
  const yTicks = ticksBetween(lo - pad, hi + pad, 5)
  const m = { l: leftMargin(yTicks.map(nf0.format)), r: 8, t: 18, b: 46 }
  const y = (v: number) => H - m.b - ((v - (lo - pad)) / (hi + pad - (lo - pad))) * (H - m.b - m.t)
  const band = (w - m.l - m.r) / bars.length
  const bw = Math.min(band * 0.62, 44)
  return (
    <div className="chart-box" ref={ref} style={{ height: H }}>
      <svg width={w} height={H}>
        {yTicks.map((v) => (
          <g key={v}>
            <line className="grid-line" x1={m.l} x2={w - m.r} y1={y(v)} y2={y(v)} />
            <text className="axis-text" x={m.l - 6} y={y(v)} dy="0.32em" textAnchor="end">
              {nf0.format(v)}
            </text>
          </g>
        ))}
        {bars.map((b, i) => {
          const cx = m.l + band * i + band / 2
          const fill = b.total ? 'var(--green-dark)' : b.v >= 0 ? 'var(--green)' : 'var(--danger)'
          const words = b.label.split(' ')
          return (
            <g key={b.label}>
              <rect x={cx - bw / 2} y={y(Math.max(b.s, b.e))} width={bw} height={Math.max(1.5, Math.abs(y(b.s) - y(b.e)))} rx={3} fill={fill}>
                <title>{`${b.full}: ${b.total ? nf0.format(b.v) : signed(b.v)}`}</title>
              </rect>
              <text className="value-text" x={cx} y={b.total || b.v >= 0 ? y(Math.max(b.s, b.e)) - 5 : y(Math.min(b.s, b.e)) + 13} textAnchor="middle">
                {b.total ? nf0.format(b.v) : signed(b.v)}
              </text>
              {words.map((wd, k) => (
                <text key={k} className="axis-text" x={cx} y={H - 28 + k * 13} textAnchor="middle">
                  {wd}
                </text>
              ))}
            </g>
          )
        })}
        <line className="axis-line" x1={m.l} x2={w - m.r} y1={y(0)} y2={y(0)} />
      </svg>
    </div>
  )
}
