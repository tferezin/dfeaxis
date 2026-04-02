"use client"

import { useEffect, useState } from "react"
import { getSupabase } from "@/lib/supabase"

interface TrialStatus {
  trialActive: boolean
  trialExpiresAt: string | null
  daysRemaining: number
  subscriptionStatus: "trial" | "active" | "cancelled" | "expired"
  loading: boolean
}

export function useTrial(): TrialStatus {
  const [status, setStatus] = useState<TrialStatus>({
    trialActive: true,
    trialExpiresAt: null,
    daysRemaining: 7,
    subscriptionStatus: "trial",
    loading: true,
  })

  useEffect(() => {
    async function fetchTrialStatus() {
      try {
        const sb = getSupabase()
        const { data: { user } } = await sb.auth.getUser()
        if (!user) return

        const { data, error } = await sb
          .from("tenants")
          .select("trial_active, trial_expires_at, subscription_status")
          .eq("user_id", user.id)
          .single()

        if (error || !data) return

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
          subscriptionStatus: data.subscription_status ?? "trial",
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
