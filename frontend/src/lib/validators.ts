import { unmaskPhone } from "./masks"

/**
 * Validates a Brazilian phone number.
 * Accepts 10 digits (landline) or 11 digits (mobile) after stripping mask.
 * Also checks that the DDD is in the valid range (11-99).
 */
export function isValidBrazilianPhone(value: string): boolean {
  const digits = unmaskPhone(value)
  if (digits.length !== 10 && digits.length !== 11) return false
  const ddd = parseInt(digits.slice(0, 2), 10)
  if (isNaN(ddd) || ddd < 11) return false
  // For 11-digit mobile numbers, the first digit after DDD must be 9
  if (digits.length === 11 && digits[2] !== "9") return false
  return true
}
