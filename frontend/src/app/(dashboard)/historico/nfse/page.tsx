"use client"

import { useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Download,
  FileDown,
  Filter,
  ChevronLeft,
  ChevronRight,
  Eye,
  AlertTriangle,
} from "lucide-react"

type NfseStatus = "Emitida" | "Cancelada" | "Substituida" | "Pendente"

interface NfseRow {
  id: number
  prestador: string
  cnpjPrestador: string
  tomador: string
  municipio: string
  uf: string
  numero: string
  valor: number
  competencia: string
  status: NfseStatus
}

const statusConfig: Record<NfseStatus, { label: string; variant: "default" | "secondary" | "outline" | "destructive" }> = {
  Emitida: { label: "Emitida", variant: "default" },
  Cancelada: { label: "Cancelada", variant: "destructive" },
  Substituida: { label: "Substituida", variant: "secondary" },
  Pendente: { label: "Pendente", variant: "outline" },
}

const mockData: NfseRow[] = [
  { id: 1, prestador: "TechServ Consultoria Ltda", cnpjPrestador: "12.345.678/0001-90", tomador: "Banco Nacional S.A.", municipio: "Sao Paulo", uf: "SP", numero: "2026000142", valor: 18500.00, competencia: "03/2026", status: "Emitida" },
  { id: 2, prestador: "Contabilize Servicos ME", cnpjPrestador: "23.456.789/0001-01", tomador: "Loja Virtual Express Ltda", municipio: "Belo Horizonte", uf: "MG", numero: "2026000087", valor: 3200.00, competencia: "03/2026", status: "Emitida" },
  { id: 3, prestador: "EngeSoft Sistemas S.A.", cnpjPrestador: "34.567.890/0001-12", tomador: "Prefeitura Municipal de Curitiba", municipio: "Curitiba", uf: "PR", numero: "2026000203", valor: 45000.00, competencia: "03/2026", status: "Emitida" },
  { id: 4, prestador: "CleanPro Limpeza Eireli", cnpjPrestador: "45.678.901/0001-23", tomador: "Shopping Center Iguatemi", municipio: "Porto Alegre", uf: "RS", numero: "2026000056", valor: 8900.00, competencia: "03/2026", status: "Cancelada" },
  { id: 5, prestador: "SeguraNet Cybersecurity", cnpjPrestador: "56.789.012/0001-34", tomador: "Hospital Santa Casa", municipio: "Rio de Janeiro", uf: "RJ", numero: "2026000321", valor: 27600.00, competencia: "03/2026", status: "Emitida" },
  { id: 6, prestador: "MarketPro Publicidade Ltda", cnpjPrestador: "67.890.123/0001-45", tomador: "Industrias Reunidas Paulista", municipio: "Campinas", uf: "SP", numero: "2026000178", valor: 12750.00, competencia: "02/2026", status: "Emitida" },
  { id: 7, prestador: "JurisTech Advocacia Digital", cnpjPrestador: "78.901.234/0001-56", tomador: "Construtora Andrade Gutierrez", municipio: "Salvador", uf: "BA", numero: "2026000094", valor: 6400.00, competencia: "02/2026", status: "Substituida" },
  { id: 8, prestador: "DataCenter Cloud Services", cnpjPrestador: "89.012.345/0001-67", tomador: "Rede Globo Comunicacoes", municipio: "Brasilia", uf: "DF", numero: "2026000265", valor: 52300.00, competencia: "02/2026", status: "Emitida" },
  { id: 9, prestador: "VetCare Servicos Animais ME", cnpjPrestador: "90.123.456/0001-78", tomador: "Agropecuaria Mato Verde", municipio: "Goiania", uf: "GO", numero: "2026000031", valor: 1850.00, competencia: "02/2026", status: "Pendente" },
  { id: 10, prestador: "ArqPlan Projetos Arquitetura", cnpjPrestador: "01.234.567/0001-89", tomador: "Incorporadora Vision Ltda", municipio: "Florianopolis", uf: "SC", numero: "2026000412", valor: 34200.00, competencia: "03/2026", status: "Emitida" },
  { id: 11, prestador: "EduTech Plataformas Ensino", cnpjPrestador: "13.579.246/0001-80", tomador: "Universidade Federal de Minas", municipio: "Recife", uf: "PE", numero: "2026000149", valor: 9800.00, competencia: "03/2026", status: "Emitida" },
  { id: 12, prestador: "LogiTransp Fretes Rapidos", cnpjPrestador: "24.680.135/0001-91", tomador: "Magazine Luiza S.A.", municipio: "Manaus", uf: "AM", numero: "2026000073", valor: 15600.00, competencia: "03/2026", status: "Cancelada" },
]

const CNPJS = [
  "Todos",
  "12.345.678/0001-90",
  "23.456.789/0001-01",
  "34.567.890/0001-12",
]

