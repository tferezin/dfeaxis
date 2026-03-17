"use client"

import { Building, ShieldCheck, Calendar } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"

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

export default function EmpresasPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Empresas / CNPJs</h1>
        <p className="text-sm text-muted-foreground">
          Dados extraídos automaticamente dos certificados A1. Para adicionar uma empresa, faça o upload do certificado em <strong>Certificados A1</strong>.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {mockEmpresas.map((emp) => (
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
