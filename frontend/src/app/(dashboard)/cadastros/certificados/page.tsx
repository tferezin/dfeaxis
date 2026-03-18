"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import { getSupabase } from "@/lib/supabase"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Card, CardContent, CardFooter, CardHeader, CardTitle,
} from "@/components/ui/card"
import {
  Plus, Trash2, RefreshCw, ShieldCheck, Upload, Inbox, Loader2, Check, AlertTriangle,
} from "lucide-react"

const API_BASE_URL = "https://dfeaxis-production.up.railway.app"

interface Certificate {
  id: string
  cnpj: string
  company_name: string | null
  valid_from: string | null
  valid_until: string | null
  is_active: boolean
  last_polling_at: string | null
}

function getDaysRemaining(validUntil: string | null): number {
  if (!validUntil) return -1
  const diff = new Date(validUntil).getTime() - Date.now()
  return Math.ceil(diff / (1000 * 60 * 60 * 24))
}

function getValidityColor(days: number) {
  if (days < 0) return "text-red-600 bg-red-50"
  if (days <= 30) return "text-amber-600 bg-amber-50"
  return "text-emerald-600 bg-emerald-50"
}

function formatCnpj(cnpj: string) {
  if (cnpj.length !== 14) return cnpj
  return `${cnpj.slice(0,2)}.${cnpj.slice(2,5)}.${cnpj.slice(5,8)}/${cnpj.slice(8,12)}-${cnpj.slice(12)}`
}