export default function HistoricoNfsePage() {
  const [currentPage, setCurrentPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState("Todos")
  const [searchNumero, setSearchNumero] = useState("")
  const [dateFrom, setDateFrom] = useState("2026-03-01")
  const [dateTo, setDateTo] = useState("2026-03-16")
  const itemsPerPage = 10

  const filteredData = mockData.filter((row) => {
    if (statusFilter !== "Todos" && row.status !== statusFilter) return false
    if (searchNumero && !row.numero.toLowerCase().includes(searchNumero.toLowerCase())) return false
    return true
  })

  const totalPages = Math.ceil(filteredData.length / itemsPerPage)
  const paginatedData = filteredData.slice(
    (currentPage - 1) * itemsPerPage,
    currentPage * itemsPerPage
  )

  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">NFS-e Recebidas</h1>
            <Badge variant="outline" className="bg-amber-50 text-amber-700 border-amber-200 text-[10px]">
              ADN
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            Notas fiscais de servico recebidas via Ambiente Nacional
          </p>
        </div>
        <Button variant="outline">
          <FileDown className="size-4" />
          Exportar
        </Button>
      </div>

      {/* Alert banners */}
      <div className="space-y-2">
        <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
          <p>
            A cobertura de NFS-e depende da adesão do município ao padrão nacional (Reforma Tributária LC 214/2025).
            Consulte <strong>gov.br/nfse</strong> para verificar a adesão do município.
          </p>
        </div>
        <div className="flex items-start gap-3 rounded-lg border border-blue-200 bg-blue-50 p-4">
          <div className="shrink-0 mt-0.5 size-5 rounded-full bg-blue-100 flex items-center justify-center">
            <span className="text-blue-600 text-xs font-bold">i</span>
          </div>
          <div>
            <p className="text-sm font-medium text-blue-900">Captura ativa via Ambiente Nacional — Integração SAP DRC em desenvolvimento</p>
            <p className="text-xs text-blue-700 mt-1">
              O DFeAxis captura NFS-e recebidas através do Ambiente Nacional da RFB. A entrega automática para o SAP via DRC ainda não é suportada pela SAP para NFS-e. Os documentos ficam disponíveis para consulta e download neste painel.
            </p>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-end gap-3 rounded-lg border p-4">
        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-muted-foreground">CNPJ Prestador</span>
          <Select defaultValue="Todos">
            <SelectTrigger className="w-[200px]">
              <SelectValue placeholder="Selecione o CNPJ" />
            </SelectTrigger>
            <SelectContent>
              {CNPJS.map((cnpj) => (
                <SelectItem key={cnpj} value={cnpj}>
                  {cnpj}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-muted-foreground">De</span>
          <Input type="date" className="w-[150px]" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
        </div>

        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-muted-foreground">Ate</span>
          <Input type="date" className="w-[150px]" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
        </div>

        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-muted-foreground">Status</span>
          <Select value={statusFilter} onValueChange={(v) => { if (v) { setStatusFilter(v); setCurrentPage(1) } }}>
            <SelectTrigger className="w-[150px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="Todos">Todos</SelectItem>
              <SelectItem value="Emitida">Emitida</SelectItem>
              <SelectItem value="Cancelada">Cancelada</SelectItem>
              <SelectItem value="Substituida">Substituida</SelectItem>
              <SelectItem value="Pendente">Pendente</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-muted-foreground">Numero NFS-e</span>
          <Input
            placeholder="Buscar por numero..."
            className="w-[200px]"
            value={searchNumero}
            onChange={(e) => { setSearchNumero(e.target.value); setCurrentPage(1) }}
          />
        </div>

        <Button variant="default" className="gap-1.5">
          <Filter className="size-3.5" />
          Filtrar
        </Button>
      </div>

      {/* Table */}
      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Prestador</TableHead>
              <TableHead>Tomador</TableHead>
              <TableHead>Municipio</TableHead>
              <TableHead>N NFS-e</TableHead>
              <TableHead className="text-right">Valor (R$)</TableHead>
              <TableHead>Competencia</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Acoes</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {paginatedData.map((row) => (
              <TableRow key={row.id}>
                <TableCell className="max-w-[180px] truncate font-medium">
                  {row.prestador}
                </TableCell>
                <TableCell className="max-w-[180px] truncate">
                  {row.tomador}
                </TableCell>
                <TableCell>
                  {row.municipio}/{row.uf}
                </TableCell>
                <TableCell className="font-mono text-xs">{row.numero}</TableCell>
                <TableCell className="text-right font-mono">
                  {row.valor.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                </TableCell>
                <TableCell>{row.competencia}</TableCell>
                <TableCell>
                  <Badge variant={statusConfig[row.status].variant}>
                    {statusConfig[row.status].label}
                  </Badge>
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-1">
                    <Button variant="ghost" size="icon-xs" title="Visualizar">
                      <Eye className="size-3.5" />
                    </Button>
                    <Button variant="ghost" size="icon-xs" title="Download">
                      <Download className="size-3.5" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
            {paginatedData.length === 0 && (
              <TableRow>
                <TableCell colSpan={8} className="h-24 text-center text-muted-foreground">
                  Nenhuma NFS-e encontrada com os filtros aplicados.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Mostrando {((currentPage - 1) * itemsPerPage) + 1} a{" "}
          {Math.min(currentPage * itemsPerPage, filteredData.length)} de{" "}
          {filteredData.length} registros
        </p>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="icon-sm"
            disabled={currentPage === 1}
            onClick={() => setCurrentPage((p) => p - 1)}
          >
            <ChevronLeft className="size-4" />
          </Button>
          {Array.from({ length: totalPages }, (_, i) => i + 1).map((page) => (
            <Button
              key={page}
              variant={page === currentPage ? "default" : "outline"}
              size="sm"
              onClick={() => setCurrentPage(page)}
            >
              {page}
            </Button>
          ))}
          <Button
            variant="outline"
            size="icon-sm"
            disabled={currentPage === totalPages}
            onClick={() => setCurrentPage((p) => p + 1)}
          >
            <ChevronRight className="size-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}
