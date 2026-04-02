"use client"

import { ShieldAlert, Mail } from "lucide-react"

export function TrialExpiredOverlay() {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="mx-4 w-full max-w-md rounded-xl bg-white p-8 shadow-2xl text-center">
        <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-red-100">
          <ShieldAlert className="h-8 w-8 text-red-600" />
        </div>
        <h2 className="mb-2 text-xl font-bold text-gray-900">
          Seu periodo de teste de 7 dias expirou
        </h2>
        <p className="mb-6 text-sm text-gray-600">
          Para continuar usando o DFeAxis, realize o pagamento via PIX.
        </p>
        <a
          href="mailto:contato@dfeaxis.com.br"
          className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-6 py-3 text-sm font-medium text-white hover:bg-emerald-700 transition-colors"
        >
          <Mail className="h-4 w-4" />
          Falar com suporte
        </a>
        <p className="mt-4 text-xs text-gray-400">
          contato@dfeaxis.com.br
        </p>
      </div>
    </div>
  )
}
