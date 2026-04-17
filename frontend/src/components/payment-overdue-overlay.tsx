"use client"

import Link from "next/link"
import { CreditCard, Mail, ArrowRight } from "lucide-react"
import { useReadOnly } from "@/contexts/read-only-context"

/**
 * Payment-overdue card. Same layout pattern as TrialExpiredOverlay —
 * overlays only the main content area, leaving sidebar and header usable.
 *
 * Shown when subscription_status === "past_due" and current_period_end
 * has passed (grace period over).
 */
export function PaymentOverdueOverlay() {
  useReadOnly()

  return (
    <div className="pointer-events-none absolute inset-0 z-40 flex items-center justify-center p-6">
      <div className="pointer-events-auto absolute inset-0 bg-slate-900/50 backdrop-blur-sm" />

      <div
        role="alertdialog"
        aria-labelledby="payment-overdue-title"
        className="pointer-events-auto relative mx-auto w-full max-w-xl rounded-2xl border border-slate-200 bg-white p-8 shadow-2xl"
        style={{ maxHeight: "min(70vh, 640px)" }}
      >
        <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-full bg-amber-100">
          <CreditCard className="h-7 w-7 text-amber-600" />
        </div>

        <h2
          id="payment-overdue-title"
          className="mb-3 text-center text-xl font-bold text-slate-900"
        >
          Pagamento pendente
        </h2>

        <p className="mb-5 text-center text-sm text-slate-600">
          Sua fatura está vencida. Regularize o pagamento para reativar o
          acesso às funcionalidades da plataforma. Seus dados estão
          preservados e serão liberados assim que o pagamento for confirmado.
        </p>

        <div className="mb-5 rounded-lg border border-amber-100 bg-amber-50 p-3 text-center text-xs text-amber-800">
          Assim que o pagamento for confirmado, o acesso será reativado
          automaticamente.
        </div>

        <div className="flex flex-col items-center gap-2">
          <Link
            href="/financeiro/creditos"
            className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 px-5 py-3 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-emerald-700"
          >
            Regularizar pagamento
            <ArrowRight className="h-4 w-4" />
          </Link>
          <a
            href="mailto:contato@dfeaxis.com.br"
            className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-5 py-2 text-xs font-medium text-slate-700 transition-colors hover:bg-slate-50"
          >
            <Mail className="h-3.5 w-3.5" />
            Falar com suporte
          </a>
        </div>
      </div>
    </div>
  )
}
