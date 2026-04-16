import { getSupabase } from './supabase'

// NEXT_PUBLIC_API_URL = raiz do backend (sem /api/v1).
// Tolera ambos os formatos pra não quebrar se alguém setar com /api/v1.
const _RAW = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
const API_BASE = _RAW.endsWith('/api/v1') ? _RAW : `${_RAW}/api/v1`

export async function apiFetch<T = unknown>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const sb = getSupabase()
  const { data: { session } } = await sb.auth.getSession()
  const token = session?.access_token

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  })

  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`API error ${res.status}: ${body}`)
  }

  return res.json()
}
