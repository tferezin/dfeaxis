"use client"

import { useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useSettings } from "@/hooks/use-settings"
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
  Inbox,
} from "lucide-react"

type MdfeStatus = "Autorizado" | "Encerrado" | "Cancelado" | "Pendente"

interface MdfeRow {
  id: number
  emitente: string
  mdfeNumero: string
  chave: string
  ufCarregamento: string
  ufDescarregamento: string
  status: MdfeStatus
  emissao: string
}

const statusConfig: Record<MdfeStatus, { label: string; variant: "default" | "secondary" | "outline" | "destructive" }> = {
  Autorizado: { label: "Autorizado", variant: "default" },
  Encerrado: { label: "Encerrado", variant: "secondary" },
  Cancelado: { label: "Cancelado", variant: "destructive" },
  Pendente: { label: "Pendente", variant: "outline" },
}

const UFS = ["AC","AL","AM","AP","BA","CE","DF","ES","GO","MA","MG","MS","MT","PA","PB","PE","PI","PR","RJ","RN","RO","RR","RS","SC","SE","SP","TO"]

const mockData: MdfeRow[] = [
  { id: 1, emitente: "Transportadora Veloz S.A.", mdfeNumero: "000.000.001", chave: "3526 0312 3456 7800 0190 5800 1000 0000 0112 3456 7890", ufCarregamento: "SP", ufDescarregamento: "MG", status: "Autorizado", emissao: "15/03/2026" },
  { id: 2, emitente: "Logistica Nacional Ltda", mdfeNumero: "000.000.002", chave: "3526 0398 7654 3200 0110 5800 1000 0000 0223 4567 8901", ufCarregamento: "RJ", ufDescarregamento: "BA", status: "Encerrado", emissao: "14/03/2026" },
  { id: 3, emitente: "Expresso Rodoviario ME", mdfeNumero: "000.000.003", chave: "3526 0311 2223 3300 0144 5800 1000 0000 0334 5678 9012", ufCarregamento: "PR", ufDescarregamento: "SC", status: "Autorizado", emissao: "14/03/2026" },
  { id: 4, emitente: "Frete Seguro Transportes", mdfeNumero: "000.000.004", chave: "3526 0344 5556 6600 0177 5800 1000 0000 0445 6789 0123", ufCarregamento: "GO", ufDescarregamento: "MT", status: "Cancelado", emissao: "13/03/2026" },
  { id: 5, emitente: "Transportadora Veloz S.A.", mdfeNumero: "000.000.005", chave: "3526 0355 6667 7700 0188 5800 1000 0000 0556 7890 1234", ufCarregamento: "SP", ufDescarregamento: "RS", status: "Encerrado", emissao: "13/03/2026" },
  { id: 6, emitente: "Rapido Translog Eireli", mdfeNumero: "000.000.006", chave: "3526 0366 7778 8800 0199 5800 1000 0000 0667 8901 2345", ufCarregamento: "MG", ufDescarregamento: "ES", status: "Autorizado", emissao: "12/03/2026" },
  { id: 7, emitente: "Logistica Nacional Ltda", mdfeNumero: "000.000.007", chave: "3526 0377 8889 9900 0100 5800 1000 0000 0778 9012 3456", ufCarregamento: "BA", ufDescarregamento: "PE", status: "Pendente", emissao: "12/03/2026" },
  { id: 8, emitente: "Expresso Rodoviario ME", mdfeNumero: "000.000.008", chave: "3526 0388 9990 0000 0111 5800 1000 0000 0889 0123 4567", ufCarregamento: "SC", ufDescarregamento: "PR", status: "Autorizado", emissao: "11/03/2026" },
  { id: 9, emitente: "Frete Seguro Transportes", mdfeNumero: "000.000.009", chave: "3526 0399 0001 1100 0122 5800 1000 0000 0990 1234 5678", ufCarregamento: "RS", ufDescarregamento: "SP", status: "Encerrado", emissao: "11/03/2026" },
  { id: 10, emitente: "Transportadora Veloz S.A.", mdfeNumero: "000.000.010", chave: "3526 0310 1112 2200 0133 5800 1000 0000 1001 2345 6789", ufCarregamento: "SP", ufDescarregamento: "GO", status: "Autorizado", emissao: "10/03/2026" },
  { id: 11, emitente: "Rapido Translog Eireli", mdfeNumero: "000.000.011", chave: "3526 0321 3334 4400 0155 5800 1000 0000 1112 3456 7890", ufCarregamento: "PE", ufDescarregamento: "CE", status: "Pendente", emissao: "10/03/2026" },
  { id: 12, emitente: "Logistica Nacional Ltda", mdfeNumero: "000.000.012", chave: "3526 0332 4445 5500 0166 5800 1000 0000 1223 4567 8901", ufCarregamento: "MT", ufDescarregamento: "MS", status: "Cancelado", emissao: "09/03/2026" },
  { id: 13, emitente: "Expresso Rodoviario ME", mdfeNumero: "000.000.013", chave: "3526 0343 5556 6600 0177 5800 1000 0000 1334 5678 9012", ufCarregamento: "MG", ufDescarregamento: "RJ", status: "Autorizado", emissao: "09/03/2026" },
  { id: 14, emitente: "Frete Seguro Transportes", mdfeNumero: "000.000.014", chave: "3526 0354 6667 7700 0188 5800 1000 0000 1445 6789 0123", ufCarregamento: "SP", ufDescarregamento: "BA", status: "Encerrado", emissao: "08/03/2026" },
  { id: 15, emitente: "Transportadora Veloz S.A.", mdfeNumero: "000.000.015", chave: "3526 0365 7778 8800 0199 5800 1000 0000 1556 7890 1234", ufCarregamento: "GO", ufDescarregamento: "SP", status: "Autorizado", emissao: "08/03/2026" },
]

