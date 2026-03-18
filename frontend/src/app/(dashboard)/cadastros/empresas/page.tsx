"use client"

import { useState, useEffect, useCallback } from "react"
import { Building, ShieldCheck, Calendar, Inbox, Loader2 } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { useSettings } from "@/hooks/use-settings"
import { getSupabase } from "@/lib/supabase"

interface Empresa {
  id: number
  razaoSocial: string // extraído do CN do certificado
  cnpj: string // extraído do certificado
  certificadoValidade: string // validade do cert
  certificadoStatus: "Ativo" | "Expirado"
  ultimaCaptura: string | null
}

const mockEmpresas: Empresa[] = [
  {
    id: 1,
    razaoSocial: "DISTRIBUIDORA ALIMENTOS LTDA:12345678000190",
    cnpj: "12.345.678/0001-90",
    certificadoValidade: "01/04/2025 - 01/04/2027",
    certificadoStatus: "Ativo",
    ultimaCaptura: "16/03/2026 08:30",
  },
  {
    id: 2,
    razaoSocial: "TECH SOLUTIONS S.A.:98765432000110",
    cnpj: "98.765.432/0001-10",
    certificadoValidade: "15/06/2025 - 15/06/2026",
    certificadoStatus: "Ativo",
    ultimaCaptura: "16/03/2026 08:25",
  },
  {
    id: 3,
    razaoSocial: "METALURGICA BRASIL ME:11222333000144",
    cnpj: "11.222.333/0001-44",
    certificadoValidade: "10/01/2025 - 10/04/2026",
    certificadoStatus: "Ativo",
    ultimaCaptura: "16/03/2026 08:20",
  },
  {
    id: 4,
    razaoSocial: "FARMACIA POPULAR EIRELI:44555666000177",
    cnpj: "44.555.666/0001-77",
    certificadoValidade: "20/03/2024 - 20/03/2025",
    certificadoStatus: "Expirado",
    ultimaCaptura: null,
  },
  {
    id: 5,
    razaoSocial: "CONSTRUTORA HORIZONTE LTDA:55666777000368",
    cnpj: "55.666.777/0003-68",
    certificadoValidade: "05/08/2025 - 05/08/2027",
    certificadoStatus: "Ativo",
    ultimaCaptura: "16/03/2026 08:15",
  },
]

function extractName(cn: string): string {
  // CN format: "RAZAO SOCIAL:CNPJ" — extract just the name
  const parts = cn.split(":")
  return parts[0]
}

function formatCnpj(raw: string): string {
  const digits = raw.replace(/\D/g, "")
  if (digits.length !== 14) return raw
  return `${digits.slice(0, 2)}.${digits.slice(2, 5)}.${digits.slice(5, 8)}/${digits.slice(8, 12)}-${digits.slice(12)}`
}

export default function EmpresasPage() {
  const { settings } = useSettings()

  const [realEmpresas, setRealEmpresas] = useState<Empresa[]>([])
  const [realLoading, setRealLoading] = useState(false)

  const loadRealData = useCallback(async () => {
    setRealLoading(true)
    try {
      const sb = getSupabase()
      const { data, error } = await sb
        .from('certificates')
        .select('id, company_name, cnpj, valid_from, valid_until, is_active')
        .order('created_at', { ascending: false })

      if (!error && data) {
        const mapped: Empresa[] = data.map((cert: any, i: number) => {
          const now = new Date()
          const validUntil = cert.valid_until ? new Date(cert.valid_until) : null
          const isExpired = validUntil ? validUntil < now : false

          const validFrom = cert.valid_from
            ? new Date(cert.valid_from).toLocaleDateString("pt-BR")
            : "--"
          const validTo = validUntil
            ? validUntil.toLocaleDateString("pt-BR")
            : "--"

          return {
            id: i + 1,
            razaoSocial: cert.company_name || cert.cnpj || "Sem nome",
            cnpj: cert.cnpj ? formatCnpj(cert.cnpj) : "--",
            certificadoValidade: `${validFrom} - ${validTo}`,
            certificadoStatus: isExpired ? "Expirado" : "Ativo",
            ultimaCaptura: null,
          }
        })
        setRealEmpresas(mapped)
      }
    } catch (e) {
      console.error("[DFeAxis] Error loading empresas:", e)
    } finally {
      setRealLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!settings.showMockData) loadRealData()
  }, [settings.showMockData, loadRealData])

  const empresas = settings.showMockData ? mockEmpresas : realEmpresas

  if (!settings.showMockData && realLoading) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Empresas / CNPJs</h1>
          <p className="text-sm text-muted-foreground">
            Dados extraídos automaticamente dos certificados A1. Para adicionar uma empresa, faça o upload do certificado em <strong>Certificados A1</strong>.
          </p>
        </div>
        <div className="flex flex-col items-center justify-center py-16 gap-3">
          <Loader2 className="size-8 animate-spin text-muted-foreground" />
          <p className="text-sm text-muted-foreground">Carregando empresas...</p>
        </div>
      </div>
    )
  }

  if (!settings.showMockData && realEmpresas.length === 0) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Empresas / CNPJs</h1>
          <p className="text-sm text-muted-foreground">
            Dados extraídos automaticamente dos certificados A1. Para adicionar uma empresa, faça o upload do certificado em <strong>Certificados A1</strong>.
          </p>
        </div>
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <Inbox className="size-12 text-muted-foreground/30 mb-4" />
          <p className="text-sm text-muted-foreground">Nenhuma empresa cadastrada. As empresas são criadas automaticamente ao enviar um certificado A1.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Empresas / CNPJs</h1>
        <p className="text-sm text-muted-foreground">
          Dados extraídos automaticamente dos certificados A1. Para adicionar uma empresa, faça o upload do certificado em <strong>Certificados A1</strong>.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {empresas.map((emp) => (
          <Card key={emp.id}>
            <CardHeader className="pb-3">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-2">
                  <Building className="size-5 text-muted-foreground shrink-0" />
                  <CardTitle className="text-sm leading-snug">
                    {extractName(emp.razaoSocial)}
                  </CardTitle>
                </div>
                <Badge
                  variant={emp.certificadoStatus === "Ativo" ? "default" : "destructive"}
                  className="shrink-0"
                >
                  {emp.certificadoStatus}
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">CNPJ</span>
                <span className="font-mono">{emp.cnpj}</span>
              </div>
              <div className="flex justify-between items-center gap-2">
                <span className="text-muted-foreground flex items-center gap-1">
                  <ShieldCheck className="size-3" />
                  Certificado
                </span>
                <span className="text-xs">{emp.certificadoValidade}</span>
              </div>
              {emp.ultimaCaptura && (
                <div className="flex justify-between items-center gap-2">
                  <span className="text-muted-foreground flex items-center gap-1">
                    <Calendar className="size-3" />
                    Última captura
                  </span>
                  <span className="text-xs">{emp.ultimaCaptura}</span>
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}
