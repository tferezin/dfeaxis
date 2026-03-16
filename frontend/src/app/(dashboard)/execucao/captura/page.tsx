"use client"

import { useState } from "react"
import {
  Play,
  Loader2,
  CheckCircle2,
  AlertCircle,
  FileText,
  Truck,
  Building2,
  FileStack,
} from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"

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
  { key: "mdfe", label: "MDF-e", icon: FileStack, checked: false },
  { key: "nfse", label: "NFS-e", icon: Building2, checked: false },
]

export default function CapturaManualPage() {
  const [certs, setCerts] = useState<CertEntry[]>(mockCerts)
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

      {/* Lista de CNPJs */}
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
    </div>
  )
}
