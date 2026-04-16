"use client"

import { useState, useRef } from "react"
import {
  Play,
  Loader2,
  CheckCircle2,
  AlertCircle,
  FileText,
  Truck,
  Building2,
  FileStack,
  Inbox,
  Upload,
  ShieldCheck,
  Database,
} from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useSettings } from "@/hooks/use-settings"
import { getSupabase } from "@/lib/supabase"

interface CertEntry {
  id: number
  empresa: string
  cnpj: string
  status: "idle" | "loading" | "success" | "error"
  docsFound: number
  message?: string
}

const mockCerts: CertEntry[] = [
  { id: 1, empresa: "Distribuidora Alimentos Ltda", cnpj: "12.345.678/0001-90", status: "idle", docsFound: 0 },
  { id: 2, empresa: "Tech Solutions S.A.", cnpj: "98.765.432/0001-10", status: "idle", docsFound: 0 },
  { id: 3, empresa: "Metalurgica Brasil ME", cnpj: "11.222.333/0001-44", status: "idle", docsFound: 0 },
  { id: 5, empresa: "Construtora Horizonte Ltda", cnpj: "55.666.777/0003-68", status: "idle", docsFound: 0 },
  { id: 6, empresa: "Auto Pecas Centro Sul", cnpj: "66.777.888/0001-99", status: "idle", docsFound: 0 },
]

const docTypes = [
  { key: "nfe", label: "NF-e", icon: FileText, checked: true },
  { key: "cte", label: "CT-e", icon: Truck, checked: true },
  { key: "mdfe", label: "MDF-e", icon: FileStack, checked: true },
  { key: "nfse", label: "NFS-e", icon: Building2, checked: true },
]

