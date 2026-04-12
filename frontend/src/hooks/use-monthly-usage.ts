"use client"

import { useEffect, useState } from "react"
import { getSupabase } from "@/lib/supabase"

/**
 * Monthly usage hook — only loads data for tenants with an active subscription.
 * Resilient to missing columns: if migration 010 isn't applied, returns zeros
 * and loading=false without crashing.
 */

interface MonthlyUsage {
  docsConsumidosMes: number
  docsIncludedMes: number
  billingDay: number
  stripePriceId: string | null
  loading: boolean
}

export function useMonthlyUsage(enabled: boolean = true): MonthlyUsage {
  const [usage, setUsage] = useState<MonthlyUsage>({
    docsConsumidosMes: 0,
    docsIncludedMes: 0,
    billingDay: 5,
    stripePriceId: null,
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
            "docs_consumidos_mes, docs_included_mes, billing_day, stripe_price_id"
          )
          .eq("user_id", user.id)
          .single()

        if (error || !data) {
          // Migration may not be applied — fail silently with defaults
          setUsage((prev) => ({ ...prev, loading: false }))
          return
        }

        setUsage({
          docsConsumidosMes: (data as Record<string, unknown>).docs_consumidos_mes as number ?? 0,
          docsIncludedMes: (data as Record<string, unknown>).docs_included_mes as number ?? 0,
          billingDay: (data as Record<string, unknown>).billing_day as number ?? 5,
          stripePriceId: (data as Record<string, unknown>).stripe_price_id as string ?? null,
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
