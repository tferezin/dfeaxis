/**
 * Helper de competência fiscal/mensal — calendário (não ciclo Stripe).
 *
 * O DFeAxis usa "competência" = mês calendário (dia 1 a último dia, fuso
 * America/Sao_Paulo). Todos os contadores (docs_consumidos_mes), cobrança
 * de excedente (overage), e filtros de dashboard operam sobre esse mês.
 *
 * Convenções:
 *   - `CompetenciaId` = string "YYYY-MM" (ex: "2026-04")
 *   - `getCompetenciaRange(id)` retorna `{start, end}` em ISO UTC cobrindo
 *     o mês inteiro no fuso SP (start = 00:00:00 dia 1, end = 23:59:59 dia X)
 *   - `formatCompetenciaLabel(id)` gera label humana tipo "Abril / 2026"
 *
 * IMPORTANTE — timezone:
 *   O Supabase `fetched_at` é armazenado em UTC (timestamptz). Pra um filtro
 *   preciso de "competência SP", a gente converte o primeiro/último minuto
 *   do mês SP pra UTC antes de mandar no `gte/lte`. A diferença é +3h (SP
 *   é UTC-3, sem horário de verão desde 2019).
 */

const SP_OFFSET_HOURS = 3 // SP é UTC-3

export type CompetenciaId = string // "YYYY-MM"

export interface CompetenciaRange {
  id: CompetenciaId
  /** Início do mês em UTC (ex: 2026-04-01T03:00:00.000Z = 00:00 SP) */
  start: string
  /** Fim do mês em UTC (ex: 2026-05-01T02:59:59.999Z = 23:59:59.999 SP) */
  end: string
  /** Label curta pro UI: "Abr 2026" */
  shortLabel: string
  /** Label longa: "Abril de 2026" */
  longLabel: string
}

const MESES_LONG = [
  "Janeiro",
  "Fevereiro",
  "Março",
  "Abril",
  "Maio",
  "Junho",
  "Julho",
  "Agosto",
  "Setembro",
  "Outubro",
  "Novembro",
  "Dezembro",
]

const MESES_SHORT = [
  "Jan",
  "Fev",
  "Mar",
  "Abr",
  "Mai",
  "Jun",
  "Jul",
  "Ago",
  "Set",
  "Out",
  "Nov",
  "Dez",
]

/**
 * Retorna a competência atual ("YYYY-MM") baseada na data do usuário.
 * Usa a data local do browser, assumindo que está em SP (maioria dos
 * nossos clientes). Usuários em outros fusos veriam um mês "errado" no
 * default mas podem trocar manualmente via dropdown.
 */
export function currentCompetencia(): CompetenciaId {
  const now = new Date()
  const year = now.getFullYear()
  const month = now.getMonth() + 1 // getMonth é 0-based
  return `${year}-${String(month).padStart(2, "0")}`
}

/**
 * Parse "YYYY-MM" para ano e mês numéricos. Throws se formato inválido.
 */
function parseCompetencia(id: CompetenciaId): { year: number; month: number } {
  const match = id.match(/^(\d{4})-(\d{2})$/)
  if (!match) {
    throw new Error(`Competência inválida: "${id}". Esperado "YYYY-MM".`)
  }
  const year = parseInt(match[1]!, 10)
  const month = parseInt(match[2]!, 10)
  if (month < 1 || month > 12) {
    throw new Error(`Mês inválido em ${id}: ${month}`)
  }
  return { year, month }
}

/**
 * Retorna o range UTC que cobre o mês SP inteiro para usar em queries
 * `gte(fetched_at, start)` / `lte(fetched_at, end)` no Supabase.
 *
 * Ex: competência "2026-04" retorna:
 *   start = 2026-04-01T03:00:00.000Z (00:00 SP de 01/04)
 *   end   = 2026-05-01T02:59:59.999Z (23:59:59.999 SP de 30/04)
 */
export function getCompetenciaRange(id: CompetenciaId): CompetenciaRange {
  const { year, month } = parseCompetencia(id)

  // Primeiro dia do mês SP = 00:00:00 SP = 03:00:00 UTC
  const startUtc = new Date(Date.UTC(year, month - 1, 1, SP_OFFSET_HOURS, 0, 0, 0))

  // Primeiro minuto do MÊS SEGUINTE SP - 1ms = último ms do mês atual SP
  const nextMonth = month === 12 ? 1 : month + 1
  const nextYear = month === 12 ? year + 1 : year
  const endUtc = new Date(
    Date.UTC(nextYear, nextMonth - 1, 1, SP_OFFSET_HOURS, 0, 0, 0) - 1
  )

  const shortLabel = `${MESES_SHORT[month - 1]} ${year}`
  const longLabel = `${MESES_LONG[month - 1]} de ${year}`

  return {
    id,
    start: startUtc.toISOString(),
    end: endUtc.toISOString(),
    shortLabel,
    longLabel,
  }
}

/**
 * Formata uma competência para label curta ("Abr 2026").
 */
export function formatCompetenciaLabel(id: CompetenciaId): string {
  const { year, month } = parseCompetencia(id)
  return `${MESES_SHORT[month - 1]} ${year}`
}

/**
 * Gera uma lista de competências pro dropdown do dashboard.
 * Por padrão: competência atual + N meses anteriores.
 *
 * @param monthsBack quantos meses pra trás incluir (default 11 = 1 ano)
 */
export function buildCompetenciaOptions(monthsBack = 11): CompetenciaRange[] {
  const out: CompetenciaRange[] = []
  const now = new Date()
  let y = now.getFullYear()
  let m = now.getMonth() + 1 // 1-12

  for (let i = 0; i <= monthsBack; i++) {
    const id = `${y}-${String(m).padStart(2, "0")}`
    out.push(getCompetenciaRange(id))
    m -= 1
    if (m === 0) {
      m = 12
      y -= 1
    }
  }

  return out
}

/** Sentinela para a opção "Todos" no dropdown de competência */
export const COMPETENCIA_TODOS: CompetenciaId = "ALL"
