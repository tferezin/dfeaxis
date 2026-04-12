"use client"
import { useState } from "react"
import { apiFetch } from "@/lib/api"

interface ManifestacaoResult {
  chave_acesso: string
  tipo_evento: string
  descricao: string
  cstat: string
  xmotivo: string
  protocolo?: string
  success: boolean
}

interface BatchResult {
  total: number
  sucesso: number
  erro: number
  resultados: ManifestacaoResult[]
}

export function useManifestacao() {
  const [loading, setLoading] = useState(false)

  async function enviarManifestacao(chave_acesso: string, tipo_evento: string, justificativa?: string): Promise<ManifestacaoResult> {
    setLoading(true)
    try {
      return await apiFetch<ManifestacaoResult>("/manifestacao", {
        method: "POST",
        body: JSON.stringify({ chave_acesso, tipo_evento, justificativa }),
      })
    } finally {
      setLoading(false)
    }
  }

  async function enviarBatch(chaves: string[], tipo_evento: string, justificativa?: string): Promise<BatchResult> {
    setLoading(true)
    try {
      return await apiFetch<BatchResult>("/manifestacao/batch", {
        method: "POST",
        body: JSON.stringify({ chaves, tipo_evento, justificativa }),
      })
    } finally {
      setLoading(false)
    }
  }

  return { enviarManifestacao, enviarBatch, loading }
}
