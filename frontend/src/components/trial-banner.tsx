"use client"

import { useTrial } from "@/hooks/use-trial"
import { Clock, AlertTriangle } from "lucide-react"

export function TrialBanner() {
  const { trialActive, daysRemaining, subscriptionStatus, loading } = useTrial()

  if (loading) return null
  if (subscriptionStatus === "active") return null

  // Expired
  if (subscriptionStatus === "expired" || (!trialActive && subscriptionStatus === "trial")) {
    return (
      <div className="flex items-center justify-between gap-3 bg-red-50 border-b border-red-200 px-6 py-3 text-red-800 text-sm">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span className="font-medium">
            Periodo de teste expirado. Realize o pagamento para continuar.
          </span>
        </div>
        <a
          href="mailto:contato@dfeaxis.com.br"
          className="shrink-0 rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700 transition-colors"
        >
          Falar com suporte
        </a>
      </div>
    )
  }

  // Last day
  if (daysRemaining <= 1) {
    return (
      <div className="flex items-center gap-2 bg-red-50 border-b border-red-200 px-6 py-3 text-red-800 text-sm">
        <AlertTriangle className="h-4 w-4 shrink-0" />
        <span className="font-medium">
          Seu periodo de teste expira hoje!
        </span>
      </div>
    )
  }

  // Trial active, more than 1 day
  return (
    <div className="flex items-center gap-2 bg-amber-50 border-b border-amber-200 px-6 py-3 text-amber-800 text-sm">
      <Clock className="h-4 w-4 shrink-0" />
      <span>
        Seu periodo de teste expira em{" "}
        <span className="font-semibold">{daysRemaining} dias</span>.
        Realize o pagamento para continuar.
      </span>
    </div>
  )
}
