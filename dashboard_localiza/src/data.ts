import { useEffect, useState } from 'react'

export const AGENCIAS = ['Istanbul', 'Hanoi', 'Marrakech', 'Zurich', 'Vienna'] as const
export type Agencia = (typeof AGENCIAS)[number]
export const AGENCIAS_PLACAR = [...AGENCIAS, 'Lisbon'] as const
export const EQUIPE = 14
export const DIAS = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']

export type PlacarRow = {
  posicao: number
  numero: number
  equipe: string
  nota: number
  finais: number
  saldo: number
  nao_atendidos: number | null
  custo_obra: number | null
} & Record<Agencia | 'Lisbon', number | null>

export type Envio = {
  agencia: Agencia
  carregadores: string
  entrada: string
  demanda_kw: number
  prioridade: string
  divisao: string
  evitar_ponta: boolean
  vagas: number
  saidas: number
  obra: number
  limite_kw: number
  contratos: number
  atendimento_pct: number
  nota_publica_motor: number
  nota_oculta_placar: number | null
  perdidos_publicos: number
  justificativa: string
}

export type Cascata = { agencia: Agencia; ordem: number; item: string; qtd: number; peso: number; pontos: number }
export type Serie = { agencia: Agencia; idx: number; hora: string; potencia_kw: number; plugados: number; fila: number; limite_kw: number; ponta: number }
export type Soc = { agencia: Agencia; soc: number; upgrade: number }
export type Perdido = { agencia: Agencia; dia: string; dia_idx: number; hora: number; perdidos: number }
export type Gasto = { hora_utc: string; rota: string; agencia: string; taxa: number; saldo: number | null }
export type Evolucao = { hora_utc: string; nota: number; fonte: string }
export type Meta = { gerado_em: string; placar_atualizado_em: string | null; equipe: number; saldo_inicial: number; saldo_atual: number; pendentes: string[] }
export type Evento = { agencia: string; tipo: string; descricao: string; inicio_idx: number; fim_idx: number; inicio_texto: string; fim_texto: string }
export type Candidata = {
  agencia: Agencia
  carregadores: string
  entrada: string
  demanda_kw: number
  evitar_ponta: boolean
  obra: number
  obra_atual: number
  nota_motor_atual: number
  nota_motor_candidata: number
  nota_placar_atual: number | null
  media_8_momentos: number | null
  pior_8_momentos: number | null
  custo_reenvio: number
  cabe_no_saldo: boolean
  tem_evento: boolean
}

export type Dados = {
  placar: { atualizado_em: string | null; equipes: PlacarRow[] }
  envios: Envio[]
  cascata: Cascata[]
  serie: Serie[]
  soc: Soc[]
  perdidos: Perdido[]
  gastos: Gasto[]
  evolucao: Evolucao[]
  eventos: Evento[]
  candidatas: Candidata[]
  meta: Meta
}

const ARQUIVOS: Record<keyof Dados, string> = {
  placar: 'placar',
  envios: 'envios',
  cascata: 'cascata',
  serie: 'serie15',
  soc: 'soc_retirada',
  perdidos: 'perdidos',
  gastos: 'gastos',
  evolucao: 'evolucao',
  eventos: 'eventos',
  candidatas: 'candidatas',
  meta: 'meta',
}

/** Lê os JSON de public/data (gerados por `python gerar_dados_dashboard.py`). */
export function useDados(): { dados?: Dados; erro?: string } {
  const [estado, setEstado] = useState<{ dados?: Dados; erro?: string }>({})
  useEffect(() => {
    let vivo = true
    const base = import.meta.env.BASE_URL
    Promise.all(
      Object.entries(ARQUIVOS).map(async ([chave, arq]) => {
        const r = await fetch(`${base}data/${arq}.json`)
        if (!r.ok) throw new Error(`${arq}.json: ${r.status}`)
        return [chave, await r.json()] as const
      }),
    )
      .then((pares) => vivo && setEstado({ dados: Object.fromEntries(pares) as unknown as Dados }))
      .catch((e: Error) => vivo && setEstado({ erro: e.message }))
    return () => {
      vivo = false
    }
  }, [])
  return estado
}
