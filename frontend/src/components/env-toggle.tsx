"use client"

import { useState } from "react"
import { useSettings } from "@/hooks/use-settings"
import { apiFetch } from "@/lib/api"
import { Loader2 } from "lucide-react"

export function EnvToggle() {
  const { settings, updateSettings } = useSettings()
  const [updating, setUpdating] = useState(false)

  const current = settings.sefazAmbiente // "1" = prod, "2" = hom

  async function handleChange(next: "1" | "2") {
    if (next === current || updating) return
    setUpdating(true)
    // Optimistic local update so UI reacts immediately
    updateSettings({ sefazAmbiente: next })
    try {
      await apiFetch("/tenants/settings", {
        method: "PATCH",
        body: JSON.stringify({ sefaz_ambiente: parseInt(next, 10) }),
      })
    } catch (e) {
      console.error("[DFeAxis] Falha ao atualizar ambiente:", e)
    } finally {
      setUpdating(false)
    }
  }

  const baseBtn =
    "relative inline-flex items-center justify-center px-3 py-1 text-xs font-medium transition-colors rounded-full"
  const active = "bg-emerald-500 text-white shadow-sm"
  const inactive = "text-muted-foreground hover:text-foreground"

  return (
    <div className="inline-flex items-center gap-1 rounded-full border bg-background p-0.5 shadow-sm">
      <button
        type="button"
        onClick={() => handleChange("2")}
        disabled={updating}
        className={`${baseBtn} ${current === "2" ? active : inactive}`}
        aria-pressed={current === "2"}
      >
        {updating && current !== "2" && (
          <Loader2 className="mr-1 h-3 w-3 animate-spin" />
        )}
        Homologação
      </button>
      <button
        type="button"
        onClick={() => handleChange("1")}
        disabled={updating}
        className={`${baseBtn} ${current === "1" ? active : inactive}`}
        aria-pressed={current === "1"}
      >
        {updating && current !== "1" && (
          <Loader2 className="mr-1 h-3 w-3 animate-spin" />
        )}
        Produção
      </button>
    </div>
  )
}
