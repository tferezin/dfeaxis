"use client"

import { useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet"
import { Separator } from "@/components/ui/separator"
import {
  Plus,
  Trash2,
  RefreshCw,
  ShieldCheck,
  Upload,
} from "lucide-react"

interface Certificate {
  id: number
  empresa: string
  cnpj: string
  validadeDe: string
  validadeAte: string
  status: "Ativo" | "Inativo"
  ultimaCaptura: string
  diasRestantes: number
}

const mockCertificates: Certificate[] = [
  {
    id: 1,
    empresa: "Distribuidora Alimentos Ltda",
    cnpj: "12.345.678/0001-90",
    validadeDe: "01/04/2025",
    validadeAte: "01/04/2027",
    status: "Ativo",
    ultimaCaptura: "16/03/2026 08:30",
    diasRestantes: 381,
  },
  {
    id: 2,
    empresa: "Tech Solutions S.A.",
    cnpj: "98.765.432/0001-10",
    validadeDe: "15/06/2025",
    validadeAte: "15/06/2026",
    status: "Ativo",
    ultimaCaptura: "16/03/2026 08:25",
    diasRestantes: 91,
  },
  {
    id: 3,
    empresa: "Metalurgica Brasil ME",
    cnpj: "11.222.333/0001-44",
    validadeDe: "10/01/2025",
    validadeAte: "10/04/2026",
    status: "Ativo",
    ultimaCaptura: "16/03/2026 08:20",
    diasRestantes: 25,
  },
  {
    id: 4,
    empresa: "Farmacia Popular Eireli",
    cnpj: "44.555.666/0001-77",
    validadeDe: "20/03/2024",
    validadeAte: "20/03/2025",
    status: "Inativo",
    ultimaCaptura: "20/03/2025 12:00",
    diasRestantes: -361,
  },
  {
    id: 5,
    empresa: "Construtora Horizonte Ltda",
    cnpj: "55.666.777/0003-68",
    validadeDe: "05/08/2025",
    validadeAte: "05/08/2027",
    status: "Ativo",
    ultimaCaptura: "16/03/2026 08:15",
    diasRestantes: 507,
  },
  {
    id: 6,
    empresa: "Auto Pecas Centro Sul",
    cnpj: "66.777.888/0001-99",
    validadeDe: "12/11/2025",
    validadeAte: "12/11/2026",
    status: "Ativo",
    ultimaCaptura: "16/03/2026 08:10",
    diasRestantes: 241,
  },
]

function getValidityColor(diasRestantes: number) {
  if (diasRestantes < 0) return "text-red-600 dark:text-red-400"
  if (diasRestantes <= 30) return "text-amber-600 dark:text-amber-400"
  return "text-emerald-600 dark:text-emerald-400"
}

function getValidityBg(diasRestantes: number) {
  if (diasRestantes < 0) return "bg-red-50 dark:bg-red-950/30"
  if (diasRestantes <= 30) return "bg-amber-50 dark:bg-amber-950/30"
  return "bg-emerald-50 dark:bg-emerald-950/30"
}

function getValidityLabel(diasRestantes: number) {
  if (diasRestantes < 0) return "Expirado"
  if (diasRestantes <= 30) return `${diasRestantes} dias restantes`
  return `${diasRestantes} dias restantes`
}

export default function CertificadosPage() {
  const [sheetOpen, setSheetOpen] = useState(false)

  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Certificados A1</h1>
          <p className="text-sm text-muted-foreground">
            Gerencie os certificados digitais das suas empresas
          </p>
        </div>
        <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
          <SheetTrigger
            render={
              <Button>
                <Plus className="size-4" />
                Novo Certificado
              </Button>
            }
          />
          <SheetContent side="right">
            <SheetHeader>
              <SheetTitle>Upload de Certificado</SheetTitle>
              <SheetDescription>
                Envie o certificado digital A1 (.pfx). A empresa será cadastrada automaticamente.
              </SheetDescription>
            </SheetHeader>
            <div className="flex flex-col gap-4 px-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="cert-file">Arquivo do certificado (.pfx)</Label>
                <div className="flex items-center gap-2">
                  <Input
                    id="cert-file"
                    type="file"
                    accept=".pfx,.p12"
                    className="flex-1"
                  />
                </div>
              </div>

              <div className="flex flex-col gap-2">
                <Label htmlFor="cert-cnpj">CNPJ</Label>
                <Input
                  id="cert-cnpj"
                  placeholder="00.000.000/0000-00"
                />
              </div>

              <div className="flex flex-col gap-2">
                <Label htmlFor="cert-senha">Senha do certificado</Label>
                <Input
                  id="cert-senha"
                  type="password"
                  placeholder="Digite a senha"
                />
              </div>

              <Separator />

              <p className="text-xs text-muted-foreground">
                O modo de operação (automático ou manual) é configurado globalmente em <strong>Configurações</strong> e aplica-se a todos os CNPJs.
              </p>
            </div>
            <SheetFooter>
              <Button className="w-full gap-2" onClick={() => setSheetOpen(false)}>
                <Upload className="size-4" />
                Enviar
              </Button>
            </SheetFooter>
          </SheetContent>
        </Sheet>
      </div>

      {/* Cards Grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {mockCertificates.map((cert) => (
          <Card key={cert.id}>
            <CardHeader>
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-2">
                  <ShieldCheck className="size-5 text-muted-foreground" />
                  <CardTitle className="leading-snug">{cert.empresa}</CardTitle>
                </div>
                <Badge variant={cert.status === "Ativo" ? "default" : "destructive"}>
                  {cert.status}
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <div className="flex flex-col gap-1">
                <span className="text-xs font-medium text-muted-foreground">CNPJ</span>
                <span className="font-mono text-sm">{cert.cnpj}</span>
              </div>

              <div className="flex flex-col gap-1">
                <span className="text-xs font-medium text-muted-foreground">Validade</span>
                <div className="flex items-center gap-2">
                  <span className="text-sm">{cert.validadeDe} - {cert.validadeAte}</span>
                </div>
                <span className={`inline-flex w-fit rounded-md px-2 py-0.5 text-xs font-medium ${getValidityColor(cert.diasRestantes)} ${getValidityBg(cert.diasRestantes)}`}>
                  {getValidityLabel(cert.diasRestantes)}
                </span>
              </div>

              <div className="flex flex-col gap-1">
                <span className="text-xs font-medium text-muted-foreground">Ultima captura</span>
                <span className="text-sm">{cert.ultimaCaptura}</span>
              </div>
            </CardContent>
            <CardFooter className="gap-2">
              <Button variant="outline" size="sm" className="flex-1 gap-1.5">
                <RefreshCw className="size-3.5" />
                Renovar
              </Button>
              <Button variant="destructive" size="sm" className="flex-1 gap-1.5">
                <Trash2 className="size-3.5" />
                Excluir
              </Button>
            </CardFooter>
          </Card>
        ))}
      </div>
    </div>
  )
}
