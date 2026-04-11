"use client"

import Link from "next/link"
import { useTrial } from "@/hooks/use-trial"
import { useReadOnly } from "@/contexts/read-only-context"
import { Clock, AlertTriangle, Lock } from "lucide-react"

/**
 * Top banner communicating trial state.
 *
 * Variants:
 *  - Blocked (any reason): red "Trial bloqueado. Assine para continuar."
 *  - Trial active, ≤ 3 days remaining: red warning
 *  - Trial active, cap ≥ 80%: amber cap warning
 *  - Trial active, > 3 days remaining: amber countdown
 *  - Paid/active: hidden
 */
export function TrialBanner() {
  const trial = useTrial() as ReturnType<typeof useTrial> & {
    docsConsumidos?: number
    trialCap?: number
    trialBlockedReason?: "time" | "cap" | null
  }
  const { isReadOnly } = useReadOnly()

  if (trial.loading) return null
  if (trial.subscriptionStatus === "active") return null

  const docsConsumidos = trial.docsConsumidos ?? 0
  const trialCap = trial.trialCap ?? 500
  const capPct = trialCap > 0 ? (docsConsumidos / trialCap) * 100 : 0

  // 1) Blocked state — highest priority
  if (isReadOnly) {
    return (
      <div className="flex items-center justify-between gap-3 border-b border-red-200 bg-red-50 px-6 py-3 text-sm text-red-800">
        <div className="flex items-center gap-2">
          <Lock className="h-4 w-4 shrink-0" />
          <span className="font-medium">
            Trial bloqueado. Assine para continuar capturando documentos.
          </span>
        </div>
        <Link
          href="/financeiro/creditos"
          className="shrink-0 rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-red-700"
        >
          Assinar plano
        </Link>
      </div>
    )
  }

  // 2) Trial active + ≤ 3 days remaining → red
  if (trial.daysRemaining <= 3) {
    return (
      <div className="flex items-center justify-between gap-3 border-b border-red-200 bg-red-50 px-6 py-3 text-sm text-red-800">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span className="font-medium">
            {trial.daysRemaining <= 0
              ? "Seu trial expira hoje — assine agora."
              : `Seu trial expira em ${trial.daysRemaining} ${trial.daysRemaining === 1 ? "dia" : "dias"} — assine agora.`}
          </span>
        </div>
        <Link
          href="/financeiro/creditos"
          className="shrink-0 rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-red-700"
        >
          Ver planos
        </Link>
      </div>
    )
  }

  // 3) Trial active + cap ≥ 80% → amber
  if (capPct >= 80) {
    return (
      <div className="flex items-center justify-between gap-3 border-b border-amber-200 bg-amber-50 px-6 py-3 text-sm text-amber-800">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>
            Você atingiu{" "}
            <span className="font-semibold">
              {Math.floor(capPct)}% do limite de documentos
            </span>{" "}
            do trial ({docsConsumidos}/{trialCap}).
          </span>
        </div>
        <Link
          href="/financeiro/creditos"
          className="shrink-0 rounded-md bg-amber-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-amber-700"
        >
          Ver planos
        </Link>
      </div>
    )
  }

  // 4) Trial active + > 3 days → amber countdown
  return (
    <div className="flex items-center gap-2 border-b border-amber-200 bg-amber-50 px-6 py-3 text-sm text-amber-800">
      <Clock className="h-4 w-4 shrink-0" />
      <span>
        Seu trial expira em{" "}
        <span className="font-semibold">{trial.daysRemaining} dias</span>.
      </span>
    </div>
  )
}
