"use client"

import { useEffect, useState } from "react"
import { getSupabase } from "@/lib/supabase"

/**
 * Monthly usage hook — only loads data for tenants with an active subscription.
 * Resilient to missing columns: if migration 010 isn't applied, returns zeros
 * and loading=false without crashing.
 */

/** Default docs_included per plan when the tenant field is 0 (migration gap) */
const PLAN_DEFAULTS: Record<string, number> = {
  starter: 3000,
  business: 8000,
  enterprise: 20000,
}

interface MonthlyUsage {
  docsConsumidosMes: number
  docsIncludedMes: number
  billingDay: number
  stripePriceId: string | null
  plan: string | null
  loading: boolean
}

export function useMonthlyUsage(enabled: boolean = true): MonthlyUsage {
  const [usage, setUsage] = useState<MonthlyUsage>({
    docsConsumidosMes: 0,
    docsIncludedMes: 0,
    billingDay: 5,
    stripePriceId: null,
    plan: null,
    loading: enabled,
  })

  useEffect(() => {
    if (!enabled) {
      setUsage((prev) => ({ ...prev, loading: false }))
      return
    }

    async function fetch() {
      try {
        const sb = getSupabase()
        const { data: { user } } = await sb.auth.getUser()
        if (!user) {
          setUsage((prev) => ({ ...prev, loading: false }))
          return
        }

        const { data, error } = await sb
          .from("tenants")
          .select(
            "docs_consumidos_mes, docs_included_mes, billing_day, stripe_price_id, plan"
          )
          .eq("user_id", user.id)
          .single()

        if (error || !data) {
          // Migration may not be applied — fail silently with defaults
          setUsage((prev) => ({ ...prev, loading: false }))
          return
        }

        const row = data as Record<string, unknown>
        const rawIncluded = (row.docs_included_mes as number) ?? 0
        const planKey = (row.plan as string) ?? "starter"
        // If docs_included_mes is 0, fall back to plan defaults
        const resolvedIncluded =
          rawIncluded > 0 ? rawIncluded : (PLAN_DEFAULTS[planKey] ?? 3000)

        setUsage({
          docsConsumidosMes: (row.docs_consumidos_mes as number) ?? 0,
          docsIncludedMes: resolvedIncluded,
          billingDay: (row.billing_day as number) ?? 5,
          stripePriceId: (row.stripe_price_id as string) ?? null,
          plan: planKey,
          loading: false,
        })
      } catch {
        setUsage((prev) => ({ ...prev, loading: false }))
      }
    }

    fetch()
  }, [enabled])

  return usage
}
