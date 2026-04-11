/**
 * Brazilian input masks. Pure functions, no React hooks.
 */

/**
 * Strips all non-numeric characters from a phone string.
 */
export function unmaskPhone(value: string): string {
  return (value || "").replace(/\D/g, "")
}

/**
 * Applies a Brazilian phone mask.
 *
 * - 11 digits (mobile): (XX) XXXXX-XXXX
 * - 10 digits (landline): (XX) XXXX-XXXX
 *
 * Handles partial input progressively so the field feels natural while typing.
 * Extra digits beyond 11 are discarded.
 *
 * Examples:
 *   formatPhone("11999999999") -> "(11) 99999-9999"
 *   formatPhone("1133334444")  -> "(11) 3333-4444"
 *   formatPhone("119")         -> "(11) 9"
 */
export function formatPhone(value: string): string {
  const digits = unmaskPhone(value).slice(0, 11)

  if (digits.length === 0) return ""
  if (digits.length < 3) return `(${digits}`
  if (digits.length < 7) {
    return `(${digits.slice(0, 2)}) ${digits.slice(2)}`
  }
  if (digits.length <= 10) {
    // Landline: (XX) XXXX-XXXX
    return `(${digits.slice(0, 2)}) ${digits.slice(2, 6)}-${digits.slice(6)}`
  }
  // Mobile: (XX) XXXXX-XXXX
  return `(${digits.slice(0, 2)}) ${digits.slice(2, 7)}-${digits.slice(7)}`
}
