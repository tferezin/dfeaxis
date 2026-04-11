"use client"

import * as React from "react"
import { ExternalLink, Loader2 } from "lucide-react"

import { createPortalSession } from "@/lib/billing"

interface PortalButtonProps {
  className?: string
  children?: React.ReactNode
}

export function PortalButton({ className, children }: PortalButtonProps) {
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  const handleClick = async () => {
    setLoading(true)
    setError(null)
    try {
      const session = await createPortalSession()
      window.location.href = session.url
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Erro ao abrir portal"
      // Most common error: tenant has no Stripe customer yet (never checked out)
      if (msg.includes("no Stripe customer")) {
        setError("Você precisa assinar um plano antes de acessar o portal.")
      } else {
        setError(msg)
      }
      setLoading(false)
    }
  }

  return (
    <div>
      <button
        type="button"
        onClick={handleClick}
        disabled={loading}
        className={
          className ||
          "inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 disabled:opacity-50"
        }
      >
        {loading ? (
          <Loader2 className="size-4 animate-spin" />
        ) : (
          <ExternalLink className="size-4" />
        )}
        {children || "Gerenciar assinatura"}
      </button>
      {error && (
        <p className="mt-2 text-xs text-red-600">{error}</p>
      )}
    </div>
  )
}