export default function CertificadosPage() {
  const [certs, setCerts] = useState<Certificate[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [renewId, setRenewId] = useState<string | null>(null)
  const [formCnpj, setFormCnpj] = useState("")
  const [formSenha, setFormSenha] = useState("")
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null)
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const getToken = useCallback(async () => {
    const sb = getSupabase()
    const { data: { session } } = await sb.auth.getSession()
    return session?.access_token || null
  }, [])

  const loadCerts = useCallback(async () => {
    const token = await getToken()
    if (!token) return
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/certificates`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.ok) {
        const data = await res.json()
        setCerts(Array.isArray(data) ? data : [])
      }
    } catch { /* ignore */ }
  }, [getToken])

  useEffect(() => {
    loadCerts().finally(() => setLoading(false))
  }, [loadCerts])

  const handleUpload = async () => {
    const file = fileRef.current?.files?.[0]
    if (!file || !formCnpj || !formSenha) {
      setMessage({ type: "error", text: "Preencha todos os campos: .pfx, CNPJ e senha." })
      return
    }
    setUploading(true)
    setMessage(null)
    const token = await getToken()
    if (!token) return

    try {
      const form = new FormData()
      form.append("pfx_file", file)
      form.append("cnpj", formCnpj.replace(/\D/g, ""))
      form.append("senha", formSenha)
      form.append("polling_mode", "manual")

      const res = await fetch(`${API_BASE_URL}/api/v1/certificates/upload`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      })

      if (res.ok) {
        const data = await res.json()
        setMessage({ type: "success", text: `Certificado cadastrado com sucesso! CNPJ: ${formatCnpj(data.cnpj)} — Validade: ${data.valid_until}` })
        setShowForm(false)
        setRenewId(null)
        setFormCnpj("")
        setFormSenha("")
        if (fileRef.current) fileRef.current.value = ""
        await loadCerts()
      } else {
        const err = await res.json().catch(() => ({}))
        setMessage({ type: "error", text: err.detail || `Erro ${res.status}: ${res.statusText}` })
      }
    } catch (e) {
      setMessage({ type: "error", text: String(e) })
    } finally {
      setUploading(false)
    }
  }

  const handleDelete = async (id: string) => {
    if (confirmDeleteId !== id) {
      setConfirmDeleteId(id)
      setTimeout(() => setConfirmDeleteId(null), 3000)
      return
    }
    const token = await getToken()
    if (!token) return
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/certificates/${id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.ok || res.status === 204) {
        setConfirmDeleteId(null)
        await loadCerts()
        setMessage({ type: "success", text: "Certificado removido." })
      }
    } catch { /* ignore */ }
  }

  const openRenew = (cert: Certificate) => {
    setRenewId(cert.id)
    setFormCnpj(formatCnpj(cert.cnpj))
    setFormSenha("")
    setShowForm(true)
    setMessage(null)
  }

  const openNew = () => {
    setRenewId(null)
    setFormCnpj("")
    setFormSenha("")
    setShowForm(true)
    setMessage(null)
  }

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
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Certificados A1</h1>
          <p className="text-sm text-muted-foreground">
            Gerencie os certificados digitais das suas empresas. Cada CNPJ precisa de um certificado A1 (.pfx) para capturar documentos na SEFAZ.
          </p>
        </div>
        <Button onClick={openNew} className="gap-1.5">
          <Plus className="size-4" />
          Novo Certificado
        </Button>
      </div>

      {/* Messages */}
      {message && (
        <div className={`rounded-lg border p-3 flex items-center gap-2 ${
          message.type === "success"
            ? "border-emerald-200 bg-emerald-50 text-emerald-800"
            : "border-red-200 bg-red-50 text-red-800"
        }`}>
          {message.type === "success" ? <Check className="size-4 shrink-0" /> : <AlertTriangle className="size-4 shrink-0" />}
          <p className="text-sm">{message.text}</p>
        </div>
      )}

      {/* Upload Form */}
      {showForm && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Upload className="size-5" />
              {renewId ? "Renovar Certificado" : "Cadastrar Novo Certificado"}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-3">
              <div className="space-y-2">
                <Label>Arquivo .pfx</Label>
                <Input ref={fileRef} type="file" accept=".pfx,.p12" />
              </div>
              <div className="space-y-2">
                <Label>CNPJ</Label>
                <Input
                  placeholder="00.000.000/0000-00"
                  value={formCnpj}
                  onChange={(e) => setFormCnpj(e.target.value)}
                  disabled={!!renewId}
                />
              </div>
              <div className="space-y-2">
                <Label>Senha do certificado</Label>
                <Input
                  type="password"
                  placeholder="Senha do .pfx"
                  value={formSenha}
                  onChange={(e) => setFormSenha(e.target.value)}
                />
              </div>
            </div>
          </CardContent>
          <CardFooter className="gap-2">
            <Button onClick={handleUpload} disabled={uploading} className="gap-1.5">
              {uploading ? <Loader2 className="size-4 animate-spin" /> : <Upload className="size-4" />}
              {renewId ? "Renovar" : "Cadastrar"}
            </Button>
            <Button variant="outline" onClick={() => { setShowForm(false); setRenewId(null) }}>
              Cancelar
            </Button>
          </CardFooter>
        </Card>
      )}

      {/* Cards Grid */}
      {certs.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <Inbox className="size-12 text-muted-foreground/30 mb-4" />
          <p className="text-sm text-muted-foreground">
            Nenhum certificado cadastrado. Clique em &quot;Novo Certificado&quot; para começar.
          </p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {certs.map((cert) => {
            const days = getDaysRemaining(cert.valid_until)
            return (
              <Card key={cert.id}>
                <CardHeader>
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-2">
                      <ShieldCheck className="size-5 text-muted-foreground shrink-0" />
                      <CardTitle className="text-sm leading-snug">
                        {cert.company_name || "Empresa"}
                      </CardTitle>
                    </div>
                    <Badge variant={cert.is_active ? "default" : "destructive"}>
                      {cert.is_active ? "Ativo" : "Inativo"}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div>
                    <span className="text-xs font-medium text-muted-foreground">CNPJ</span>
                    <p className="font-mono text-sm">{formatCnpj(cert.cnpj)}</p>
                  </div>
                  <div>
                    <span className="text-xs font-medium text-muted-foreground">Validade</span>
                    <p className="text-sm">
                      {cert.valid_from ? new Date(cert.valid_from).toLocaleDateString("pt-BR") : "—"} até {cert.valid_until ? new Date(cert.valid_until).toLocaleDateString("pt-BR") : "—"}
                    </p>
                    <span className={`inline-flex w-fit rounded-md px-2 py-0.5 text-xs font-medium mt-1 ${getValidityColor(days)}`}>
                      {days < 0 ? "Expirado" : `${days} dias restantes`}
                    </span>
                  </div>
                  {cert.last_polling_at && (
                    <div>
                      <span className="text-xs font-medium text-muted-foreground">Última captura</span>
                      <p className="text-sm">{new Date(cert.last_polling_at).toLocaleString("pt-BR")}</p>
                    </div>
                  )}
                </CardContent>
                <CardFooter className="gap-2">
                  <Button variant="outline" size="sm" className="flex-1 gap-1.5" onClick={() => openRenew(cert)}>
                    <RefreshCw className="size-3.5" />
                    Renovar
                  </Button>
                  <Button
                    variant={confirmDeleteId === cert.id ? "destructive" : "outline"}
                    size="sm"
                    className="flex-1 gap-1.5"
                    onClick={() => handleDelete(cert.id)}
                  >
                    <Trash2 className="size-3.5" />
                    {confirmDeleteId === cert.id ? "Confirmar?" : "Excluir"}
                  </Button>
                </CardFooter>
              </Card>
            )
          })}
        </div>
      )}
    </div>
  )
}
