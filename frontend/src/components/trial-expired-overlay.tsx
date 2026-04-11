"use client"

import Link from "next/link"
import { ShieldAlert, Mail, ArrowRight } from "lucide-react"
import { useReadOnly } from "@/contexts/read-only-context"

/**
 * Trial-blocked card. NOT a full-screen modal — it overlays only the main
 * content area, leaving the sidebar and header usable so the user can still
 * navigate to billing, settings, or history.
 *
 * Render this inside the scrollable <main> container (positioned absolute).
 */
export function TrialExpiredOverlay() {
  const { reason } = useReadOnly()

  const title =
    reason === "cap"
      ? "Você atingiu o limite do trial"
      : reason === "time"
        ? "Seu período de teste terminou"
        : "Acesso bloqueado"

  const description =
    reason === "cap"
      ? "Você atingiu o limite de 500 documentos do trial. Para liberar a captura de novos documentos, escolha um plano."
      : reason === "time"
        ? "Seu período de teste de 10 dias terminou. Para continuar capturando documentos, escolha um plano."
        : "Seu acesso de teste está encerrado. Escolha um plano para continuar capturando documentos."

  return (
    <div className="pointer-events-none absolute inset-0 z-40 flex items-center justify-center p-6">
      {/* Backdrop — covers only the content area, not the sidebar/header */}
      <div className="pointer-events-auto absolute inset-0 bg-slate-900/50 backdrop-blur-sm" />

      {/* Card */}
      <div
        role="alertdialog"
        aria-labelledby="trial-blocked-title"
        className="pointer-events-auto relative mx-auto w-full max-w-xl rounded-2xl border border-slate-200 bg-white p-8 shadow-2xl"
        style={{ maxHeight: "min(60vh, 560px)" }}
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

        <p className="mb-6 text-center text-sm text-slate-600">{description}</p>

        <div className="mb-5 rounded-lg border border-emerald-100 bg-emerald-50 p-4 text-center text-xs text-emerald-800">
          Você continua podendo navegar, consultar o histórico e configurar
          a cobrança. Assim que o pagamento for confirmado, a captura será
          reativada automaticamente.
        </div>

        <div className="flex flex-col items-center gap-2 sm:flex-row sm:justify-center">
          <Link
            href="/financeiro/creditos"
            className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-emerald-700 sm:w-auto"
          >
            Ver planos
            <ArrowRight className="h-4 w-4" />
          </Link>
          <a
            href="mailto:contato@dfeaxis.com.br"
            className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-5 py-2.5 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 sm:w-auto"
          >
            <Mail className="h-4 w-4" />
            Falar com suporte
          </a>
        </div>
      </div>
    </div>
  )
}
