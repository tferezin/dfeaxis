"use client"

import Link from "next/link"
import { AlertTriangle, ArrowRight } from "lucide-react"
import { useTrial } from "@/hooks/use-trial"
import { usePendentes } from "@/hooks/use-pendentes"
import { useSettings } from "@/hooks/use-settings"

export function PendentesPanel() {
  const { subscriptionStatus, trialBlockedReason, loading: trialLoading } = useTrial()
  const {
    pendentesNfe,
    pendentesCte,
    pendentesMdfe,
    pendentesNfse,
    total,
    loading: pendLoading,
  } = usePendentes()
  const { settings } = useSettings()

  if (trialLoading || pendLoading) return null
  if (subscriptionStatus === "active") return null

  // Show when trial is blocked OR when there are pendentes and user is on trial
  const isBlocked = trialBlockedReason === "cap" || trialBlockedReason === "time"
  const hasPendentes = total > 0
  if (!isBlocked && !hasPendentes) return null
  if (!hasPendentes) return null

  const ambienteLabel = settings.sefazAmbiente === "1" ? "Produção" : "Homologação"

  return (
    <div className="rounded-xl border border-amber-300 bg-gradient-to-br from-amber-50 to-orange-50 p-4 shadow-sm">
      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-amber-200 text-amber-800">
          <AlertTriangle className="h-5 w-5" />
        </div>
        <div className="flex-1">
          <h3 className="text-sm font-semibold text-amber-900">
            Documentos aguardando captura
          </h3>
          <p className="mt-0.5 text-xs text-amber-800">
            <span className="font-bold">{total.toLocaleString("pt-BR")}</span>{" "}
            documentos identificados na SEFAZ ({ambienteLabel})
            {isBlocked && " — limite do trial atingido"}
          </p>

          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <PendentesItem label="NF-e" value={pendentesNfe} />
            <PendentesItem label="CT-e" value={pendentesCte} />
            <PendentesItem label="MDF-e" value={pendentesMdfe} />
            <PendentesItem label="NFS-e" value={pendentesNfse} />
          </div>

          <div className="mt-3">
            <Link
              href="/financeiro/creditos"
              className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-500 px-3 py-1.5 text-xs font-semibold text-white shadow-sm transition-colors hover:bg-emerald-600"
            >
              Assinar plano e liberar captura
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}

function PendentesItem({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-amber-200 bg-white/70 px-2.5 py-1.5">
      <div className="text-[10px] font-medium uppercase tracking-wide text-amber-700">
        {label}
      </div>
      <div className="text-sm font-bold text-amber-900">
        {value.toLocaleString("pt-BR")}
      </div>
    </div>
  )
}