export default function HistoricoMdfePage() {
  const { settings } = useSettings()
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

  if (!settings.showMockData) {
    return (
      <div className="flex flex-col gap-6 p-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">MDF-e Recebidos</h1>
          <p className="text-sm text-muted-foreground">
            Manifestos eletronicos recebidos via captura automatica
          </p>
        </div>
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <Inbox className="size-12 text-muted-foreground/30 mb-4" />
          <p className="text-sm text-muted-foreground">Nenhum MDF-e capturado. Configure um certificado e execute uma captura para ver documentos reais.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">MDF-e Recebidos</h1>
          <p className="text-sm text-muted-foreground">
            Manifestos eletronicos recebidos via captura automatica
          </p>
        </div>
        <Button variant="outline">
          <FileDown className="size-4" />
          Exportar
        </Button>
      </div>

      {/* SAP DRC availability notice */}
      <div className="flex items-start gap-3 rounded-lg border border-blue-200 bg-blue-50 p-4">
        <div className="shrink-0 mt-0.5 size-5 rounded-full bg-blue-100 flex items-center justify-center">
          <span className="text-blue-600 text-xs font-bold">i</span>
        </div>
        <div>
          <p className="text-sm font-medium text-blue-900">Captura ativa — Integração SAP DRC em desenvolvimento</p>
          <p className="text-xs text-blue-700 mt-1">
            O DFeAxis captura MDF-e recebidos da SEFAZ normalmente. A entrega automática para o SAP via DRC ainda não é suportada pela SAP para este tipo de documento. Os MDF-e ficam disponíveis para consulta e download manual neste painel.
          </p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-end gap-3 rounded-lg border p-4">
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
              <SelectItem value="Autorizado">Autorizado</SelectItem>
              <SelectItem value="Encerrado">Encerrado</SelectItem>
              <SelectItem value="Cancelado">Cancelado</SelectItem>
              <SelectItem value="Pendente">Pendente</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-muted-foreground">UF Carreg.</span>
          <Select defaultValue="Todos">
            <SelectTrigger className="w-[110px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="Todos">Todos</SelectItem>
              {UFS.map((uf) => (
                <SelectItem key={uf} value={uf}>{uf}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-muted-foreground">UF Descarr.</span>
          <Select defaultValue="Todos">
            <SelectTrigger className="w-[110px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="Todos">Todos</SelectItem>
              {UFS.map((uf) => (
                <SelectItem key={uf} value={uf}>{uf}</SelectItem>
              ))}
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
              <TableHead>Emitente</TableHead>
              <TableHead>MDF-e N.</TableHead>
              <TableHead>Chave de Acesso</TableHead>
              <TableHead>UF Carregamento</TableHead>
              <TableHead>UF Descarregamento</TableHead>
              <TableHead>Emissao</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Acoes</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {paginatedData.map((row) => (
              <TableRow key={row.id}>
                <TableCell className="max-w-[200px] truncate font-medium">
                  {row.emitente}
                </TableCell>
                <TableCell className="font-mono text-xs">{row.mdfeNumero}</TableCell>
                <TableCell className="max-w-[200px] truncate font-mono text-xs">
                  {row.chave}
                </TableCell>
                <TableCell className="text-center font-medium">{row.ufCarregamento}</TableCell>
                <TableCell className="text-center font-medium">{row.ufDescarregamento}</TableCell>
                <TableCell>{row.emissao}</TableCell>
                <TableCell>
                  <Badge variant={statusConfig[row.status].variant}>
                    {statusConfig[row.status].label}
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
                  </div>
                </TableCell>
              </TableRow>
            ))}
            {paginatedData.length === 0 && (
              <TableRow>
                <TableCell colSpan={8} className="h-24 text-center text-muted-foreground">
                  Nenhum MDF-e encontrado com os filtros aplicados.
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
