"use client"

import { useEffect, useState } from "react"
import { getSupabase } from "@/lib/supabase"

/**
 * Monthly usage hook — só carrega dados pra tenants com subscription ativa.
 *
 * IMPORTANTE: `docs_included_mes` e `plan` vem do webhook do Stripe. Se o
 * webhook falhar ou a migration 010 não tiver rodado, retornamos 0 e
 * sinalizamos `syncError: true` — consumidores devem mostrar aviso ao
 * usuário em vez de chutar um valor. Fallback silencioso pra plan-defaults
 * foi removido (causava cobrança/exibição incorreta quando Stripe mudava).
 */

interface MonthlyUsage {
  docsConsumidosMes: number
  docsIncludedMes: number
  billingDay: number
  stripePriceId: string | null
  plan: string | null
  /** true quando o tenant tem subscription ativa mas docs_included_mes não
   *  veio do Stripe (webhook pendente ou migration gap). UI deve mostrar
   *  aviso "Sincronizando com Stripe..." em vez de valor chutado. */
  syncError: boolean
  loading: boolean
}

export function useMonthlyUsage(enabled: boolean = true): MonthlyUsage {
  const [usage, setUsage] = useState<MonthlyUsage>({
    docsConsumidosMes: 0,
    docsIncludedMes: 0,
    billingDay: 5,
    stripePriceId: null,
    plan: null,
    syncError: false,
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
            "docs_consumidos_mes, docs_included_mes, billing_day, stripe_price_id, plan, subscription_status"
          )
          .eq("user_id", user.id)
          .single()

        if (error || !data) {
          setUsage((prev) => ({ ...prev, loading: false }))
          return
        }

        const row = data as Record<string, unknown>
        const rawIncluded = (row.docs_included_mes as number) ?? 0
        const planKey = (row.plan as string) ?? null
        const subStatus = (row.subscription_status as string) ?? null

        // syncError: tenant com subscription ativa mas sem docs_included_mes
        // populado — provavelmente webhook do Stripe não processou ainda ou
        // falhou. UI mostra aviso em vez de chutar valor.
        const syncError = subStatus === "active" && rawIncluded <= 0

        setUsage({
          docsConsumidosMes: (row.docs_consumidos_mes as number) ?? 0,
          docsIncludedMes: rawIncluded,
          billingDay: (row.billing_day as number) ?? 5,
          stripePriceId: (row.stripe_price_id as string) ?? null,
          plan: planKey,
          syncError,
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
