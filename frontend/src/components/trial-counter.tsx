"use client"

import { useTrial } from "@/hooks/use-trial"
import { Gauge } from "lucide-react"

export function TrialCounter() {
  const { subscriptionStatus, docsConsumidos, trialCap, daysRemaining, loading } = useTrial()

  if (loading) return null
  if (subscriptionStatus === "active") return null

  const cap = trialCap || 500
  const pct = Math.min(100, Math.round((docsConsumidos / cap) * 100))

  let barColor = "bg-emerald-500"
  let textColor = "text-emerald-700"
  let bgColor = "bg-emerald-50"
  let borderColor = "border-emerald-200"
  if (pct >= 80) {
    barColor = "bg-red-500"
    textColor = "text-red-700"
    bgColor = "bg-red-50"
    borderColor = "border-red-200"
  } else if (pct >= 50) {
    barColor = "bg-amber-500"
    textColor = "text-amber-700"
    bgColor = "bg-amber-50"
    borderColor = "border-amber-200"
  }

  // Formato combinado: "87 / 500 documentos · 7 dias restantes"
  // O contador avança quando o SAP confirma entrega via /confirmar —
  // não quando a gente captura da SEFAZ. Por isso o texto é neutro
  // ("documentos") e não "capturados".
  const diasText =
    daysRemaining <= 0
      ? "trial expirado"
      : daysRemaining === 1
        ? "1 dia restante"
        : `${daysRemaining} dias restantes`

  return (
    <div className={`rounded-lg border ${borderColor} ${bgColor} px-3 py-2.5`}>
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Gauge className={`h-4 w-4 ${textColor}`} />
          <span className={`text-xs font-semibold ${textColor}`}>
            {docsConsumidos.toLocaleString("pt-BR")} / {cap.toLocaleString("pt-BR")} documentos
            <span className="mx-1.5 opacity-60">·</span>
            {diasText}
          </span>
        </div>
        <span className={`text-xs font-medium ${textColor}`}>{pct}%</span>
      </div>
      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-white/60">
        <div
          className={`h-full ${barColor} transition-all duration-500 ease-out`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}
