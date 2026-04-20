"use client"

import { useState, useRef, useEffect } from "react"
import {
  Play,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  FileText,
  Truck,
  FileStack,
  Building2,
  Upload,
  Database,
  ClipboardList,
  Download,
  Clock,
  Search,
  ChevronDown,
  ChevronRight,
  Zap,
} from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { getSupabase } from "@/lib/supabase"

const cteDocTypes = [
  { key: "cte", label: "CT-e", icon: Truck },
  { key: "mdfe", label: "MDF-e", icon: FileStack },
  { key: "nfse", label: "NFS-e", icon: Building2 },
]

interface RegisteredCert {
  id: string
  cnpj: string
  company_name: string
}

export default function CapturaManualPage() {
  const fileRef = useRef<HTMLInputElement>(null)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [cnpj, setCnpj] = useState("")
  const [password, setPassword] = useState("")

  // Registered certificates
  const [registeredCerts, setRegisteredCerts] = useState<RegisteredCert[]>([])
  const [selectedCertId, setSelectedCertId] = useState<string>("")
  const [showUpload, setShowUpload] = useState(false)
  const [certsLoading, setCertsLoading] = useState(true)

  // "Capturar TODOS" state
  const [captureAllStatus, setCaptureAllStatus] = useState<"idle" | "loading">("idle")
  const [captureAllProgress, setCaptureAllProgress] = useState("")
  const [captureAllResults, setCaptureAllResults] = useState<Array<{
    cnpj: string
    company_name: string
    success: boolean
    message: string
  }>>([])

  // Load registered certificates on mount
  useEffect(() => {
    async function loadCerts() {
      try {
        const sb = getSupabase()
        const { data } = await sb
          .from("certificates")
          .select("id, cnpj, company_name")
          .eq("is_active", true)
        if (data && data.length > 0) {
          setRegisteredCerts(data)
          // Auto-select first cert
          setSelectedCertId(data[0].id)
          setCnpj(data[0].cnpj)
        }
      } finally {
        setCertsLoading(false)
      }
    }
    loadCerts()
  }, [])

  // When cert selection changes, update CNPJ
  const handleCertSelect = (certId: string) => {
    setSelectedCertId(certId)
    const cert = registeredCerts.find((c) => c.id === certId)
    if (cert) {
      setCnpj(cert.cnpj)
    }
  }

  // CT-e / MDF-e / NFS-e state
  const [directTipos, setDirectTipos] = useState<Record<string, boolean>>({
    cte: true,
    mdfe: true,
    nfse: true,
  })
  const [directStatus, setDirectStatus] = useState<"idle" | "loading">("idle")
  const [directResult, setDirectResult] = useState<{
    error?: string
    certificate?: { subject: string; valid_from: string; valid_until: string }
    cnpj?: string
    results?: Array<{
      tipo: string
      status: string
      cstat?: string
      xmotivo?: string
      docs_found?: number
      latency_ms?: number
      message?: string
    }>
    message?: string
  } | null>(null)

  // NF-e 2-step state
  const [nfeResetNsu, setNfeResetNsu] = useState(false)
  const [nfeResetFilaStatus, setNfeResetFilaStatus] = useState<"idle" | "loading">("idle")
  const [nfeResetFilaResult, setNfeResetFilaResult] = useState<string | null>(null)
  const [nfeStep1Status, setNfeStep1Status] = useState<"idle" | "loading">("idle")
  const [nfeRetryCienciaStatus, setNfeRetryCienciaStatus] = useState<"idle" | "loading">("idle")
  const [nfeRetryCienciaResult, setNfeRetryCienciaResult] = useState<{
    error?: string
    pending_in_queue?: number
    ciencia_sent?: number
    ciencia_failed?: number
    results?: Array<{
      chave?: string
      status?: string
      cstat?: string
      xmotivo?: string
      detail?: string
    }>
  } | null>(null)
  const [nfeStep2Status, setNfeStep2Status] = useState<"idle" | "loading">("idle")
  const [nfeStep1Result, setNfeStep1Result] = useState<{
    error?: string
    resumos_found?: number
    ciencia_sent?: number
    completos_found?: number
    sefaz_cstat?: string
    sefaz_xmotivo?: string
    ult_nsu_used?: string
    ult_nsu_returned?: string
    max_nsu?: string
    total_docs_in_response?: number
    results?: Array<{
      chave?: string
      nsu?: string
      tipo?: string
      status?: string
      cstat?: string
      xmotivo?: string
      detail?: string
    }>
  } | null>(null)
  const [nfeStep2Result, setNfeStep2Result] = useState<{
    error?: string
    xml_found?: number
    saved?: number
    still_pending?: number
    results?: Array<{
      chave?: string
      nsu?: string
      status?: string
      detail?: string
      tentativas?: number
    }>
  } | null>(null)

  const selectedDirectTipos = Object.entries(directTipos)
    .filter(([, v]) => v)
    .map(([k]) => k)

  const cleanCnpj = cnpj.replace(/\D/g, "")

  const getBackendUrl = () => {
    const raw = process.env.NEXT_PUBLIC_API_URL || "https://dfeaxis-production.up.railway.app"
    return raw.endsWith("/api/v1") ? raw : `${raw}/api/v1`
  }

  const getAuthToken = async () => {
    const sb = getSupabase()
    const { data: { session } } = await sb.auth.getSession()
    return session?.access_token ?? null
  }

  const isUsingRegisteredCert = !!selectedCertId && !showUpload

  // --- Direct capture (CT-e, MDF-e, NFS-e) ---
  const handleDirectCapture = async () => {
    if (!isUsingRegisteredCert) {
      // Upload flow: need file + cnpj + password
      const file = fileRef.current?.files?.[0]
      if (!file || !cleanCnpj || !password) {
        setDirectResult({ error: "Preencha todos os campos: certificado .pfx, CNPJ e senha." })
        return
      }
    } else if (!cleanCnpj) {
      setDirectResult({ error: "Selecione um certificado cadastrado." })
      return
    }

    if (selectedDirectTipos.length === 0) {
      setDirectResult({ error: "Selecione pelo menos um tipo de documento." })
      return
    }

    setDirectStatus("loading")
    setDirectResult(null)

    const backendUrl = getBackendUrl()

    try {
      const token = await getAuthToken()
      if (!token) {
        setDirectResult({ error: "Sessao expirada. Faca login novamente." })
        return
      }

      // If uploading a new cert, upload first
      if (!isUsingRegisteredCert) {
        const file = fileRef.current?.files?.[0]!
        const uploadForm = new FormData()
        uploadForm.append("pfx_file", file)
        uploadForm.append("cnpj", cleanCnpj)
        uploadForm.append("senha", password)
        uploadForm.append("polling_mode", "manual")

        const uploadRes = await fetch(`${backendUrl}/certificates/upload`, {
          method: "POST",
          headers: { "Authorization": `Bearer ${token}` },
          body: uploadForm,
        })

        if (!uploadRes.ok) {
          const uploadErr = await uploadRes.json().catch(() => ({}))
          setDirectResult({ error: `Erro ao cadastrar certificado: ${uploadErr.detail || uploadRes.statusText}` })
          return
        }
      }

      // Trigger polling (works for both registered and uploaded certs)
      const pollingRes = await fetch(`${backendUrl}/polling/trigger`, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ cnpj: cleanCnpj, tipos: selectedDirectTipos }),
      })

      if (!pollingRes.ok) {
        const pollingErr = await pollingRes.json().catch(() => ({}))
        setDirectResult({
          cnpj: cleanCnpj,
          error: `Erro na captura: ${pollingErr.detail || pollingRes.statusText}`,
        })
        return
      }

      const pollingData = await pollingRes.json()

      const results = (pollingData.results || []).map((r: { tipo: string; status: string; cstat: string; xmotivo: string; docs_found: number; latency_ms: number; error?: string; saved_to_db: boolean }) => ({
        tipo: r.tipo,
        status: r.error ? "error" : "success",
        cstat: r.cstat,
        xmotivo: r.xmotivo,
        docs_found: r.docs_found,
        latency_ms: r.latency_ms,
        message: r.error || (r.saved_to_db ? `${r.docs_found} doc(s) salvo(s)` : ""),
      }))

      setDirectResult({
        cnpj: cleanCnpj,
        results,
        message: `${pollingData.docs_found || 0} documento(s) capturado(s) e salvo(s) no banco.`,
      })
    } catch (err) {
      setDirectResult({ error: `Erro: ${String(err)}` })
    } finally {
      setDirectStatus("idle")
    }
  }

  // --- Capture ALL registered certs ---
  const handleCaptureAll = async () => {
    if (registeredCerts.length === 0) return

    setCaptureAllStatus("loading")
    setCaptureAllResults([])

    const backendUrl = getBackendUrl()

    try {
      const token = await getAuthToken()
      if (!token) {
        setCaptureAllResults([{ cnpj: "", company_name: "", success: false, message: "Sessao expirada." }])
        return
      }

      const allResults: typeof captureAllResults = []

      for (let i = 0; i < registeredCerts.length; i++) {
        const cert = registeredCerts[i]
        setCaptureAllProgress(`Processando certificado ${i + 1}/${registeredCerts.length}: ${cert.company_name || cert.cnpj}...`)

        try {
          // Trigger CT-e/MDF-e/NFS-e
          const triggerRes = await fetch(`${backendUrl}/polling/trigger`, {
            method: "POST",
            headers: {
              "Authorization": `Bearer ${token}`,
              "Content-Type": "application/json",
            },
            body: JSON.stringify({ cnpj: cert.cnpj, tipos: ["cte", "mdfe", "nfse"] }),
          })

          // Trigger NFe Etapa 1
          const nfeRes = await fetch(`${backendUrl}/polling/nfe-resumos`, {
            method: "POST",
            headers: {
              "Authorization": `Bearer ${token}`,
              "Content-Type": "application/json",
            },
            body: JSON.stringify({ cnpj: cert.cnpj }),
          })

          const triggerOk = triggerRes.ok
          const nfeOk = nfeRes.ok

          let triggerDocs = 0
          let nfeResumos = 0
          if (triggerOk) {
            const td = await triggerRes.json()
            triggerDocs = td.docs_found || 0
          }
          if (nfeOk) {
            const nd = await nfeRes.json()
            nfeResumos = nd.resumos_found || 0
          }

          allResults.push({
            cnpj: cert.cnpj,
            company_name: cert.company_name || cert.cnpj,
            success: triggerOk || nfeOk,
            message: triggerOk && nfeOk
              ? `CT-e/MDF-e/NFS-e: ${triggerDocs} doc(s) | NF-e: ${nfeResumos} resumo(s)`
              : !triggerOk && !nfeOk
                ? "Erro em ambas as capturas"
                : !triggerOk
                  ? `Erro CT-e/MDF-e/NFS-e | NF-e: ${nfeResumos} resumo(s)`
                  : `CT-e/MDF-e/NFS-e: ${triggerDocs} doc(s) | Erro NF-e`,
          })
        } catch (err) {
          allResults.push({
            cnpj: cert.cnpj,
            company_name: cert.company_name || cert.cnpj,
            success: false,
            message: `Erro: ${String(err)}`,
          })
        }

        setCaptureAllResults([...allResults])
      }
    } catch (err) {
      setCaptureAllResults([{ cnpj: "", company_name: "", success: false, message: `Erro: ${String(err)}` }])
    } finally {
      setCaptureAllStatus("idle")
      setCaptureAllProgress("")
    }
  }

  // --- NF-e Reset Fila ---
  const handleResetFila = async () => {
    if (!cleanCnpj) return
    setNfeResetFilaStatus("loading")
    setNfeResetFilaResult(null)
    const backendUrl = getBackendUrl()
    try {
      const token = await getAuthToken()
      if (!token) { setNfeResetFilaResult("Sessao expirada."); return }
      const res = await fetch(`${backendUrl}/polling/nfe-reset-fila`, {
        method: "POST",
        headers: { "Authorization": `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ cnpj: cleanCnpj }),
      })
      const data = await res.json()
      setNfeResetFilaResult(data.message || data.detail || JSON.stringify(data))
    } catch (err) {
      setNfeResetFilaResult(`Erro: ${String(err)}`)
    } finally {
      setNfeResetFilaStatus("idle")
    }
  }

  // --- NF-e Step 1: Resumos + Ciencia ---
  const handleNfeStep1 = async () => {
    if (!cleanCnpj) {
      setNfeStep1Result({ error: "Preencha o campo CNPJ acima." })
      return
    }
    setNfeStep1Status("loading")
    setNfeStep1Result(null)

    const backendUrl = getBackendUrl()

    try {
      const token = await getAuthToken()
      if (!token) {
        setNfeStep1Result({ error: "Sessao expirada. Faca login novamente." })
        return
      }

      const res = await fetch(`${backendUrl}/polling/nfe-resumos`, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ cnpj: cleanCnpj, force_reset_nsu: nfeResetNsu }),
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        setNfeStep1Result({ error: `Erro ${res.status}: ${err.detail || res.statusText}` })
        return
      }

      const data = await res.json()
      setNfeStep1Result(data)
    } catch (err) {
      setNfeStep1Result({ error: `Erro: ${String(err)}` })
    } finally {
      setNfeStep1Status("idle")
    }
  }

  // --- NF-e Retry Ciencia ---
  const handleRetryCiencia = async () => {
    if (!cleanCnpj) return
    setNfeRetryCienciaStatus("loading")
    setNfeRetryCienciaResult(null)

    const backendUrl = getBackendUrl()
    try {
      const token = await getAuthToken()
      if (!token) {
        setNfeRetryCienciaResult({ error: "Sessao expirada." })
        return
      }
      const res = await fetch(`${backendUrl}/polling/nfe-retry-ciencia`, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ cnpj: cleanCnpj }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        setNfeRetryCienciaResult({ error: `Erro ${res.status}: ${err.detail || res.statusText}` })
        return
      }
      const data = await res.json()
      setNfeRetryCienciaResult(data)
    } catch (err) {
      setNfeRetryCienciaResult({ error: `Erro: ${String(err)}` })
    } finally {
      setNfeRetryCienciaStatus("idle")
    }
  }

  // --- NF-e Step 2: XML Completo ---
  const handleNfeStep2 = async () => {
    if (!cleanCnpj) {
      setNfeStep2Result({ error: "Preencha o campo CNPJ acima." })
      return
    }
    setNfeStep2Status("loading")
    setNfeStep2Result(null)

    const backendUrl = getBackendUrl()

    try {
      const token = await getAuthToken()
      if (!token) {
        setNfeStep2Result({ error: "Sessao expirada. Faca login novamente." })
        return
      }

      const res = await fetch(`${backendUrl}/polling/nfe-xml-completo`, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ cnpj: cleanCnpj }),
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        setNfeStep2Result({ error: `Erro ${res.status}: ${err.detail || res.statusText}` })
        return
      }

      const data = await res.json()
      setNfeStep2Result(data)
    } catch (err) {
      setNfeStep2Result({ error: `Erro: ${String(err)}` })
    } finally {
      setNfeStep2Status("idle")
    }
  }

  return (
    <div className="space-y-6">
      {/* Warning banner */}
      <div className="flex items-start gap-3 rounded-lg border border-amber-300 bg-amber-50 dark:border-amber-700 dark:bg-amber-950/30 p-4">
        <AlertTriangle className="mt-0.5 size-5 shrink-0 text-amber-600 dark:text-amber-400" />
        <div>
          <p className="text-sm font-medium text-amber-900 dark:text-amber-200">
            Funcionalidade de teste / validacao
          </p>
          <p className="text-xs text-amber-700 dark:text-amber-400 mt-1">
            Esta funcionalidade e apenas para testes durante a fase de validacao. Em producao, a captura deve ser disparada pelo seu ERP via API
            (<code className="bg-amber-100 dark:bg-amber-900/50 px-1 py-0.5 rounded text-xs font-mono">POST /api/v1/polling/trigger</code>).
          </p>
        </div>
      </div>

      {/* Page title */}
      <div>
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-semibold tracking-tight">Captura Manual</h1>
          <Badge variant="secondary" className="text-[10px]">Temporario</Badge>
        </div>
        <p className="text-sm text-muted-foreground mt-1">
          Teste a conexao com a SEFAZ e capture documentos.
        </p>
      </div>

      {/* Certificado A1 card */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Certificado A1</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Option 1: Registered certificates */}
          {certsLoading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
              Carregando certificados...
            </div>
          ) : registeredCerts.length > 0 ? (
            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label className="text-xs">Certificado cadastrado</Label>
                <select
                  className="flex h-9 w-full rounded-lg border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 dark:bg-input/30"
                  value={selectedCertId}
                  onChange={(e) => handleCertSelect(e.target.value)}
                >
                  {registeredCerts.map((cert) => (
                    <option key={cert.id} value={cert.id}>
                      {cert.company_name ? `${cert.company_name} — ${cert.cnpj}` : cert.cnpj}
                    </option>
                  ))}
                </select>
              </div>

              {/* Auto-filled CNPJ (read-only) */}
              <div className="space-y-1.5">
                <Label className="text-xs">CNPJ</Label>
                <Input
                  placeholder="00.000.000/0000-00"
                  className="text-sm bg-muted/50"
                  value={cnpj}
                  readOnly
                />
              </div>

              {/* Capture ALL button */}
              <div className="pt-1">
                <Button
                  variant="outline"
                  className="gap-2 text-xs"
                  disabled={captureAllStatus === "loading" || registeredCerts.length === 0}
                  onClick={handleCaptureAll}
                >
                  {captureAllStatus === "loading" ? (
                    <Loader2 className="size-3.5 animate-spin" />
                  ) : (
                    <Zap className="size-3.5" />
                  )}
                  {captureAllStatus === "loading"
                    ? captureAllProgress || "Processando..."
                    : `Capturar TODOS os certificados (${registeredCerts.length})`}
                </Button>
              </div>

              {/* Capture ALL results */}
              {captureAllResults.length > 0 && (
                <div className="space-y-2">
                  {captureAllResults.map((r, i) => (
                    <div
                      key={i}
                      className={`rounded-lg border p-3 ${
                        r.success
                          ? "border-emerald-200 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/30"
                          : "border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-950/30"
                      }`}
                    >
                      <p className={`text-xs font-medium ${
                        r.success ? "text-emerald-800 dark:text-emerald-300" : "text-red-700 dark:text-red-300"
                      }`}>
                        {r.company_name}
                      </p>
                      <p className="text-xs text-muted-foreground mt-0.5">{r.message}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="rounded-lg border border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/30 p-3">
              <p className="text-xs text-amber-800 dark:text-amber-300">
                Nenhum certificado cadastrado. Use a secao abaixo para enviar um certificado .pfx.
              </p>
            </div>
          )}

          {/* Option 2: Upload new certificate (collapsible) */}
          <div className="border-t pt-3">
            <button
              type="button"
              className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
              onClick={() => {
                setShowUpload(!showUpload)
                if (!showUpload) {
                  // Switching to upload mode: clear registered cert selection
                  setSelectedCertId("")
                  setCnpj("")
                } else {
                  // Switching back: re-select first registered cert
                  if (registeredCerts.length > 0) {
                    setSelectedCertId(registeredCerts[0].id)
                    setCnpj(registeredCerts[0].cnpj)
                  }
                }
              }}
            >
              {showUpload ? (
                <ChevronDown className="size-4" />
              ) : (
                <ChevronRight className="size-4" />
              )}
              Ou testar com certificado novo
            </button>

            {showUpload && (
              <div className="mt-3 space-y-4">
                {/* File input - styled */}
                <div className="space-y-1.5">
                  <Label className="text-xs">Certificado digital (.pfx)</Label>
                  <label className="cursor-pointer inline-flex items-center gap-2 px-4 py-2 rounded-lg border-2 border-dashed border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-800/50 hover:border-slate-400 dark:hover:border-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors">
                    <Upload className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm text-muted-foreground">
                      {selectedFile ? selectedFile.name : "Selecionar certificado .pfx"}
                    </span>
                    <input
                      type="file"
                      accept=".pfx,.p12"
                      ref={fileRef}
                      className="hidden"
                      onChange={(e) => setSelectedFile(e.target.files?.[0] ?? null)}
                    />
                  </label>
                </div>

                {/* CNPJ + Senha */}
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-1.5">
                    <Label className="text-xs">CNPJ</Label>
                    <Input
                      placeholder="00.000.000/0000-00"
                      className="text-sm"
                      value={cnpj}
                      onChange={(e) => setCnpj(e.target.value)}
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Senha do certificado</Label>
                    <Input
                      type="password"
                      placeholder="Senha"
                      className="text-sm"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                    />
                  </div>
                </div>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* CT-e / MDF-e / NFS-e - Direct capture (AFTER NF-e section) */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">CT-e / MDF-e / NFS-e — Captura direta</CardTitle>
          <p className="text-xs text-muted-foreground">
            Estes documentos vem completos da SEFAZ em uma unica consulta.
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Checkboxes */}
          <div className="flex flex-wrap gap-3">
            {cteDocTypes.map((dt) => {
              const Icon = dt.icon
              return (
                <label
                  key={dt.key}
                  className={`flex items-center gap-2 rounded-lg border px-4 py-2 cursor-pointer transition-colors ${
                    directTipos[dt.key]
                      ? "border-primary bg-primary/5 text-primary"
                      : "border-border text-muted-foreground hover:border-muted-foreground/30"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={directTipos[dt.key]}
                    onChange={(e) => setDirectTipos((prev) => ({ ...prev, [dt.key]: e.target.checked }))}
                    className="sr-only"
                  />
                  <Icon className="size-4" />
                  <span className="text-sm font-medium">{dt.label}</span>
                </label>
              )
            })}
          </div>

          {/* Capture button */}
          <Button
            className="gap-2"
            disabled={directStatus === "loading" || selectedDirectTipos.length === 0}
            onClick={handleDirectCapture}
          >
            {directStatus === "loading" ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Play className="size-4" />
            )}
            {directStatus === "loading" ? "Capturando..." : "Capturar documentos"}
          </Button>

          {/* Results */}
          {directResult && (
            <div className="space-y-2">
              {directResult.error ? (
                <div className="rounded-lg border border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-950/30 p-3">
                  <p className="text-xs text-red-700 dark:text-red-300 font-medium">{directResult.error}</p>
                </div>
              ) : (
                <>
                  {directResult.certificate && (
                    <div className="rounded-lg border border-emerald-200 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/30 p-3">
                      <p className="text-xs font-medium text-emerald-800 dark:text-emerald-300">Certificado valido</p>
                      <p className="text-xs text-emerald-700 dark:text-emerald-400 mt-0.5 font-mono">{directResult.certificate.subject}</p>
                      {directResult.certificate.valid_until && (
                        <p className="text-xs text-emerald-600 dark:text-emerald-400 mt-0.5">Validade: {directResult.certificate.valid_from} ate {directResult.certificate.valid_until}</p>
                      )}
                    </div>
                  )}
                  {directResult.message && (
                    <div className="rounded-lg border border-blue-200 bg-blue-50 dark:border-blue-800 dark:bg-blue-950/30 p-3 flex items-center gap-2">
                      <Database className="w-4 h-4 text-blue-600 dark:text-blue-400 flex-shrink-0" />
                      <p className="text-xs font-medium text-blue-800 dark:text-blue-300">{directResult.message}</p>
                    </div>
                  )}
                  {directResult.results?.map((r, i) => (
                    <div
                      key={i}
                      className={`rounded-lg border p-3 ${
                        r.status === "success"
                          ? r.cstat === "137" || r.cstat === "138"
                            ? "border-emerald-200 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/30"
                            : "border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/30"
                          : r.status === "skipped"
                            ? "border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-900/30"
                            : "border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-950/30"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <Badge variant="secondary" className="text-[10px]">{r.tipo}</Badge>
                          <span className={`text-xs font-medium ${
                            r.status === "success" ? "text-emerald-700 dark:text-emerald-300" : r.status === "skipped" ? "text-gray-600 dark:text-gray-400" : "text-red-700 dark:text-red-300"
                          }`}>
                            {r.status === "success" ? `cStat ${r.cstat}` : r.status === "skipped" ? "Ignorado" : "Erro"}
                          </span>
                        </div>
                        {r.latency_ms && <span className="text-xs text-muted-foreground">{r.latency_ms}ms</span>}
                      </div>
                      <p className="text-xs mt-1 text-muted-foreground">
                        {r.xmotivo || r.message}
                      </p>
                      {r.docs_found !== undefined && r.docs_found > 0 && (
                        <p className="text-xs mt-1 font-medium text-emerald-700 dark:text-emerald-300">{r.docs_found} documento(s) encontrado(s)</p>
                      )}
                    </div>
                  ))}
                </>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* NF-e - 2-step capture */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <FileText className="size-5 text-amber-600 dark:text-amber-400" />
            <CardTitle className="text-base">NF-e — Captura em 2 etapas</CardTitle>
          </div>
          <p className="text-xs text-muted-foreground">
            A SEFAZ exige ciencia da operacao antes de liberar o XML completo da NF-e.
          </p>
        </CardHeader>
        <CardContent className="space-y-5">
          {/* Reset fila */}
          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5 text-xs border-red-300 text-red-600 hover:bg-red-50"
              disabled={nfeResetFilaStatus === "loading" || !cleanCnpj}
              onClick={handleResetFila}
            >
              {nfeResetFilaStatus === "loading" ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <AlertTriangle className="size-3.5" />
              )}
              Limpar fila e resetar cursor
            </Button>
            {nfeResetFilaResult && (
              <span className="text-xs text-muted-foreground">{nfeResetFilaResult}</span>
            )}
          </div>

          <div className="grid gap-6 md:grid-cols-2">
          {/* Step 1 */}
          <div className="space-y-3">
            <div>
              <p className="text-sm font-medium">Etapa 1: Buscar resumos e enviar ciência</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Consulta a SEFAZ para obter resumos de NF-e pendentes e envia ciência automaticamente.
              </p>
            </div>
            <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer">
              <input
                type="checkbox"
                checked={nfeResetNsu}
                onChange={(e) => setNfeResetNsu(e.target.checked)}
                className="rounded"
              />
              Resetar cursor (buscar desde o inicio)
            </label>
            <Button
              className="gap-2 bg-amber-600 hover:bg-amber-700 text-white"
              disabled={nfeStep1Status === "loading" || !cleanCnpj}
              onClick={handleNfeStep1}
            >
              {nfeStep1Status === "loading" ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Search className="size-4" />
              )}
              {nfeStep1Status === "loading" ? "Buscando resumos..." : "Buscar Resumos + Enviar Ciencia"}
            </Button>

            {/* Step 1 results */}
            {nfeStep1Result && (
              <div className="space-y-2">
                {nfeStep1Result.error ? (
                  <div className="rounded-lg border border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-950/30 p-3">
                    <p className="text-xs text-red-700 dark:text-red-300 font-medium">{nfeStep1Result.error}</p>
                  </div>
                ) : (
                  <>
                    <div className="rounded-lg border border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/30 p-3 space-y-2">
                      <div className="flex gap-4 text-xs flex-wrap">
                        <span className="text-amber-800 dark:text-amber-300">
                          <strong>{nfeStep1Result.resumos_found ?? 0}</strong> resumo(s) encontrado(s)
                        </span>
                        <span className="text-emerald-700 dark:text-emerald-300">
                          <strong>{nfeStep1Result.ciencia_sent ?? 0}</strong> ciencia(s) enviada(s)
                        </span>
                        {(nfeStep1Result.completos_found ?? 0) > 0 && (
                          <span className="text-blue-700 dark:text-blue-300">
                            <strong>{nfeStep1Result.completos_found}</strong> XML(s) completo(s) ja disponivel(is)
                          </span>
                        )}
                      </div>
                      {/* SEFAZ diagnostic */}
                      <div className="border-t border-amber-200 dark:border-amber-700 pt-1.5 space-y-0.5">
                        <p className="text-[10px] font-mono text-amber-700 dark:text-amber-400">
                          SEFAZ cStat: <strong>{nfeStep1Result.sefaz_cstat ?? "?"}</strong> — {nfeStep1Result.sefaz_xmotivo ?? "sem resposta"}
                        </p>
                        <p className="text-[10px] font-mono text-amber-700/70 dark:text-amber-400/70">
                          NSU enviado: {nfeStep1Result.ult_nsu_used ?? "?"} | NSU retornado: {nfeStep1Result.ult_nsu_returned ?? "?"} | maxNSU: {nfeStep1Result.max_nsu ?? "?"} | docs na resposta: {nfeStep1Result.total_docs_in_response ?? 0}
                        </p>
                      </div>
                    </div>
                    {nfeStep1Result.results?.map((r, i) => (
                      <div
                        key={i}
                        className={`rounded-lg border p-2 text-xs ${
                          r.status === "ciencia_ok" || r.status === "saved"
                            ? "border-emerald-200 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/30"
                            : r.status === "enqueued" || r.status === "skipped"
                              ? "border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-900/30"
                              : "border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-950/30"
                        }`}
                      >
                        <div className="flex items-center gap-2">
                          <Badge variant="secondary" className="text-[10px]">{r.tipo}</Badge>
                          <span className={`font-medium ${
                            r.status === "ciencia_ok" || r.status === "saved" ? "text-emerald-700 dark:text-emerald-300"
                              : r.status === "enqueued" || r.status === "skipped" ? "text-gray-600 dark:text-gray-400"
                              : "text-red-700 dark:text-red-300"
                          }`}>
                            {r.status}
                          </span>
                          {r.cstat && <span className="text-muted-foreground">cStat {r.cstat}</span>}
                        </div>
                        <p className="text-muted-foreground mt-0.5 font-mono text-[10px] truncate">
                          {r.chave}
                        </p>
                        {(r.xmotivo || r.detail) && (
                          <p className="text-muted-foreground mt-0.5">{r.xmotivo || r.detail}</p>
                        )}
                      </div>
                    ))}
                  </>
                )}
              </div>
            )}
          </div>

          {/* Step 2 */}
          <div className="space-y-3">
            <div>
              <p className="text-sm font-medium">Etapa 2: Capturar XML completo</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Busca os XMLs completos das NF-e cuja ciencia ja foi processada pela SEFAZ.
              </p>
            </div>
            <Button
              className="gap-2 bg-emerald-600 hover:bg-emerald-700 text-white"
              disabled={nfeStep2Status === "loading" || !cleanCnpj}
              onClick={handleNfeStep2}
            >
              {nfeStep2Status === "loading" ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Download className="size-4" />
              )}
              {nfeStep2Status === "loading" ? "Buscando XMLs..." : "Capturar XML Completo"}
            </Button>

            {/* Step 2 results */}
            {nfeStep2Result && (
              <div className="space-y-2">
                {nfeStep2Result.error ? (
                  <div className="rounded-lg border border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-950/30 p-3">
                    <p className="text-xs text-red-700 dark:text-red-300 font-medium">{nfeStep2Result.error}</p>
                  </div>
                ) : (
                  <>
                    <div className="rounded-lg border border-emerald-200 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/30 p-3 space-y-1">
                      <div className="flex gap-4 text-xs flex-wrap">
                        <span className="text-emerald-800 dark:text-emerald-300">
                          <strong>{nfeStep2Result.xml_found ?? 0}</strong> XML(s) encontrado(s)
                        </span>
                        <span className="text-emerald-700 dark:text-emerald-300">
                          <strong>{nfeStep2Result.saved ?? 0}</strong> salvo(s) no banco
                        </span>
                        {(nfeStep2Result.still_pending ?? 0) > 0 && (
                          <span className="text-amber-700 dark:text-amber-300">
                            <strong>{nfeStep2Result.still_pending}</strong> ainda pendente(s)
                          </span>
                        )}
                      </div>
                    </div>
                    {nfeStep2Result.results?.map((r, i) => (
                      <div
                        key={i}
                        className={`rounded-lg border p-2 text-xs ${
                          r.status === "saved"
                            ? "border-emerald-200 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/30"
                            : r.status === "pending"
                              ? "border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/30"
                              : r.status === "empty"
                                ? "border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-900/30"
                                : "border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-950/30"
                        }`}
                      >
                        <div className="flex items-center gap-2">
                          <span className={`font-medium ${
                            r.status === "saved" ? "text-emerald-700 dark:text-emerald-300"
                              : r.status === "pending" ? "text-amber-700 dark:text-amber-300"
                              : "text-gray-600 dark:text-gray-400"
                          }`}>
                            {r.status === "saved" ? "XML salvo" : r.status === "pending" ? "Pendente" : r.status === "empty" ? "Fila vazia" : r.status}
                          </span>
                          {r.tentativas && <span className="text-muted-foreground">tentativa {r.tentativas}</span>}
                        </div>
                        {r.chave && (
                          <p className="text-muted-foreground mt-0.5 font-mono text-[10px] truncate">
                            {r.chave}
                          </p>
                        )}
                        {r.detail && (
                          <p className="text-muted-foreground mt-0.5">{r.detail}</p>
                        )}
                      </div>
                    ))}
                  </>
                )}
              </div>
            )}
          </div>
          </div>{/* close grid */}

          {/* Retry Ciencia button */}
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <Button
                variant="outline"
                className="gap-2 border-amber-300 text-amber-700 hover:bg-amber-50 dark:border-amber-700 dark:text-amber-300"
                disabled={nfeRetryCienciaStatus === "loading" || !cleanCnpj}
                onClick={handleRetryCiencia}
              >
                {nfeRetryCienciaStatus === "loading" ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <ClipboardList className="size-4" />
                )}
                {nfeRetryCienciaStatus === "loading" ? "Reenviando..." : "Reenviar Ciencia (fila pendente)"}
              </Button>
              <span className="text-xs text-muted-foreground">
                Reenvia ciencia para resumos na fila sem chamar SEFAZ DistDFe
              </span>
            </div>

            {nfeRetryCienciaResult && (
              <div className="space-y-2">
                {nfeRetryCienciaResult.error ? (
                  <div className="rounded-lg border border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-950/30 p-3">
                    <p className="text-xs text-red-700 dark:text-red-300 font-medium">{nfeRetryCienciaResult.error}</p>
                  </div>
                ) : (
                  <>
                    <div className="rounded-lg border border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/30 p-3">
                      <div className="flex gap-4 text-xs flex-wrap">
                        <span className="text-amber-800 dark:text-amber-300">
                          <strong>{nfeRetryCienciaResult.pending_in_queue ?? 0}</strong> na fila
                        </span>
                        <span className="text-emerald-700 dark:text-emerald-300">
                          <strong>{nfeRetryCienciaResult.ciencia_sent ?? 0}</strong> ciencia(s) enviada(s)
                        </span>
                        {(nfeRetryCienciaResult.ciencia_failed ?? 0) > 0 && (
                          <span className="text-red-700 dark:text-red-300">
                            <strong>{nfeRetryCienciaResult.ciencia_failed}</strong> falha(s)
                          </span>
                        )}
                      </div>
                    </div>
                    {nfeRetryCienciaResult.results?.map((r, i) => (
                      <div
                        key={i}
                        className={`rounded-lg border p-2 text-xs ${
                          r.status === "ciencia_ok"
                            ? "border-emerald-200 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/30"
                            : "border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-950/30"
                        }`}
                      >
                        <div className="flex items-center gap-2">
                          <span className={`font-medium ${
                            r.status === "ciencia_ok" ? "text-emerald-700 dark:text-emerald-300" : "text-red-700 dark:text-red-300"
                          }`}>
                            {r.status === "ciencia_ok" ? "Ciencia OK" : r.status}
                          </span>
                          {r.cstat && <span className="text-muted-foreground">cStat {r.cstat}</span>}
                        </div>
                        <p className="text-muted-foreground mt-0.5 font-mono text-[10px] truncate">{r.chave}</p>
                        {(r.xmotivo || r.detail) && (
                          <p className="text-muted-foreground mt-0.5">{r.xmotivo || r.detail}</p>
                        )}
                      </div>
                    ))}
                  </>
                )}
              </div>
            )}
          </div>

          {/* Wait notice */}
          <div className="flex items-start gap-2 rounded-md border border-blue-200 bg-blue-50 dark:border-blue-800 dark:bg-blue-950/30 p-3">
            <Clock className="size-4 text-blue-500 dark:text-blue-400 mt-0.5 flex-shrink-0" />
            <p className="text-xs text-blue-700 dark:text-blue-300">
              Aguarde <strong>30-60 minutos</strong> entre a Etapa 1 e a Etapa 2 para a SEFAZ processar a ciência.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
