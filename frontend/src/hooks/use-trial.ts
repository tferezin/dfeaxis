"use client"

import { useEffect, useState } from "react"
import { getSupabase } from "@/lib/supabase"

export type SubscriptionStatus = "trial" | "active" | "cancelled" | "expired"
export type TrialBlockedReason = "time" | "cap" | null

interface TrialStatus {
  trialActive: boolean
  trialExpiresAt: string | null
  daysRemaining: number
  subscriptionStatus: SubscriptionStatus
  docsConsumidos: number
  trialCap: number
  trialBlockedReason: TrialBlockedReason
  docsConsumidosMes: number
  docsIncludedMes: number
  billingDay: number
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
    docsConsumidosMes: 0,
    docsIncludedMes: 0,
    billingDay: 5,
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

        const { data, error } = await sb
          .from("tenants")
          .select(
            "trial_active, trial_expires_at, subscription_status, docs_consumidos_trial, trial_cap, trial_blocked_reason, docs_consumidos_mes, docs_included_mes, billing_day, stripe_price_id"
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

        setStatus({
          trialActive: data.trial_active ?? false,
          trialExpiresAt: data.trial_expires_at,
          daysRemaining,
          subscriptionStatus: (data.subscription_status ?? "trial") as SubscriptionStatus,
          docsConsumidos: data.docs_consumidos_trial ?? 0,
          trialCap: data.trial_cap ?? 500,
          trialBlockedReason: (data.trial_blocked_reason ?? null) as TrialBlockedReason,
          docsConsumidosMes: data.docs_consumidos_mes ?? 0,
          docsIncludedMes: data.docs_included_mes ?? 0,
          billingDay: data.billing_day ?? 5,
          stripePriceId: data.stripe_price_id ?? null,
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
