"use client"

import { useState, useEffect, useCallback } from "react"
import Link from "next/link"
import { getSupabase } from "@/lib/supabase"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Plus, Copy, Trash2, Check, Key, Server, Shield, AlertTriangle, Loader2,
} from "lucide-react"

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "https://dfeaxis-production.up.railway.app"

function formatCnpj(cnpj: string) {
  if (cnpj.length !== 14) return cnpj
  return `${cnpj.slice(0,2)}.${cnpj.slice(2,5)}.${cnpj.slice(5,8)}/${cnpj.slice(8,12)}-${cnpj.slice(12)}`
}

interface ApiKeyEntry {
  id: string
  key_prefix: string
  description: string
  last_used_at: string | null
  is_active: boolean
  created_at: string
}

export default function ApiKeysPage() {
  const [keys, setKeys] = useState<ApiKeyEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [newKeyFull, setNewKeyFull] = useState<string | null>(null)
  const [newKeyDesc, setNewKeyDesc] = useState("")
  const [copiedField, setCopiedField] = useState<string | null>(null)
  const [confirmRevokeId, setConfirmRevokeId] = useState<string | null>(null)
  const [cnpjs, setCnpjs] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)

  const getToken = useCallback(async () => {
    const sb = getSupabase()
    const { data: { session } } = await sb.auth.getSession()
    return session?.access_token || null
  }, [])

  const loadKeys = useCallback(async () => {
    const token = await getToken()
    if (!token) return
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/api-keys`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.ok) {
        const data = await res.json()
        setKeys(Array.isArray(data) ? data : [])
      }
    } catch { /* ignore */ }
  }, [getToken])

  const loadCnpjs = useCallback(async () => {
    try {
      const sb = getSupabase()
      const { data } = await sb.from('certificates').select('cnpj').eq('is_active', true)
      if (data) {
        setCnpjs(data.map((c: { cnpj: string }) => c.cnpj))
      }
    } catch { /* ignore */ }
  }, [])

  useEffect(() => {
    Promise.all([loadKeys(), loadCnpjs()]).finally(() => setLoading(false))
  }, [loadKeys, loadCnpjs])

  const handleCreate = async () => {
    if (!newKeyDesc.trim()) {
      setError("Informe uma descrição para a chave.")
      return
    }
    setCreating(true)
    setError(null)
    const token = await getToken()
    if (!token) return

    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/api-keys`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ description: newKeyDesc }),
      })
      if (res.ok) {
        const data = await res.json()
        setNewKeyFull(data.api_key || data.raw_key || data.key || null)
        await loadKeys()
      } else {
        const err = await res.json().catch(() => ({}))
        setError(err.detail || "Erro ao criar API Key")
      }
    } catch (e) {
      setError(String(e))
    } finally {
      setCreating(false)
    }
  }

  const handleRevoke = async (id: string) => {
    if (confirmRevokeId !== id) {
      setConfirmRevokeId(id)
      setTimeout(() => setConfirmRevokeId(null), 3000)
      return
    }
    const token = await getToken()
    if (!token) return
    try {
      await fetch(`${API_BASE_URL}/api/v1/api-keys/${id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      })
      setConfirmRevokeId(null)
      await loadKeys()
    } catch { /* ignore */ }
  }

  const copyToClipboard = (text: string, field: string) => {
    navigator.clipboard.writeText(text)
    setCopiedField(field)
    setTimeout(() => setCopiedField(null), 2000)
  }

  const CopyBtn = ({ text, field, label }: { text: string; field: string; label?: string }) => (
    <Button
      variant="outline"
      size="sm"
      className="gap-1.5 text-xs shrink-0"
      onClick={() => copyToClipboard(text, field)}
    >
      {copiedField === field ? <Check className="size-3.5 text-emerald-600" /> : <Copy className="size-3.5" />}
      {label || (copiedField === field ? "Copiado" : "Copiar")}
    </Button>
  )

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="size-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Chave de Acesso da API</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Sua chave única de integração com o DFeAxis. Use no header <code className="text-xs bg-muted px-1 rounded">X-API-Key</code> de todas as chamadas.
        </p>
      </div>

      {/* Integration Info Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Server className="size-5" />
            Dados de Integração
          </CardTitle>
          <p className="text-xs text-muted-foreground mt-1">
            Informações essenciais pra configurar seu ERP agora. Pra ver todos os endpoints disponíveis (manifestação, histórico, SAP DRC nativo), consulte{" "}
            <Link href="/getting-started" className="text-primary hover:underline">Ajuda → Primeiros Passos</Link>.
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3">
            <div className="flex items-center justify-between rounded-lg border p-3">
              <div>
                <p className="text-xs font-medium text-muted-foreground">URL Base da API</p>
                <code className="text-sm font-mono">{API_BASE_URL}/api/v1</code>
              </div>
              <CopyBtn text={`${API_BASE_URL}/api/v1`} field="url" />
            </div>

            <div className="flex items-center justify-between rounded-lg border p-3">
              <div>
                <p className="text-xs font-medium text-muted-foreground">Header de Autenticação</p>
                <code className="text-sm font-mono">X-API-Key: &lt;sua_chave&gt;</code>
              </div>
              <CopyBtn text="X-API-Key" field="header" />
            </div>

            <div className="flex items-center justify-between rounded-lg border p-3">
              <div>
                <p className="text-xs font-medium text-muted-foreground">CNPJs Cadastrados</p>
                {cnpjs.length > 0 ? (
                  <code className="text-sm font-mono">{cnpjs.map(formatCnpj).join(", ")}</code>
                ) : (
                  <span className="text-sm text-muted-foreground">Nenhum certificado cadastrado</span>
                )}
              </div>
              {cnpjs.length > 0 && <CopyBtn text={cnpjs[0]} field="cnpj" />}
            </div>

            <div className="flex items-center justify-between rounded-lg border p-3">
              <div>
                <p className="text-xs font-medium text-muted-foreground">Buscar documentos</p>
                <code className="text-sm font-mono">GET /api/v1/documentos?cnpj={cnpjs[0] || "SEU_CNPJ"}&tipo=nfe</code>
              </div>
              <CopyBtn
                text={`curl -s "${API_BASE_URL}/api/v1/documentos?cnpj=${cnpjs[0] || "SEU_CNPJ"}&tipo=nfe" -H "X-API-Key: SUA_CHAVE"`}
                field="curl"
                label="curl"
              />
            </div>

            <div className="flex items-center justify-between rounded-lg border p-3">
              <div>
                <p className="text-xs font-medium text-muted-foreground">Confirmar recebimento</p>
                <code className="text-sm font-mono">POST /api/v1/documentos/&#123;chave_44_digitos&#125;/confirmar</code>
              </div>
              <CopyBtn
                text={`curl -s -X POST "${API_BASE_URL}/api/v1/documentos/CHAVE_44_DIGITOS/confirmar" -H "X-API-Key: SUA_CHAVE"`}
                field="curl-confirm"
                label="curl"
              />
            </div>
          </div>

          <div className="rounded-lg bg-blue-50 border border-blue-200 p-3">
            <div className="flex gap-2">
              <Shield className="size-4 text-blue-600 mt-0.5 shrink-0" />
              <p className="text-xs text-blue-800">
                <strong>Multi-CNPJ:</strong> Uma única API Key dá acesso a <strong>todos os CNPJs</strong> cadastrados na sua conta. O seu ERP escolhe qual CNPJ consultar via parâmetro <code>?cnpj=XXXXX</code>. Cada CNPJ deve ter seu certificado A1 cadastrado em <strong>Cadastros &gt; Certificados A1</strong>.
              </p>
            </div>
          </div>

          <div className="rounded-lg bg-amber-50 border border-amber-200 p-3">
            <div className="flex gap-2">
              <AlertTriangle className="size-4 text-amber-600 mt-0.5 shrink-0" />
              <p className="text-xs text-amber-800">
                <strong>Tipos suportados:</strong> <code>nfe</code>, <code>cte</code>, <code>mdfe</code>, <code>nfse</code>. O XML é retornado em base64 no campo <code>xml_b64</code>. Após processar no seu ERP, chame <code>/confirmar</code> para limpar do DFeAxis.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Create API Key */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Shield className="size-5" />
            Sua Chave de Acesso
          </CardTitle>
          <p className="text-xs text-muted-foreground mt-1">
            Ao gerar uma nova chave, as anteriores <strong>continuam ativas</strong> — útil pra ter chaves separadas por ERP ou ambiente. Revogue manualmente as que não usa mais.
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* New key form */}
          {!newKeyFull ? (
            <div className="flex gap-3">
              <div className="flex-1">
                <Input
                  placeholder="Descrição (ex: ERP Produção, ambiente de testes)"
                  value={newKeyDesc}
                  onChange={(e) => setNewKeyDesc(e.target.value)}
                />
              </div>
              <Button onClick={handleCreate} disabled={creating} className="gap-1.5">
                {creating ? <Loader2 className="size-4 animate-spin" /> : <Plus className="size-4" />}
                Gerar API Key
              </Button>
            </div>
          ) : (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 space-y-3">
              <p className="text-sm font-medium text-emerald-800">
                API Key criada com sucesso! Copie agora — ela não será exibida novamente.
              </p>
              <div className="flex items-center gap-2">
                <code className="flex-1 break-all rounded bg-white px-3 py-2 font-mono text-xs border">
                  {newKeyFull}
                </code>
                <CopyBtn text={newKeyFull} field="newkey" />
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => { setNewKeyFull(null); setNewKeyDesc("") }}
              >
                Fechar
              </Button>
            </div>
          )}

          {error && (
            <p className="text-sm text-destructive">{error}</p>
          )}

          {/* Keys list */}
          {keys.length > 0 ? (
            <div className="rounded-lg border divide-y">
              {keys.map((k) => (
                <div key={k.id} className="flex items-center gap-4 p-4">
                  <Key className="size-4 text-muted-foreground shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <code className="font-mono text-xs">{k.key_prefix}...</code>
                      <Badge variant={k.is_active ? "default" : "destructive"} className="text-xs">
                        {k.is_active ? "Ativa" : "Revogada"}
                      </Badge>
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {k.description || "Sem descrição"} — criada em {new Date(k.created_at).toLocaleDateString("pt-BR")}
                      {k.last_used_at && ` — último uso: ${new Date(k.last_used_at).toLocaleDateString("pt-BR")}`}
                    </p>
                  </div>
                  {k.is_active && (
                    <Button
                      variant={confirmRevokeId === k.id ? "destructive" : "ghost"}
                      size="sm"
                      onClick={() => handleRevoke(k.id)}
                      className="gap-1.5"
                    >
                      <Trash2 className="size-3.5" />
                      {confirmRevokeId === k.id ? "Confirmar?" : "Revogar"}
                    </Button>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8">
              <Key className="size-10 text-muted-foreground/30 mx-auto mb-2" />
              <p className="text-sm text-muted-foreground">
                Nenhuma API Key criada. Gere uma para integrar com o SAP.
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