export default function CapturaManualPage() {
  const { settings } = useSettings()
  const [certs, setCerts] = useState<CertEntry[]>(mockCerts)
  const fileRef = useRef<HTMLInputElement>(null)
  const [testCnpj, setTestCnpj] = useState("")
  const [testPassword, setTestPassword] = useState("")
  const [testStatus, setTestStatus] = useState<"idle" | "loading">("idle")
  const [testResult, setTestResult] = useState<{
    error?: string;
    certificate?: { subject: string; valid_from: string; valid_until: string };
    cnpj?: string;
    ambiente?: string;
    results?: Array<{
      tipo: string;
      status: string;
      cstat?: string;
      xmotivo?: string;
      docs_found?: number;
      latency_ms?: number;
      message?: string;
    }>;
    message?: string;
  } | null>(null)

  const handleTestCapture = async () => {
    const file = fileRef.current?.files?.[0]
    if (!file || !testCnpj || !testPassword) {
      setTestResult({ error: "Preencha todos os campos: .pfx, CNPJ e senha." })
      return
    }
    setTestStatus("loading")
    setTestResult(null)
    console.log("[DFeAxis] ===== CAPTURA MANUAL INICIADA =====")
    console.log("[DFeAxis] Arquivo:", file.name, "CNPJ:", testCnpj, "Tipos:", selectedTipos)

    const cleanCnpj = testCnpj.replace(/\D/g, "")
    const _raw = process.env.NEXT_PUBLIC_API_URL || "https://dfeaxis-production.up.railway.app"
    const backendUrl = _raw.endsWith("/api/v1") ? _raw : `${_raw}/api/v1`
    console.log("[DFeAxis] Backend URL:", backendUrl)

    try {
      // Get auth token
      console.log("[DFeAxis] 🔐 Obtendo sessão...")
      const sb = getSupabase()
      const { data: { session } } = await sb.auth.getSession()
      const token = session?.access_token

      if (!token) {
        console.error("[DFeAxis] ❌ Sem token — sessão expirada")
        setTestResult({ error: "Sessão expirada. Faça login novamente." })
        return
      }
      console.log("[DFeAxis] ✅ Token obtido")

      const authHeaders = {
        "Authorization": `Bearer ${token}`,
      }

      // Step 1: Upload certificate to backend (registers in DB)
      console.log(`[DFeAxis] 📤 Step 1: Upload certificado para ${backendUrl}/certificates/upload`)
      const uploadForm = new FormData()
      uploadForm.append("pfx_file", file)
      uploadForm.append("cnpj", cleanCnpj)
      uploadForm.append("senha", testPassword)
      uploadForm.append("polling_mode", "manual")

      const uploadRes = await fetch(`${backendUrl}/certificates/upload`, {
        method: "POST",
        headers: authHeaders,
        body: uploadForm,
      })

      console.log(`[DFeAxis] Upload response: ${uploadRes.status} ${uploadRes.statusText}`)

      if (!uploadRes.ok) {
        const uploadErr = await uploadRes.json().catch(() => ({}))
        console.error("[DFeAxis] ❌ Erro upload:", uploadErr)
        setTestResult({ error: `Erro ao cadastrar certificado: ${uploadErr.detail || uploadRes.statusText}` })
        return
      }

      const uploadData = await uploadRes.json()
      console.log("[DFeAxis] ✅ Certificado cadastrado:", uploadData)

      // Step 2: Trigger polling (queries SEFAZ + saves to DB)
      console.log(`[DFeAxis] 🔄 Step 2: Polling SEFAZ para tipos: ${selectedTipos.join(", ")}`)
      const pollingRes = await fetch(`${backendUrl}/polling/trigger`, {
        method: "POST",
        headers: { ...authHeaders, "Content-Type": "application/json" },
        body: JSON.stringify({
          cnpj: cleanCnpj,
          tipos: selectedTipos,
        }),
      })

      console.log(`[DFeAxis] Polling response: ${pollingRes.status} ${pollingRes.statusText}`)

      if (!pollingRes.ok) {
        const pollingErr = await pollingRes.json().catch(() => ({}))
        console.error("[DFeAxis] ❌ Erro polling:", pollingErr)
        setTestResult({
          certificate: { subject: `Certificado cadastrado (${uploadData.cnpj})`, valid_from: "", valid_until: String(uploadData.valid_until || "") },
          cnpj: cleanCnpj,
          error: `Certificado cadastrado, mas erro na captura: ${pollingErr.detail || pollingRes.statusText}`,
        })
        return
      }

      const pollingData = await pollingRes.json()
      console.log("[DFeAxis] ✅ Polling completo:", JSON.stringify(pollingData, null, 2))

      // Build results from polling response (no second SEFAZ call needed)
      const results = (pollingData.results || []).map((r: { tipo: string; status: string; cstat: string; xmotivo: string; docs_found: number; latency_ms: number; error?: string; saved_to_db: boolean }) => ({
        tipo: r.tipo,
        status: r.error ? "error" : "success",
        cstat: r.cstat,
        xmotivo: r.xmotivo,
        docs_found: r.docs_found,
        latency_ms: r.latency_ms,
        message: r.error || (r.saved_to_db ? `${r.docs_found} doc(s) salvo(s)` : ""),
      }))

      setTestResult({
        certificate: {
          subject: `Certificado cadastrado (${uploadData.cnpj})`,
          valid_from: "",
          valid_until: String(uploadData.valid_until || ""),
        },
        cnpj: cleanCnpj,
        results,
        message: `Certificado cadastrado. ${pollingData.docs_found || 0} documento(s) capturado(s) e salvo(s) no banco.`,
      })
    } catch (err) {
      setTestResult({ error: `Erro: ${String(err)}` })
    } finally {
      setTestStatus("idle")
    }
  }
  const [tipos, setTipos] = useState<Record<string, boolean>>(
    Object.fromEntries(docTypes.map((d) => [d.key, d.checked]))
  )
  const [allRunning, setAllRunning] = useState(false)

  const selectedTipos = Object.entries(tipos)
    .filter(([, v]) => v)
    .map(([k]) => k)

  const simulateCapture = (certId: number) => {
    setCerts((prev) =>
      prev.map((c) => (c.id === certId ? { ...c, status: "loading" as const, docsFound: 0 } : c))
    )
    // Simula resposta da SEFAZ
    setTimeout(() => {
      const docs = Math.floor(Math.random() * 8)
      setCerts((prev) =>
        prev.map((c) =>
          c.id === certId
            ? {
                ...c,
                status: "success" as const,
                docsFound: docs,
                message: docs > 0 ? `${docs} documentos capturados` : "Nenhum documento novo",
              }
            : c
        )
      )
    }, 1500 + Math.random() * 2000)
  }

  const captureAll = () => {
    setAllRunning(true)
    certs.forEach((c, i) => {
      setTimeout(() => simulateCapture(c.id), i * 500)
    })
    setTimeout(() => setAllRunning(false), certs.length * 500 + 3500)
  }

  const captureSingle = (certId: number) => {
    simulateCapture(certId)
  }

  const totalDocs = certs.reduce((sum, c) => sum + c.docsFound, 0)
  const allDone = certs.every((c) => c.status === "success" || c.status === "error")

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Captura Manual</h1>
          <p className="text-sm text-muted-foreground">
            Dispare a captura de documentos recebidos sob demanda.
          </p>
        </div>
        <Button
          onClick={captureAll}
          disabled={allRunning || selectedTipos.length === 0}
          className="gap-2"
        >
          {allRunning ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <Play className="size-4" />
          )}
          {allRunning ? "Capturando..." : "Capturar todos os CNPJs"}
        </Button>
      </div>

      {/* Tipos de documento */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Tipos de documento</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-3">
            {docTypes.map((dt) => {
              const Icon = dt.icon
              return (
                <label
                  key={dt.key}
                  className={`flex items-center gap-2 rounded-lg border px-4 py-2 cursor-pointer transition-colors ${
                    tipos[dt.key]
                      ? "border-primary bg-primary/5 text-primary"
                      : "border-border text-muted-foreground hover:border-muted-foreground/30"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={tipos[dt.key]}
                    onChange={(e) => setTipos((prev) => ({ ...prev, [dt.key]: e.target.checked }))}
                    className="sr-only"
                  />
                  <Icon className="size-4" />
                  <span className="text-sm font-medium">{dt.label}</span>
                </label>
              )
            })}
          </div>
        </CardContent>
      </Card>

      {/* Resultado geral */}
      {allDone && totalDocs >= 0 && certs.some((c) => c.status !== "idle") && (
        <div className="flex items-center gap-3 rounded-lg border border-emerald-200 bg-emerald-50 p-4">
          <CheckCircle2 className="size-5 text-emerald-600" />
          <div>
            <p className="text-sm font-medium text-emerald-800">
              Captura concluída — {totalDocs} documento{totalDocs !== 1 ? "s" : ""} encontrado{totalDocs !== 1 ? "s" : ""}
            </p>
            <p className="text-xs text-emerald-700 mt-0.5">
              Os documentos estão disponíveis em Documentos Recebidos.
            </p>
          </div>
        </div>
      )}

      {/* Teste direto — upload de .pfx sem banco de dados */}
      <Card className="border-amber-200 bg-amber-50/50">
        <CardHeader className="pb-2">
          <div className="flex items-center gap-2">
            <ShieldCheck className="size-5 text-amber-600" />
            <CardTitle className="text-base">Teste rápido com certificado</CardTitle>
            <Badge variant="secondary" className="text-[10px]">Temporário</Badge>
          </div>
          <p className="text-xs text-muted-foreground">
            Faça upload do certificado A1 (.pfx) para testar a conexão com a SEFAZ sem precisar de banco de dados.
          </p>
        </CardHeader>
        <CardContent className="space-y-3 pt-0">
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Certificado (.pfx)</Label>
              <Input
                type="file"
                accept=".pfx,.p12"
                className="text-xs"
                ref={fileRef}
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">CNPJ</Label>
              <Input
                placeholder="00.000.000/0000-00"
                className="text-xs"
                value={testCnpj}
                onChange={(e) => setTestCnpj(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Senha do certificado</Label>
              <Input
                type="password"
                placeholder="Senha"
                className="text-xs"
                value={testPassword}
                onChange={(e) => setTestPassword(e.target.value)}
              />
            </div>
          </div>
          <Button
            size="sm"
            className="gap-1.5"
            disabled={testStatus === "loading" || selectedTipos.length === 0}
            onClick={handleTestCapture}
          >
            {testStatus === "loading" ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Upload className="size-3.5" />
            )}
            {testStatus === "loading" ? "Consultando SEFAZ (homologação)..." : "Testar captura na SEFAZ"}
          </Button>

          {/* Resultados */}
          {testResult && (
            <div className="space-y-2 mt-2">
              {testResult.error ? (
                <div className="rounded-lg border border-red-200 bg-red-50 p-3">
                  <p className="text-xs text-red-700 font-medium">{testResult.error}</p>
                  {testResult.message && <p className="text-xs text-red-600 mt-1">{testResult.message}</p>}
                </div>
              ) : (
                <>
                  {testResult.certificate && (
                    <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3">
                      <p className="text-xs font-medium text-emerald-800">Certificado válido</p>
                      <p className="text-xs text-emerald-700 mt-0.5 font-mono">{testResult.certificate.subject}</p>
                      <p className="text-xs text-emerald-600 mt-0.5">Validade: {testResult.certificate.valid_from} até {testResult.certificate.valid_until}</p>
                    </div>
                  )}
                  {testResult.message && (
                    <div className="rounded-lg border border-blue-200 bg-blue-50 p-3 flex items-center gap-2">
                      <Database className="w-4 h-4 text-blue-600 flex-shrink-0" />
                      <p className="text-xs font-medium text-blue-800">{testResult.message}</p>
                    </div>
                  )}
                  {testResult.results?.map((r, i) => (
                    <div
                      key={i}
                      className={`rounded-lg border p-3 ${
                        r.status === "success"
                          ? r.cstat === "137" || r.cstat === "138"
                            ? "border-emerald-200 bg-emerald-50"
                            : "border-amber-200 bg-amber-50"
                          : r.status === "skipped"
                            ? "border-gray-200 bg-gray-50"
                            : "border-red-200 bg-red-50"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <Badge variant="secondary" className="text-[10px]">{r.tipo}</Badge>
                          <span className={`text-xs font-medium ${
                            r.status === "success" ? "text-emerald-700" : r.status === "skipped" ? "text-gray-600" : "text-red-700"
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
                        <p className="text-xs mt-1 font-medium text-emerald-700">{r.docs_found} documento(s) encontrado(s)</p>
                      )}
                    </div>
                  ))}
                </>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Lista de CNPJs */}
      {!settings.showMockData ? (
        <div className="flex flex-col items-center justify-center py-8 text-center">
          <Inbox className="size-10 text-muted-foreground/30 mb-3" />
          <p className="text-xs text-muted-foreground">Certificados cadastrados aparecerão aqui quando o banco de dados estiver conectado.</p>
        </div>
      ) : (
      <div className="space-y-3">
        {certs.map((cert) => (
          <Card key={cert.id}>
            <CardContent className="flex items-center gap-4 py-4">
              {/* Status indicator */}
              <div className="shrink-0">
                {cert.status === "idle" && (
                  <div className="size-10 rounded-full bg-muted flex items-center justify-center">
                    <Play className="size-4 text-muted-foreground" />
                  </div>
                )}
                {cert.status === "loading" && (
                  <div className="size-10 rounded-full bg-blue-100 flex items-center justify-center">
                    <Loader2 className="size-4 text-blue-600 animate-spin" />
                  </div>
                )}
                {cert.status === "success" && (
                  <div className="size-10 rounded-full bg-emerald-100 flex items-center justify-center">
                    <CheckCircle2 className="size-4 text-emerald-600" />
                  </div>
                )}
                {cert.status === "error" && (
                  <div className="size-10 rounded-full bg-red-100 flex items-center justify-center">
                    <AlertCircle className="size-4 text-red-600" />
                  </div>
                )}
              </div>

              {/* Info */}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{cert.empresa}</p>
                <p className="text-xs text-muted-foreground font-mono">{cert.cnpj}</p>
              </div>

              {/* Result */}
              <div className="text-right shrink-0">
                {cert.status === "success" && (
                  <div>
                    <Badge variant={cert.docsFound > 0 ? "default" : "secondary"}>
                      {cert.docsFound} doc{cert.docsFound !== 1 ? "s" : ""}
                    </Badge>
                    <p className="text-xs text-muted-foreground mt-1">{cert.message}</p>
                  </div>
                )}
                {cert.status === "loading" && (
                  <span className="text-xs text-blue-600">Consultando SEFAZ...</span>
                )}
                {cert.status === "error" && (
                  <span className="text-xs text-red-600">Erro na captura</span>
                )}
              </div>

              <Separator orientation="vertical" className="h-8" />

              {/* Action */}
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5 shrink-0"
                disabled={cert.status === "loading" || allRunning}
                onClick={() => captureSingle(cert.id)}
              >
                {cert.status === "loading" ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <Play className="size-3.5" />
                )}
                Capturar
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
      )}
    </div>
  )
}
