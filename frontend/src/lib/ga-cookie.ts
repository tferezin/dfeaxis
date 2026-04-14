/**
 * Extrai o `client_id` do cookie `_ga` setado pelo gtag.js do GA4.
 *
 * Formato do cookie: `GA1.1.XXXXXXXX.YYYYYYYY`
 *   - "GA1.1" = versão
 *   - "XXXXXXXX.YYYYYYYY" = client_id (2 números separados por ponto)
 *
 * Este client_id é o que liga a sessão anônima do visitante (que clicou no
 * anúncio) ao evento `purchase` disparado pelo backend depois que o Stripe
 * confirma o pagamento. Sem ele, o Google Ads não consegue atribuir a
 * conversão ao clique original.
 *
 * Retorna `null` se o cookie não existir (gtag ainda não carregou, usuário
 * com bloqueador de tracking, server-side render, etc). O código que usa
 * essa função deve tolerar `null` graciosamente.
 */
export function getGaClientId(): string | null {
  if (typeof document === "undefined") return null

  // Split robusto — `split("; ")` falha se o browser/servidor usar `;` sem
  // espaço. O regex `/;\s*/` lida com ambos.
  const cookies = document.cookie.split(/;\s*/)
  const gaCookie = cookies.find((c) => c.startsWith("_ga="))
  if (!gaCookie) return null

  const value = gaCookie.substring("_ga=".length)
  // Formato esperado: GA1.1.1234567890.1234567890
  const parts = value.split(".")
  if (parts.length < 4) return null

  // Pega as 2 últimas partes — é o client_id que o GA4 Measurement Protocol
  // espera receber no campo `client_id`.
  return `${parts[parts.length - 2]}.${parts[parts.length - 1]}`
}
