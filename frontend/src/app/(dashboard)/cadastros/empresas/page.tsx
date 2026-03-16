"use client"

import { useState } from "react"
import { Building, Plus, Pencil, Trash2, MapPin } from "lucide-react"
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet"

interface Empresa {
  id: number
  razaoSocial: string
  nomeFantasia: string
  cnpj: string
  inscricaoEstadual: string
  uf: string
  cidade: string
  certificadoAtivo: boolean
  status: "Ativa" | "Inativa"
}

const mockEmpresas: Empresa[] = [
  {
    id: 1,
    razaoSocial: "Distribuidora Alimentos Ltda",
    nomeFantasia: "DistAlimentos",
    cnpj: "12.345.678/0001-90",
    inscricaoEstadual: "123.456.789.001",
    uf: "SP",
    cidade: "São Paulo",
    certificadoAtivo: true,
    status: "Ativa",
  },
  {
    id: 2,
    razaoSocial: "Tech Solutions S.A.",
    nomeFantasia: "TechSol",
    cnpj: "98.765.432/0001-10",
    inscricaoEstadual: "987.654.321.002",
    uf: "SP",
    cidade: "Campinas",
    certificadoAtivo: true,
    status: "Ativa",
  },
  {
    id: 3,
    razaoSocial: "Metalurgica Brasil ME",
    nomeFantasia: "MetalBR",
    cnpj: "11.222.333/0001-44",
    inscricaoEstadual: "112.223.334.003",
    uf: "MG",
    cidade: "Belo Horizonte",
    certificadoAtivo: true,
    status: "Ativa",
  },
  {
    id: 4,
    razaoSocial: "Farmacia Popular Eireli",
    nomeFantasia: "FarmaPop",
    cnpj: "44.555.666/0001-77",
    inscricaoEstadual: "445.556.667.004",
    uf: "RJ",
    cidade: "Rio de Janeiro",
    certificadoAtivo: false,
    status: "Inativa",
  },
  {
    id: 5,
    razaoSocial: "Construtora Horizonte Ltda",
    nomeFantasia: "Horizonte",
    cnpj: "55.666.777/0003-68",
    inscricaoEstadual: "556.667.778.005",
    uf: "PR",
    cidade: "Curitiba",
    certificadoAtivo: true,
    status: "Ativa",
  },
]

export default function EmpresasPage() {
  const [sheetOpen, setSheetOpen] = useState(false)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Empresas / CNPJs</h1>
          <p className="text-sm text-muted-foreground">
            Gerencie as empresas vinculadas à sua conta.
          </p>
        </div>
        <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
          <SheetTrigger
            render={
              <Button className="gap-2">
                <Plus className="size-4" />
                Nova Empresa
              </Button>
            }
          />
          <SheetContent side="right">
            <SheetHeader>
              <SheetTitle>Cadastrar Empresa</SheetTitle>
              <SheetDescription>
                Adicione uma empresa para capturar documentos recebidos.
              </SheetDescription>
            </SheetHeader>
            <div className="flex flex-col gap-4 px-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="razao">Razão Social</Label>
                <Input id="razao" placeholder="Razão Social da empresa" />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="fantasia">Nome Fantasia</Label>
                <Input id="fantasia" placeholder="Nome Fantasia" />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="cnpj">CNPJ</Label>
                <Input id="cnpj" placeholder="00.000.000/0000-00" />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="ie">Inscrição Estadual</Label>
                <Input id="ie" placeholder="000.000.000.000" />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="flex flex-col gap-2">
                  <Label htmlFor="uf">UF</Label>
                  <Input id="uf" placeholder="SP" maxLength={2} />
                </div>
                <div className="flex flex-col gap-2">
                  <Label htmlFor="cidade">Cidade</Label>
                  <Input id="cidade" placeholder="São Paulo" />
                </div>
              </div>
            </div>
            <SheetFooter>
              <Button className="w-full gap-2" onClick={() => setSheetOpen(false)}>
                <Plus className="size-4" />
                Cadastrar
              </Button>
            </SheetFooter>
          </SheetContent>
        </Sheet>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {mockEmpresas.map((emp) => (
          <Card key={emp.id}>
            <CardHeader className="pb-3">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-2">
                  <Building className="size-5 text-muted-foreground" />
                  <div>
                    <CardTitle className="text-base leading-snug">{emp.nomeFantasia}</CardTitle>
                    <p className="text-xs text-muted-foreground mt-0.5">{emp.razaoSocial}</p>
                  </div>
                </div>
                <Badge variant={emp.status === "Ativa" ? "default" : "destructive"}>
                  {emp.status}
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">CNPJ</span>
                <span className="font-mono">{emp.cnpj}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">IE</span>
                <span className="font-mono">{emp.inscricaoEstadual}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-muted-foreground">Localização</span>
                <span className="flex items-center gap-1">
                  <MapPin className="size-3" />
                  {emp.cidade}/{emp.uf}
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-muted-foreground">Certificado</span>
                <Badge variant={emp.certificadoAtivo ? "secondary" : "destructive"} className="text-xs">
                  {emp.certificadoAtivo ? "Vinculado" : "Pendente"}
                </Badge>
              </div>
            </CardContent>
            <CardFooter className="gap-2">
              <Button variant="outline" size="sm" className="flex-1 gap-1.5">
                <Pencil className="size-3.5" />
                Editar
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
