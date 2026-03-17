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
  FileText,
  Filter,
  FileDown,
  ChevronLeft,
  ChevronRight,
  Eye,
  Send,
} from "lucide-react"

type NfeStatus = "Disponivel" | "Entregue" | "Pendente" | "Cancelada"
type Manifestacao = "Ciencia" | "Confirmada" | "Pendente" | "Desconhecida"

interface NfeRow {
  id: number
  emitente: string
  cnpj: string
  emissao: string
  nota: string
  chave: string
  valor: number
  status: NfeStatus
  manifestacao: Manifestacao
}

const statusConfig: Record<NfeStatus, { label: string; variant: "default" | "secondary" | "outline" | "destructive" }> = {
  Disponivel: { label: "Disponivel", variant: "default" },
  Entregue: { label: "Entregue", variant: "secondary" },
  Pendente: { label: "Pendente", variant: "outline" },
  Cancelada: { label: "Cancelada", variant: "destructive" },
}

const manifestacaoConfig: Record<Manifestacao, { label: string; variant: "default" | "secondary" | "outline" | "destructive" }> = {
  Ciencia: { label: "Ciencia", variant: "secondary" },
  Confirmada: { label: "Confirmada", variant: "default" },
  Pendente: { label: "Pendente", variant: "outline" },
  Desconhecida: { label: "Desconhecida", variant: "destructive" },
}

const mockData: NfeRow[] = [
  { id: 1, emitente: "Distribuidora Alimentos Ltda", cnpj: "12.345.678/0001-90", emissao: "15/03/2026", nota: "001.234.567", chave: "3526 0312 3456 7800 0190 5500 1001 2345 6712 3456 7890", valor: 15420.50, status: "Disponivel", manifestacao: "Pendente" },
  { id: 2, emitente: "Tech Solutions S.A.", cnpj: "98.765.432/0001-10", emissao: "14/03/2026", nota: "002.345.678", chave: "3526 0398 7654 3200 0110 5500 1002 3456 7823 4567 8901", valor: 8750.00, status: "Entregue", manifestacao: "Confirmada" },
  { id: 3, emitente: "Metalurgica Brasil ME", cnpj: "11.222.333/0001-44", emissao: "14/03/2026", nota: "003.456.789", chave: "3526 0311 2223 3300 0144 5500 1003 4567 8934 5678 9012", valor: 32100.75, status: "Disponivel", manifestacao: "Ciencia" },
  { id: 4, emitente: "Farmacia Popular Eireli", cnpj: "44.555.666/0001-77", emissao: "13/03/2026", nota: "004.567.890", chave: "3526 0344 5556 6600 0177 5500 1004 5678 9045 6789 0123", valor: 2340.20, status: "Cancelada", manifestacao: "Desconhecida" },
  { id: 5, emitente: "Construtora Horizonte Ltda", cnpj: "55.666.777/0001-88", emissao: "13/03/2026", nota: "005.678.901", chave: "3526 0355 6667 7700 0188 5500 1005 6789 0156 7890 1234", valor: 98500.00, status: "Entregue", manifestacao: "Confirmada" },
  { id: 6, emitente: "Auto Pecas Centro Sul", cnpj: "66.777.888/0001-99", emissao: "12/03/2026", nota: "006.789.012", chave: "3526 0366 7778 8800 0199 5500 1006 7890 1267 8901 2345", valor: 4560.30, status: "Disponivel", manifestacao: "Pendente" },
  { id: 7, emitente: "Grafica Express ME", cnpj: "77.888.999/0001-00", emissao: "12/03/2026", nota: "007.890.123", chave: "3526 0377 8889 9900 0100 5500 1007 8901 2378 9012 3456", valor: 1280.00, status: "Pendente", manifestacao: "Pendente" },
  { id: 8, emitente: "Industria Quimica Norte", cnpj: "88.999.000/0001-11", emissao: "11/03/2026", nota: "008.901.234", chave: "3526 0388 9990 0000 0111 5500 1008 9012 3489 0123 4567", valor: 67890.45, status: "Entregue", manifestacao: "Confirmada" },
  { id: 9, emitente: "Supermercado Bom Preco", cnpj: "99.000.111/0001-22", emissao: "11/03/2026", nota: "009.012.345", chave: "3526 0399 0001 1100 0122 5500 1009 0123 4590 1234 5678", valor: 540.80, status: "Disponivel", manifestacao: "Ciencia" },
  { id: 10, emitente: "Transportadora Veloz S.A.", cnpj: "10.111.222/0001-33", emissao: "10/03/2026", nota: "010.123.456", chave: "3526 0310 1112 2200 0133 5500 1010 1234 5601 2345 6789", valor: 12300.00, status: "Pendente", manifestacao: "Pendente" },
  { id: 11, emitente: "Padaria Sao Jorge Ltda", cnpj: "21.333.444/0001-55", emissao: "10/03/2026", nota: "011.234.567", chave: "3526 0321 3334 4400 0155 5500 1011 2345 6712 3456 7890", valor: 890.25, status: "Entregue", manifestacao: "Confirmada" },
  { id: 12, emitente: "Eletro Comercial Eireli", cnpj: "32.444.555/0001-66", emissao: "09/03/2026", nota: "012.345.678", chave: "3526 0332 4445 5500 0166 5500 1012 3456 7823 4567 8901", valor: 23450.00, status: "Disponivel", manifestacao: "Pendente" },
  { id: 13, emitente: "Moveis Planejados Sul", cnpj: "43.555.666/0001-77", emissao: "09/03/2026", nota: "013.456.789", chave: "3526 0343 5556 6600 0177 5500 1013 4567 8934 5678 9012", valor: 18900.60, status: "Cancelada", manifestacao: "Desconhecida" },
  { id: 14, emitente: "Laboratorio Vida Saude", cnpj: "54.666.777/0001-88", emissao: "08/03/2026", nota: "014.567.890", chave: "3526 0354 6667 7700 0188 5500 1014 5678 9045 6789 0123", valor: 7650.00, status: "Entregue", manifestacao: "Confirmada" },
  { id: 15, emitente: "Textil Nordeste ME", cnpj: "65.777.888/0001-99", emissao: "08/03/2026", nota: "015.678.901", chave: "3526 0365 7778 8800 0199 5500 1015 6789 0156 7890 1234", valor: 45230.80, status: "Disponivel", manifestacao: "Ciencia" },
  { id: 16, emitente: "Posto Combustivel Rota", cnpj: "76.888.999/0001-00", emissao: "07/03/2026", nota: "016.789.012", chave: "3526 0376 8889 9900 0100 5500 1016 7890 1267 8901 2345", valor: 3210.40, status: "Pendente", manifestacao: "Pendente" },
  { id: 17, emitente: "Agropecuaria Campo Verde", cnpj: "87.999.000/0001-11", emissao: "07/03/2026", nota: "017.890.123", chave: "3526 0387 9990 0000 0111 5500 1017 8901 2378 9012 3456", valor: 156780.00, status: "Entregue", manifestacao: "Confirmada" },
  { id: 18, emitente: "Clinica Odonto Plus", cnpj: "98.000.111/0001-22", emissao: "06/03/2026", nota: "018.901.234", chave: "3526 0398 0001 1100 0122 5500 1018 9012 3489 0123 4567", valor: 4890.00, status: "Disponivel", manifestacao: "Pendente" },
]

