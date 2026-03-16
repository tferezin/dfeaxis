"use client"

import { useCallback, useSyncExternalStore } from "react"

interface TenantSettings {
  operationMode: "auto" | "manual" // unifica captura + manifestação
  sefazAmbiente: "1" | "2"
  capturaInterval: string
  notifyEmail: string
  notifyCertExpiry: boolean
  notifyNoCredits: boolean
}

const STORAGE_KEY = "dfeaxis_settings"

const defaultSettings: TenantSettings = {
  operationMode: "auto",
  sefazAmbiente: "2",
  capturaInterval: "15",
  notifyEmail: "",
  notifyCertExpiry: true,
  notifyNoCredits: true,
}

let listeners: Array<() => void> = []

function emitChange() {
  for (const listener of listeners) {
    listener()
  }
}

function getSnapshot(): TenantSettings {
  if (typeof window === "undefined") return defaultSettings
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? { ...defaultSettings, ...JSON.parse(raw) } : defaultSettings
  } catch {
    return defaultSettings
  }
}

function subscribe(listener: () => void) {
  listeners = [...listeners, listener]
  return () => {
    listeners = listeners.filter((l) => l !== listener)
  }
}

export function useSettings() {
  const settings = useSyncExternalStore(subscribe, getSnapshot, () => defaultSettings)

  const updateSettings = useCallback((updates: Partial<TenantSettings>) => {
    const current = getSnapshot()
    const next = { ...current, ...updates }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    emitChange()
  }, [])

  return { settings, updateSettings }
}
