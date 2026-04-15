"use client"

import { useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { ShieldAlert, Mail, ArrowRight, CalendarDays } from "lucide-react"
import { useReadOnly } from "@/contexts/read-only-context"

/**
 * Trial-blocked card. NOT a full-screen modal — it overlays only the main
 * content area, leaving the sidebar and header usable so the user can still
 * navigate to billing, settings, or history.
 *
 * Render this inside the scrollable <main> container (positioned absolute).
 */
export function TrialExpiredOverlay() {
  useReadOnly() // mantém o contexto ativo mesmo não usando reason aqui
  const router = useRouter()
  const [billingDay, setBillingDay] = useState<5 | 10 | 15>(5)

  // Mensagem unificada acordada 2026-04-15: uma só copy pra cap e tempo.
  // Motivo: cliente entende melhor e a call-to-action é idêntica.
  const title = "Limite do período de teste atingido"
  const description =
    "Limite do período de teste atingido (500 documentos ou 10 dias). Assine um plano para continuar ativo em nossa plataforma."

  const handleAddPayment = () => {
    // Persist billing day so the pricing table can forward it to
    // createCheckoutSession when the user picks a plan.
    if (typeof window !== "undefined") {
      window.sessionStorage.setItem("dfeaxis:billing_day", String(billingDay))
    }
    router.push("/financeiro/creditos")
  }

  return (
    <div className="pointer-events-none absolute inset-0 z-40 flex items-center justify-center p-6">
      {/* Backdrop — covers only the content area, not the sidebar/header */}
      <div className="pointer-events-auto absolute inset-0 bg-slate-900/50 backdrop-blur-sm" />

      {/* Card */}
      <div
        role="alertdialog"
        aria-labelledby="trial-blocked-title"
        className="pointer-events-auto relative mx-auto w-full max-w-xl rounded-2xl border border-slate-200 bg-white p-8 shadow-2xl"
        style={{ maxHeight: "min(70vh, 640px)" }}
      >
        <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-full bg-red-100">
          <ShieldAlert className="h-7 w-7 text-red-600" />
        </div>

        <h2
          id="trial-blocked-title"
          className="mb-3 text-center text-xl font-bold text-slate-900"
        >
          {title}
        </h2>

        <p className="mb-5 text-center text-sm text-slate-600">{description}</p>

        {/* Billing day selector */}
        <div className="mb-5 rounded-lg border border-slate-200 bg-slate-50 p-4">
          <label
            htmlFor="billing-day"
            className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-600"
          >
            <CalendarDays className="h-3.5 w-3.5" />
            Dia preferido de cobrança
          </label>
          <div className="grid grid-cols-3 gap-2" role="radiogroup" aria-labelledby="billing-day">
            {([5, 10, 15] as const).map((day) => {
              const selected = billingDay === day
              return (
                <button
                  key={day}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  onClick={() => setBillingDay(day)}
                  className={`rounded-lg border px-3 py-2 text-sm font-semibold transition-colors ${
                    selected
                      ? "border-emerald-600 bg-emerald-600 text-white shadow-sm"
                      : "border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50"
                  }`}
                >
                  Dia {day}
                </button>
              )
            })}
          </div>
          <p className="mt-2 text-[11px] text-slate-500">
            Sua fatura mensal será emitida sempre neste dia.
          </p>
        </div>

        <div className="mb-5 rounded-lg border border-emerald-100 bg-emerald-50 p-3 text-center text-xs text-emerald-800">
          Assim que o pagamento for confirmado, a captura será reativada
          automaticamente.
        </div>

        <div className="flex flex-col items-center gap-2">
          <button
            type="button"
            onClick={handleAddPayment}
            className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 px-5 py-3 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-emerald-700"
          >
            Adicionar pagamento e continuar
            <ArrowRight className="h-4 w-4" />
          </button>
          <div className="flex w-full flex-col items-center gap-2 sm:flex-row sm:justify-center">
            <Link
              href="/financeiro/creditos"
              className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-5 py-2 text-xs font-medium text-slate-700 transition-colors hover:bg-slate-50 sm:w-auto"
            >
              Ver planos
            </Link>
            <a
              href="mailto:contato@dfeaxis.com.br"
              className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-5 py-2 text-xs font-medium text-slate-700 transition-colors hover:bg-slate-50 sm:w-auto"
            >
              <Mail className="h-3.5 w-3.5" />
              Falar com suporte
            </a>
          </div>
        </div>
      </div>
    </div>
  )
}
