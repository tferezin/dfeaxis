/**
 * Client-side billing helpers — calls the backend /api/v1/billing/* endpoints.
 *
 * Designed to be plug-and-play across SaaS projects: only depends on
 * `apiFetch` (which already handles auth headers) and types defined here.
 */

import { apiFetch } from "./api"

export interface Plan {
  key: string
  name: string
  description: string
  price_id_monthly: string
  price_id_yearly: string
  monthly_amount_cents: number
  yearly_amount_cents: number
  docs_included: number
  overage_cents_per_doc: number
  max_cnpjs: number
  features: string[]
}

export type BillingPeriod = "monthly" | "yearly"

/** Fetches the configured plans (no auth required). */
export async function listPlans(): Promise<Plan[]> {
  return apiFetch<Plan[]>("/billing/plans")
}

/** Creates a checkout session and returns the redirect URL. */
export async function createCheckoutSession(
  priceId: string
): Promise<{ session_id: string; url: string }> {
  return apiFetch<{ session_id: string; url: string }>("/billing/checkout", {
    method: "POST",
    body: JSON.stringify({ price_id: priceId }),
  })
}

/** Creates a Customer Portal session and returns the redirect URL. */
export async function createPortalSession(): Promise<{
  session_id: string
  url: string
}> {
  return apiFetch<{ session_id: string; url: string }>("/billing/portal", {
    method: "POST",
  })
}

/** Formats cents → BRL string. */
export function formatBRL(cents: number): string {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(cents / 100)
}

/** Returns the per-month price for a given plan + period.
 *  For yearly, divides by 12. */
export function getPerMonthCents(plan: Plan, period: BillingPeriod): number {
  if (period === "monthly") return plan.monthly_amount_cents
  return Math.round(plan.yearly_amount_cents / 12)
}

/** Returns the price_id for a given plan + period. */
export function getPriceId(plan: Plan, period: BillingPeriod): string {
  return period === "monthly" ? plan.price_id_monthly : plan.price_id_yearly
}