const CNPJS = [
  "Todos",
  "12.345.678/0001-90",
  "55.666.777/0001-88",
  "98.765.432/0001-10",
]

export default function HistoricoNfePage() {
  const [currentPage, setCurrentPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState("Todos")

  const [searchChave, setSearchChave] = useState("")
  const [dateFrom, setDateFrom] = useState("2026-03-01")
  const [dateTo, setDateTo] = useState("2026-03-16")
  const itemsPerPage = 10

  const filteredData = mockData.filter((row) => {
    if (statusFilter !== "Todos" && row.status !== statusFilter) return false
    if (searchChave && !row.chave.toLowerCase().includes(searchChave.toLowerCase())) return false
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
          <h1 className="text-2xl font-semibold tracking-tight">NF-e Recebidas</h1>
          <p className="text-sm text-muted-foreground">
            Notas fiscais recebidas de fornecedores via captura automatica
          </p>
        </div>
        <Button variant="outline">
          <FileDown className="size-4" />
          Exportar
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-end gap-3 rounded-lg border p-4">
        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-muted-foreground">CNPJ</span>
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
              <SelectItem value="Disponivel">Disponivel</SelectItem>
              <SelectItem value="Entregue">Entregue</SelectItem>
              <SelectItem value="Pendente">Pendente</SelectItem>
              <SelectItem value="Cancelada">Cancelada</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-muted-foreground">Chave de acesso</span>
          <Input
            placeholder="Buscar por chave..."
            className="w-[220px]"
            value={searchChave}
            onChange={(e) => { setSearchChave(e.target.value); setCurrentPage(1) }}
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
              <TableHead>Emitente (Fornecedor)</TableHead>
              <TableHead>CNPJ Emitente</TableHead>
              <TableHead>Emissao</TableHead>
              <TableHead>Nota</TableHead>
              <TableHead>Chave de Acesso</TableHead>
              <TableHead className="text-right">Valor (R$)</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Manifestacao</TableHead>
              <TableHead>Acoes</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {paginatedData.map((row) => (
              <TableRow key={row.id}>
                <TableCell className="max-w-[200px] truncate font-medium">
                  {row.emitente}
                </TableCell>
                <TableCell className="font-mono text-xs">{row.cnpj}</TableCell>
                <TableCell>{row.emissao}</TableCell>
                <TableCell className="font-mono text-xs">{row.nota}</TableCell>
                <TableCell className="max-w-[180px] truncate font-mono text-xs">
                  {row.chave}
                </TableCell>
                <TableCell className="text-right font-mono">
                  {row.valor.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                </TableCell>
                <TableCell>
                  <Badge variant={statusConfig[row.status].variant}>
                    {statusConfig[row.status].label}
                  </Badge>
                </TableCell>
                <TableCell>
                  <Badge variant={manifestacaoConfig[row.manifestacao].variant}>
                    {manifestacaoConfig[row.manifestacao].label}
                  </Badge>
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-1">
                    <Button variant="ghost" size="icon-xs" title="Visualizar XML">
                      <Eye className="size-3.5" />
                    </Button>
                    <Button variant="ghost" size="icon-xs" title="Download">
                      <Download className="size-3.5" />
                    </Button>
                    <Button variant="ghost" size="icon-xs" title="Manifestar">
                      <Send className="size-3.5" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
            {paginatedData.length === 0 && (
              <TableRow>
                <TableCell colSpan={9} className="h-24 text-center text-muted-foreground">
                  Nenhuma NF-e encontrada com os filtros aplicados.
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
