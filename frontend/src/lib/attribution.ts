/**
 * Campaign attribution capture — salva UTM params / click IDs / referrer
 * em localStorage para sobreviver à navegação interna até o momento do
 * signup. É enviado junto do POST /tenants/register para persistir em
 * `tenants` (migration 014) e possibilitar relatórios internos de ROAS
 * por canal/campanha/keyword, sem depender exclusivamente do painel GA4.
 *
 * Estratégia: last-touch. Se o usuário visitar a landing com UTMs novos,
 * os anteriores no localStorage são sobrescritos. Isso bate com o modelo
 * de atribuição default do Google Ads quando há múltiplos toques.
 *
 * Por que localStorage e não sessionStorage?
 *   Alguns usuários abrem a landing num dia, pesquisam mais, voltam no
 *   outro dia pra cadastrar. SessionStorage perderia a atribuição. Usamos
 *   localStorage que persiste entre sessões — a atribuição sobrevive
 *   enquanto o usuário não limpar o storage.
 *
 * Por que não cookies?
 *   Cookies iriam pro server automaticamente a cada request, custo de
 *   bandwidth desnecessário, e teriam que ser configurados como first-party
 *   com as flags certas. localStorage é mais simples e suficiente porque
 *   só lemos do cliente no momento do signup.
 */

const STORAGE_KEY = "dfeaxis_attribution"

// Campos que aceitamos e limitamos em tamanho.
// Chave fixa que bate com o Pydantic model no backend.
export interface Attribution {
  utm_source?: string | null
  utm_medium?: string | null
  utm_campaign?: string | null
  utm_term?: string | null
  utm_content?: string | null
  gclid?: string | null
  fbclid?: string | null
  referrer?: string | null
  landing_path?: string | null
  captured_at?: string | null // ISO timestamp (debug)
}

// Limite de segurança por campo (alinhado com o schema do backend).
const MAX_FIELD_LENGTH = 255

/**
 * Trunca um valor para o limite máximo e retorna `null` se vier vazio.
 */
function sanitize(value: string | null | undefined): string | null {
  if (!value) return null
  const trimmed = value.trim()
  if (!trimmed) return null
  return trimmed.length > MAX_FIELD_LENGTH
    ? trimmed.slice(0, MAX_FIELD_LENGTH)
    : trimmed
}

/**
 * Lê UTM + click IDs da URL atual e os mescla com qualquer atribuição já
 * guardada em localStorage. Se a URL atual NÃO tiver nenhum UTM nem gclid,
 * mantém a atribuição antiga intacta (o usuário só navegou internamente).
 *
 * Deve ser chamada idealmente na montagem da página raiz (root layout).
 *
 * Retorna a atribuição efetivamente armazenada depois da operação.
 */
export function captureAttribution(): Attribution | null {
  if (typeof window === "undefined") return null

  const params = new URLSearchParams(window.location.search)

  const fromUrl: Attribution = {
    utm_source: sanitize(params.get("utm_source")),
    utm_medium: sanitize(params.get("utm_medium")),
    utm_campaign: sanitize(params.get("utm_campaign")),
    utm_term: sanitize(params.get("utm_term")),
    utm_content: sanitize(params.get("utm_content")),
    gclid: sanitize(params.get("gclid")),
    fbclid: sanitize(params.get("fbclid")),
  }

  // Se nada foi encontrado na URL, mantém o que já existe no storage.
  const hasAnyUrlSignal =
    fromUrl.utm_source ||
    fromUrl.utm_medium ||
    fromUrl.utm_campaign ||
    fromUrl.gclid ||
    fromUrl.fbclid

  if (!hasAnyUrlSignal) {
    return getStoredAttribution()
  }

  // Nova atribuição (last-touch) — reseta tudo.
  const fresh: Attribution = {
    ...fromUrl,
    referrer: sanitize(document.referrer) || null,
    landing_path: sanitize(window.location.pathname + window.location.search) || null,
    captured_at: new Date().toISOString(),
  }

  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(fresh))
  } catch {
    // localStorage pode estar desabilitado (modo privado, quota cheia) —
    // tracking nunca pode quebrar o fluxo de signup.
  }

  return fresh
}

/**
 * Lê a atribuição já armazenada em localStorage. Retorna `null` se nada
 * estiver guardado ou se o storage não estiver acessível.
 */
export function getStoredAttribution(): Attribution | null {
  if (typeof window === "undefined") return null

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Attribution
    if (typeof parsed !== "object" || parsed === null) return null
    return parsed
  } catch {
    return null
  }
}

/**
 * Limpa a atribuição do storage. Chamada opcional — normalmente a gente
 * prefere deixar, pra que futuros eventos (ex: upgrade de plano) ainda
 * possam ser atribuídos ao canal original dentro da mesma sessão.
 */
export function clearAttribution(): void {
  if (typeof window === "undefined") return
  try {
    window.localStorage.removeItem(STORAGE_KEY)
  } catch {
    // noop
  }
}
