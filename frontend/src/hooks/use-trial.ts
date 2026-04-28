"use client"

import { useEffect, useState } from "react"
import { getSupabase } from "@/lib/supabase"

export type SubscriptionStatus = "trial" | "active" | "cancelled" | "expired" | "past_due"
export type TrialBlockedReason = "time" | "cap" | null

interface TrialStatus {
  trialActive: boolean
  trialExpiresAt: string | null
  daysRemaining: number
  subscriptionStatus: SubscriptionStatus
  docsConsumidos: number
  trialCap: number
  trialBlockedReason: TrialBlockedReason
  currentPeriodEnd: string | null
  /** Timestamp ISO da primeira falha de pagamento no ciclo. null se nao esta em past_due. */
  pastDueSince: string | null
  /** Dias restantes antes do bloqueio de escrita (regra 5+5).
   *  - > 0: ainda dentro da tolerancia
   *  - 0: bloqueado (middleware retorna 402 em endpoints de escrita)
   *  - null: nao esta em past_due */
  pastDueDaysRemaining: number | null
  /** true = cliente no soft block (past_due ha mais de 5 dias) */
  isPaymentBlocked: boolean
  /** Stripe price_id do plano atual (apenas pra subscriptionStatus=active|past_due). */
  stripePriceId: string | null
  loading: boolean
}

export function useTrial(): TrialStatus {
  const [status, setStatus] = useState<TrialStatus>({
    trialActive: true,
    trialExpiresAt: null,
    daysRemaining: 10,
    subscriptionStatus: "trial",
    docsConsumidos: 0,
    trialCap: 500,
    trialBlockedReason: null,
    currentPeriodEnd: null,
    pastDueSince: null,
    pastDueDaysRemaining: null,
    isPaymentBlocked: false,
    stripePriceId: null,
    loading: true,
  })

  useEffect(() => {
    async function fetchTrialStatus() {
      try {
        const sb = getSupabase()
        const { data: { user } } = await sb.auth.getUser()
        if (!user) {
          setStatus((prev) => ({ ...prev, loading: false }))
          return
        }

        // Essential columns only — exist since migration 007.
        // Monthly-usage fields live in useMonthlyUsage() to avoid coupling
        // trial state to migrations that may not be applied in all envs.
        const { data, error } = await sb
          .from("tenants")
          .select(
            "trial_active, trial_expires_at, subscription_status, docs_consumidos_trial, trial_cap, trial_blocked_reason, current_period_end, past_due_since, stripe_price_id"
          )
          .eq("user_id", user.id)
          .single()

        if (error || !data) {
          setStatus((prev) => ({ ...prev, loading: false }))
          return
        }

        const now = new Date()
        const expiresAt = data.trial_expires_at
          ? new Date(data.trial_expires_at)
          : null
        const diffMs = expiresAt ? expiresAt.getTime() - now.getTime() : 0
        const daysRemaining = Math.max(0, Math.ceil(diffMs / (1000 * 60 * 60 * 24)))

        // Calcula countdown do dunning (regra 5+5)
        const pastDueRaw = (data as Record<string, unknown>).past_due_since as string | null
        let pastDueDaysRemaining: number | null = null
        let isPaymentBlocked = false
        if (pastDueRaw) {
          const pastDueDate = new Date(pastDueRaw)
          const daysSince = Math.floor(
            (now.getTime() - pastDueDate.getTime()) / (1000 * 60 * 60 * 24)
          )
          pastDueDaysRemaining = Math.max(0, 5 - daysSince)
          isPaymentBlocked = daysSince > 5
        }

        setStatus({
          trialActive: data.trial_active ?? false,
          trialExpiresAt: data.trial_expires_at,
          daysRemaining,
          subscriptionStatus: (data.subscription_status ?? "trial") as SubscriptionStatus,
          docsConsumidos: data.docs_consumidos_trial ?? 0,
          trialCap: data.trial_cap ?? 500,
          trialBlockedReason: (data.trial_blocked_reason ?? null) as TrialBlockedReason,
          currentPeriodEnd: data.current_period_end ?? null,
          pastDueSince: pastDueRaw,
          pastDueDaysRemaining,
          isPaymentBlocked,
          stripePriceId: ((data as Record<string, unknown>).stripe_price_id as string | null) ?? null,
          loading: false,
        })
      } catch {
        setStatus((prev) => ({ ...prev, loading: false }))
      }
    }

    fetchTrialStatus()
  }, [])

  return status
}
