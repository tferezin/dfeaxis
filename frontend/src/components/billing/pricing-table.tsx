"use client"

import * as React from "react"
import { Check, Loader2 } from "lucide-react"

import {
  type Plan,
  type BillingPeriod,
  formatBRL,
  getPerMonthCents,
  getPriceId,
  createCheckoutSession,
  changePlan,
  listPlans,
} from "@/lib/billing"

interface PricingTableProps {
  /** Plano destacado (badge "Mais popular") */
  popular?: string
  /** Callback quando ocorre erro no checkout */
  onError?: (msg: string) => void
  /** Se o tenant ja paga ('active' ou 'past_due'), usamos /change-plan em vez
   *  de /checkout — caso contrario o cliente acaba com 2 subscriptions na Stripe.
   *  Default: undefined (cliente novo, fluxo de checkout). */
  subscriptionStatus?: string | null
  /** price_id do plano atual do cliente (se pagante) — usado pra desabilitar
   *  botao do plano atual e indicar visualmente. */
  currentPriceId?: string | null
}

export function PricingTable({
  popular = "business",
  onError,
  subscriptionStatus,
  currentPriceId,
}: PricingTableProps) {
  const [plans, setPlans] = React.useState<Plan[]>([])
  const [loading, setLoading] = React.useState(true)
  const [period, setPeriod] = React.useState<BillingPeriod>("monthly")
  const [checkoutLoading, setCheckoutLoading] = React.useState<string | null>(null)

  const isExistingSubscriber =
    subscriptionStatus === "active" || subscriptionStatus === "past_due"

  React.useEffect(() => {
    listPlans()
      .then(setPlans)
      .catch((e) => {
        console.error("Failed to load plans", e)
        onError?.("Falha ao carregar planos")
      })
      .finally(() => setLoading(false))
  }, [onError])

  // Extrai mensagem amigavel do erro do backend. apiFetch encapsula como
  // `Error("API error {status}: {body}")` e o body eh JSON com `detail`.
  const extractBackendMessage = (err: unknown, fallback: string): string => {
    if (!(err instanceof Error)) return fallback
    const match = err.message.match(/^API error \d+:\s*(.+)$/)
    if (!match) return err.message || fallback
    try {
      const parsed = JSON.parse(match[1])
      const detail = parsed?.detail
      if (typeof detail === "string" && detail) return detail
      if (detail && typeof detail.message === "string") return detail.message
    } catch {
      /* body nao era JSON */
    }
    return fallback
  }

  const handleSelectPlan = async (plan: Plan) => {
    const priceId = getPriceId(plan, period)
    if (!priceId) {
      onError?.("Plano sem price configurado. Rode o seed do Stripe.")
      return
    }
    setCheckoutLoading(plan.key)
    try {
      if (isExistingSubscriber) {
        // Cliente ja pagante → /billing/change-plan via Stripe.Subscription.modify
        await changePlan(priceId)
        // Sucesso — recarrega pra refletir novo plano (subscription_status,
        // max_cnpjs, docs_included etc vem via webhook)
        window.location.href = "/financeiro/creditos?plan_changed=success"
        return
      }

      // Cliente novo (trial/cancelled/expired) → /billing/checkout
      let billingDay: number | undefined
      if (typeof window !== "undefined") {
        const stored = window.sessionStorage.getItem("dfeaxis:billing_day")
        if (stored) {
          const parsed = parseInt(stored, 10)
          if ([5, 10, 15].includes(parsed)) billingDay = parsed
        }
      }
      const session = await createCheckoutSession(priceId, billingDay)
      window.location.href = session.url
    } catch (e) {
      console.error("Plan selection failed", e)
      onError?.(extractBackendMessage(e, "Erro ao processar plano"))
      setCheckoutLoading(null)
    }
  }

  if (loading) {
    return (
      <div className="flex justify-center py-16">
        <Loader2 className="size-6 animate-spin text-emerald-600" />
      </div>
    )
  }

  if (plans.length === 0) {
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50 p-6 text-center">
        <p className="text-sm text-amber-900">
          Nenhum plano configurado. Execute{" "}
          <code className="rounded bg-amber-100 px-1 py-0.5 text-xs">
            python scripts/seed_stripe_products.py
          </code>{" "}
          no backend.
        </p>
      </div>
    )
  }

  return (
    <div>
      {/* Period toggle */}
      <div className="mb-8 flex items-center justify-center gap-3">
        <button
          type="button"
          onClick={() => setPeriod("monthly")}
          className={`text-sm font-semibold transition-colors ${
            period === "monthly" ? "text-slate-900" : "text-slate-400"
          }`}
        >
          Mensal
        </button>
        <button
          type="button"
          onClick={() => setPeriod(period === "monthly" ? "yearly" : "monthly")}
          aria-label="Alternar período de cobrança"
          className="relative h-7 w-12 rounded-full bg-emerald-600 transition-colors"
        >
          <span
            className={`absolute top-1 h-5 w-5 rounded-full bg-white shadow-sm transition-transform ${
              period === "yearly" ? "translate-x-6" : "translate-x-1"
            }`}
          />
        </button>
        <button
          type="button"
          onClick={() => setPeriod("yearly")}
          className={`text-sm font-semibold transition-colors ${
            period === "yearly" ? "text-slate-900" : "text-slate-400"
          }`}
        >
          Anual
        </button>
        <span className="ml-2 rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-bold text-emerald-700">
          -20%
        </span>
      </div>

      {/* Plans grid */}
      <div className="grid gap-6 md:grid-cols-3">
        {plans.map((plan) => {
          const isPopular = plan.key === popular
          const monthlyCents = getPerMonthCents(plan, period)
          const isLoading = checkoutLoading === plan.key
          const planPriceId = getPriceId(plan, period)
          const isCurrentPlan =
            isExistingSubscriber &&
            !!currentPriceId &&
            !!planPriceId &&
            currentPriceId === planPriceId

          return (
            <div
              key={plan.key}
              className={`relative flex flex-col rounded-2xl border bg-white p-6 shadow-sm transition-shadow hover:shadow-md ${
                isPopular ? "border-emerald-500 ring-2 ring-emerald-100" : "border-slate-200"
              }`}
            >
              {isPopular && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-emerald-600 px-3 py-1 text-xs font-bold uppercase tracking-wide text-white shadow-sm">
                  Mais popular
                </div>
              )}

              <h3 className="text-lg font-semibold text-slate-900">{plan.name}</h3>
              <p className="mt-1 min-h-[40px] text-sm text-slate-500">{plan.description}</p>

              <div className="mt-5 flex items-baseline gap-1">
                <span className="text-4xl font-bold text-slate-900">
                  {formatBRL(monthlyCents)}
                </span>
                <span className="text-sm text-slate-500">/mês</span>
              </div>
              {period === "yearly" && (
                <p className="mt-1 text-xs text-slate-500">
                  Cobrado anualmente: {formatBRL(plan.yearly_amount_cents)}
                </p>
              )}

              <div className="my-5 h-px bg-slate-100" />

              <ul className="space-y-2.5">
                {plan.features.map((feature) => (
                  <li key={feature} className="flex items-start gap-2 text-sm text-slate-700">
                    <Check className="mt-0.5 size-4 shrink-0 text-emerald-600" />
                    <span>{feature}</span>
                  </li>
                ))}
              </ul>

              <button
                type="button"
                onClick={() => handleSelectPlan(plan)}
                disabled={isLoading || isCurrentPlan}
                className={`mt-6 inline-flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                  isCurrentPlan
                    ? "border border-emerald-200 bg-emerald-50 text-emerald-700"
                    : isPopular
                    ? "bg-emerald-600 text-white hover:bg-emerald-700"
                    : "border border-slate-200 bg-white text-slate-900 hover:bg-slate-50"
                }`}
              >
                {isLoading ? (
                  <>
                    <Loader2 className="size-4 animate-spin" />
                    {isExistingSubscriber ? "Alterando..." : "Redirecionando..."}
                  </>
                ) : isCurrentPlan ? (
                  "Plano atual"
                ) : isExistingSubscriber ? (
                  `Mudar para ${plan.name}`
                ) : (
                  "Assinar agora"
                )}
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
