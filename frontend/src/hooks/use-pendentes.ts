"use client"

import { useEffect, useState, useCallback } from "react"
import { getSupabase } from "@/lib/supabase"
import { useSettings } from "@/hooks/use-settings"

interface PendentesData {
  pendentesNfe: number
  pendentesCte: number
  pendentesMdfe: number
  pendentesNfse: number
  total: number
  loading: boolean
  reload: () => void
}

export function usePendentes(): PendentesData {
  const { settings } = useSettings()
  const ambiente = parseInt(settings.sefazAmbiente, 10)

  const [data, setData] = useState<Omit<PendentesData, "reload">>({
    pendentesNfe: 0,
    pendentesCte: 0,
    pendentesMdfe: 0,
    pendentesNfse: 0,
    total: 0,
    loading: true,
  })

  const load = useCallback(async () => {
    setData((prev) => ({ ...prev, loading: true }))
    try {
      const sb = getSupabase()
      const { data: { user } } = await sb.auth.getUser()
      if (!user) {
        setData((prev) => ({ ...prev, loading: false }))
        return
      }

      // Get tenant_id
      const { data: tenant } = await sb
        .from("tenants")
        .select("id")
        .eq("user_id", user.id)
        .single()
      if (!tenant) {
        setData((prev) => ({ ...prev, loading: false }))
        return
      }

      // Get tenant's certificates
      const { data: certs } = await sb
        .from("certificates")
        .select("id")
        .eq("tenant_id", tenant.id)
        .eq("is_active", true)
      const certIds = (certs ?? []).map((c) => c.id)
      if (certIds.length === 0) {
        setData({
          pendentesNfe: 0,
          pendentesCte: 0,
          pendentesMdfe: 0,
          pendentesNfse: 0,
          total: 0,
          loading: false,
        })
        return
      }

      // Query nsu_state for pendentes by tipo, filtered by ambiente
      const { data: rows } = await sb
        .from("nsu_state")
        .select("tipo, pendentes, ambiente, certificate_id")
        .in("certificate_id", certIds)
        .eq("ambiente", ambiente)

      let nfe = 0, cte = 0, mdfe = 0, nfse = 0
      for (const r of rows ?? []) {
        const p = r.pendentes ?? 0
        switch ((r.tipo ?? "").toUpperCase()) {
          case "NFE": nfe += p; break
          case "CTE": cte += p; break
          case "MDFE": mdfe += p; break
          case "NFSE": nfse += p; break
        }
      }

      setData({
        pendentesNfe: nfe,
        pendentesCte: cte,
        pendentesMdfe: mdfe,
        pendentesNfse: nfse,
        total: nfe + cte + mdfe + nfse,
        loading: false,
      })
    } catch {
      setData((prev) => ({ ...prev, loading: false }))
    }
  }, [ambiente])

  useEffect(() => {
    load()
  }, [load])

  return { ...data, reload: load }
}
