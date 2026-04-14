"use client"

import { useEffect } from "react"
import { captureAttribution } from "@/lib/attribution"

/**
 * Client Component que dispara `captureAttribution()` uma vez no mount.
 * Incluído no root layout.tsx pra rodar em qualquer entrada na app —
 * cobre o caso de usuários que caem direto em /signup, /dashboard, etc
 * via anúncio (bypass da landing estática).
 *
 * Não renderiza nada — é só um side-effect.
 */
export function AttributionCapture() {
  useEffect(() => {
    captureAttribution()
  }, [])

  return null
}
