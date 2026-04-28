"use client"

import * as React from "react"
import { useSearchParams } from "next/navigation"
import { CheckCircle2 } from "lucide-react"

import { PricingTable } from "@/components/billing/pricing-table"
import { PortalButton } from "@/components/billing/portal-button"
import { useTrial } from "@/hooks/use-trial"

export default function BillingPage() {
  return (
    <React.Suspense fallback={<div className="py-16 text-center text-sm text-slate-500">Carregando...</div>}>
      <BillingPageInner />
    </React.Suspense>
  )
}

function BillingPageInner() {
  const search = useSearchParams()
  const checkoutResult = search?.get("checkout")
  const planChanged = search?.get("plan_changed")
  const { subscriptionStatus, stripePriceId } = useTrial()
  const [error, setError] = React.useState<string | null>(null)

  const isActive = subscriptionStatus === "active"

  return (
    <div className="mx-auto max-w-5xl py-8">
      {/* Success banner after checkout */}
      {checkoutResult === "success" && (
        <div className="mb-6 flex items-center gap-3 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
          <CheckCircle2 className="size-5 text-emerald-600" />
          <div>
            <p className="font-semibold">Pagamento confirmado!</p>
            <p className="text-xs text-emerald-700">
              Sua assinatura está ativa. A captura automática foi liberada.
            </p>
          </div>
        </div>
      )}

      {/* Success banner after plan change */}
      {planChanged === "success" && (
        <div className="mb-6 flex items-center gap-3 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
          <CheckCircle2 className="size-5 text-emerald-600" />
          <div>
            <p className="font-semibold">Plano alterado com sucesso!</p>
            <p className="text-xs text-emerald-700">
              A próxima fatura já refletirá o novo plano (com prorata aplicada).
            </p>
          </div>
        </div>
      )}

      <div className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">
          Planos & Assinatura
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Escolha um plano para liberar a captura automática de documentos fiscais.
        </p>
      </div>

      {/* Active subscription panel */}
      {isActive && (
        <div className="mb-8 rounded-lg border border-slate-200 bg-white p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-semibold text-slate-900">
                Sua assinatura está ativa
              </p>
              <p className="mt-1 text-xs text-slate-500">
                Gerencie seu cartão, baixe invoices ou cancele a qualquer momento.
              </p>
            </div>
            <PortalButton />
          </div>
        </div>
      )}

      {error && (
        <div className="mb-6 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-900">
          {error}
        </div>
      )}

      <PricingTable
        onError={setError}
        subscriptionStatus={subscriptionStatus}
        currentPriceId={stripePriceId}
      />

      <p className="mt-8 text-center text-xs text-slate-500">
        Precisa de mais de 50 CNPJs ou termos personalizados?{" "}
        <a
          href="mailto:contato@dfeaxis.com.br"
          className="font-medium text-emerald-600 hover:underline"
        >
          Fale com a gente
        </a>
        .
      </p>
    </div>
  )
}
