"use client"

import { useState, useEffect, useCallback } from "react"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useSettings } from "@/hooks/use-settings"
import { getSupabase } from "@/lib/supabase"
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
  Loader2,
} from "lucide-react"

type CteosStatus = "Autorizado" | "Cancelado" | "Pendente" | "Denegado"

interface CteosRow {
  id: number
  emitente: string
  tomador: string
  cteosNumero: string
  chave: string
  valorServico: number
  status: CteosStatus
  emissao: string
}

const statusConfig: Record<CteosStatus, { label: string; className: string }> = {
  Autorizado: {
    label: "Disponível",
    className: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
  },
  Cancelado: {
    label: "Cancelado",
    className: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
  },
  Pendente: {
    label: "Pendente",
    className: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400",
  },
  Denegado: {
    label: "Denegado",
    className: "bg-gray-100 text-gray-600 dark:bg-gray-800/50 dark:text-gray-400",
  },
}

// CT-e OS (modelo 67) cobre prestacao de servico de transporte de
// passageiros e valores — onibus interestadual, carro-forte, van de
// turismo. Nao tem "remetente/destinatario" como CT-e de carga: tem
// emitente (transportadora) e tomador (quem contrata o servico).
const mockData: CteosRow[] = [
  { id: 1, emitente: "Expresso Brasileiro Onibus Ltda", tomador: "Industria Metalurgica Norte S.A.", cteosNumero: "000.001.234", chave: "3526 0312 3456 7800 0190 6700 1001 2345 6712 3456 7890", valorServico: 1250.75, status: "Autorizado", emissao: "15/03/2026" },
  { id: 2, emitente: "Viacao Interestadual Sul", tomador: "Construtora Horizonte Ltda", cteosNumero: "000.002.345", chave: "3526 0398 7654 3200 0110 6700 1002 3456 7823 4567 8901", valorServico: 3800.00, status: "Autorizado", emissao: "14/03/2026" },
  { id: 3, emitente: "Van Turismo Executivo ME", tomador: "Tech Solutions Consultoria S.A.", cteosNumero: "000.003.456", chave: "3526 0311 2223 3300 0144 6700 1003 4567 8934 5678 9012", valorServico: 680.50, status: "Pendente", emissao: "14/03/2026" },
  { id: 4, emitente: "Proteforte Transporte de Valores", tomador: "Banco Regional Investimentos", cteosNumero: "000.004.567", chave: "3526 0344 5556 6600 0177 6700 1004 5678 9045 6789 0123", valorServico: 4200.00, status: "Cancelado", emissao: "13/03/2026" },
  { id: 5, emitente: "Rodoviaria Litoral Express", tomador: "Hotel Beira Mar Resort", cteosNumero: "000.005.678", chave: "3526 0355 6667 7700 0188 6700 1005 6789 0156 7890 1234", valorServico: 2150.00, status: "Autorizado", emissao: "13/03/2026" },
  { id: 6, emitente: "Via Segura Carros-Fortes", tomador: "Rede Varejo Nacional Ltda", cteosNumero: "000.006.789", chave: "3526 0366 7778 8800 0199 6700 1006 7890 1267 8901 2345", valorServico: 890.30, status: "Autorizado", emissao: "12/03/2026" },
  { id: 7, emitente: "Translog Passageiros Eireli", tomador: "Universidade Federal do Estado", cteosNumero: "000.007.890", chave: "3526 0377 8889 9900 0100 6700 1007 8901 2378 9012 3456", valorServico: 550.00, status: "Denegado", emissao: "12/03/2026" },
  { id: 8, emitente: "Expresso Brasileiro Onibus Ltda", tomador: "Industria Textil Sao Paulo", cteosNumero: "000.008.901", chave: "3526 0388 9990 0000 0111 6700 1008 9012 3489 0123 4567", valorServico: 1780.45, status: "Autorizado", emissao: "11/03/2026" },
  { id: 9, emitente: "Fretamento Turismo Nacional", tomador: "Prefeitura Municipal Campo Verde", cteosNumero: "000.009.012", chave: "3526 0399 0001 1100 0122 6700 1009 0123 4590 1234 5678", valorServico: 3670.80, status: "Pendente", emissao: "11/03/2026" },
  { id: 10, emitente: "Proteforte Transporte de Valores", tomador: "Supermercados Central S.A.", cteosNumero: "000.010.123", chave: "3526 0310 1112 2200 0133 6700 1010 1234 5601 2345 6789", valorServico: 6540.00, status: "Autorizado", emissao: "10/03/2026" },
  { id: 11, emitente: "Viacao Interestadual Sul", tomador: "Mineradora Atlantico Ltda", cteosNumero: "000.011.234", chave: "3526 0321 3334 4400 0155 6700 1011 2345 6712 3456 7890", valorServico: 4230.25, status: "Autorizado", emissao: "10/03/2026" },
  { id: 12, emitente: "Van Turismo Executivo ME", tomador: "Secretaria Estadual de Esportes", cteosNumero: "000.012.345", chave: "3526 0332 4445 5500 0166 6700 1012 3456 7823 4567 8901", valorServico: 1890.00, status: "Cancelado", emissao: "09/03/2026" },
  { id: 13, emitente: "Rodoviaria Litoral Express", tomador: "Agencia Turismo Ferias Ltda", cteosNumero: "000.013.456", chave: "3526 0343 5556 6600 0177 6700 1013 4567 8934 5678 9012", valorServico: 7650.60, status: "Autorizado", emissao: "09/03/2026" },
  { id: 14, emitente: "Via Segura Carros-Fortes", tomador: "Cooperativa de Credito Rural", cteosNumero: "000.014.567", chave: "3526 0354 6667 7700 0188 6700 1014 5678 9045 6789 0123", valorServico: 2100.00, status: "Pendente", emissao: "08/03/2026" },
  { id: 15, emitente: "Expresso Brasileiro Onibus Ltda", tomador: "Federacao das Industrias", cteosNumero: "000.015.678", chave: "3526 0365 7778 8800 0199 6700 1015 6789 0156 7890 1234", valorServico: 920.80, status: "Autorizado", emissao: "08/03/2026" },
]

export default function HistoricoCtePage() {
  const { settings } = useSettings()
  const [currentPage, setCurrentPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState("Todos")
  const [searchChave, setSearchChave] = useState("")
  const [dateFrom, setDateFrom] = useState(() => {
    const now = new Date()
    return new Date(now.getFullYear(), now.getMonth(), 1).toISOString().split("T")[0]
  })
  const [dateTo, setDateTo] = useState(() => new Date().toISOString().split("T")[0])
  const itemsPerPage = 10

  const [realData, setRealData] = useState<any[]>([])
  const [realLoading, setRealLoading] = useState(false)

  const loadRealData = useCallback(async () => {
    setRealLoading(true)
    try {
      const sb = getSupabase()
      const { data, error } = await sb
        .from('documents')
        .select('*')
        .eq('tipo', 'CTEOS')
        .order('fetched_at', { ascending: false })
        .limit(100)

      if (!error && data) {
        setRealData(data)
      }
    } catch (e) {
      console.error("[DFeAxis] Error loading documents:", e)
    } finally {
      setRealLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!settings.showMockData) {
      loadRealData()
    }
  }, [settings.showMockData, loadRealData])

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
    const statusMap: Record<string, CteosStatus> = {
      available: "Autorizado",
      delivered: "Autorizado",
      expired: "Cancelado",
    }

    const mappedData = realData.map((doc, i) => ({
      id: i,
      chave: doc.chave_acesso || "",
      cnpj: doc.cnpj || "",
      cnpjEmitente: doc.cnpj_emitente || null,
      razaoSocialEmitente: doc.razao_social_emitente || null,
      status: statusMap[doc.status] || (doc.is_resumo ? "Pendente" : "Autorizado"),
      nsu: doc.nsu || "",
      fetchedAt: doc.fetched_at ? new Date(doc.fetched_at).toLocaleString("pt-BR") : "",
    }))

    const filteredReal = mappedData.filter((row) => {
      if (statusFilter !== "Todos" && row.status !== statusFilter) return false
      if (searchChave && !row.chave.toLowerCase().includes(searchChave.toLowerCase())) return false
      return true
    })

    const totalPagesReal = Math.ceil(filteredReal.length / itemsPerPage)
    const paginatedReal = filteredReal.slice(
      (currentPage - 1) * itemsPerPage,
      currentPage * itemsPerPage
    )

    return (
      <div className="flex flex-col gap-6 p-6">
        <div className="flex items-center justify-between">
          <div>
            <h1>CT-e OS Recebidos</h1>
            <p className="text-sm text-muted-foreground">
              Conhecimentos de transporte recebidos via captura automática
            </p>
          </div>
          <Button variant="outline" onClick={loadRealData} disabled={realLoading}>
            {realLoading ? <Loader2 className="size-4 animate-spin" /> : <FileDown className="size-4" />}
            {realLoading ? "Carregando..." : "Atualizar"}
          </Button>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-end gap-3 rounded-lg border p-4">
          <div className="flex flex-col gap-1.5">
            <span className="text-xs font-medium text-muted-foreground">Status</span>
            <Select value={statusFilter} onValueChange={(v) => { if (v) { setStatusFilter(v); setCurrentPage(1) } }}>
              <SelectTrigger className="w-[150px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="Todos">Todos</SelectItem>
                <SelectItem value="Autorizado">Autorizado</SelectItem>
                <SelectItem value="Cancelado">Cancelado</SelectItem>
                <SelectItem value="Pendente">Pendente</SelectItem>
                <SelectItem value="Denegado">Denegado</SelectItem>
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
          <Button variant="default" className="gap-1.5" onClick={loadRealData} disabled={realLoading}>
            <Filter className="size-3.5" />
            Filtrar
          </Button>
        </div>

        {realLoading ? (
          <div className="flex flex-col items-center justify-center py-16 gap-3">
            <Loader2 className="size-8 animate-spin text-muted-foreground" />
            <p className="text-sm text-muted-foreground">Carregando documentos...</p>
          </div>
        ) : realData.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <Inbox className="size-12 text-muted-foreground/30 mb-4" />
            <p className="text-sm text-muted-foreground">Nenhum CT-e OS capturado. CT-e OS (modelo 67) é específico para transporte de passageiros e valores — só aparecem quando houver emissão para os CNPJs cadastrados.</p>
          </div>
        ) : (
          <>
            <div className="rounded-lg border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Chave de Acesso</TableHead>
                    <TableHead>Fornecedor</TableHead>
                    <TableHead>NSU</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Capturado em</TableHead>
                    <TableHead>Ações</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {paginatedReal.map((row) => (
                    <TableRow key={row.id}>
                      <TableCell className="max-w-[220px] truncate font-mono text-xs">
                        {row.chave}
                      </TableCell>
                      <TableCell>
                        <div>
                          {row.razaoSocialEmitente && (
                            <p className="text-xs font-medium text-foreground truncate max-w-[180px]">
                              {row.razaoSocialEmitente}
                            </p>
                          )}
                          <p className="font-mono text-xs text-muted-foreground">
                            {row.cnpjEmitente || row.cnpj}
                            {!row.cnpjEmitente && (
                              <span className="ml-1 text-[10px] text-amber-600" title="CNPJ do certificado (emitente indisponivel)">(cert)</span>
                            )}
                          </p>
                        </div>
                      </TableCell>
                      <TableCell className="font-mono text-xs">{row.nsu}</TableCell>
                      <TableCell>
                        <span
                          className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${statusConfig[row.status].className}`}
                        >
                          {statusConfig[row.status].label}
                        </span>
                      </TableCell>
                      <TableCell className="text-xs">{row.fetchedAt}</TableCell>
                      <TableCell>
                        <div className="flex items-center gap-1">
                          <Button variant="ghost" size="icon-xs" title="Visualizar XML" onClick={() => toast.info("Visualização de XML em breve")}>
                            <Eye className="size-3.5" />
                          </Button>
                          <Button variant="ghost" size="icon-xs" title="Download" onClick={() => toast.info("Download do XML em breve")}>
                            <Download className="size-3.5" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                  {paginatedReal.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={6} className="h-24 text-center text-muted-foreground">
                        Nenhum CT-e OS encontrado com os filtros aplicados.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>

            {/* Pagination */}
            <div className="flex items-center justify-between">
              <p className="text-sm text-muted-foreground">
                Mostrando {filteredReal.length === 0 ? 0 : ((currentPage - 1) * itemsPerPage) + 1} a{" "}
                {Math.min(currentPage * itemsPerPage, filteredReal.length)} de{" "}
                {filteredReal.length} registros
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
                {Array.from({ length: Math.min(totalPagesReal, 5) }, (_, i) => i + 1).map((page) => (
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
                  disabled={currentPage === totalPagesReal || totalPagesReal === 0}
                  onClick={() => setCurrentPage((p) => p + 1)}
                >
                  <ChevronRight className="size-4" />
                </Button>
              </div>
            </div>
          </>
        )}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1>CT-e OS Recebidos</h1>
          <p className="text-sm text-muted-foreground">
            Conhecimentos de transporte recebidos via captura automática
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
          <span className="text-xs font-medium text-muted-foreground">De</span>
          <Input type="date" className="w-[150px]" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
        </div>

        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-muted-foreground">Até</span>
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
              <SelectItem value="Cancelado">Cancelado</SelectItem>
              <SelectItem value="Pendente">Pendente</SelectItem>
              <SelectItem value="Denegado">Denegado</SelectItem>
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

        <Button variant="default" className="gap-1.5" onClick={(e) => e.preventDefault()}>
          <Filter className="size-3.5" />
          Filtrar
        </Button>
      </div>

      {/* Table */}
      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Emitente (Transportadora)</TableHead>
              <TableHead>Tomador</TableHead>
              <TableHead>CT-e OS N.</TableHead>
              <TableHead>Chave de Acesso</TableHead>
              <TableHead className="text-right">Valor Serviço (R$)</TableHead>
              <TableHead>Emissão</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Ações</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {paginatedData.map((row) => (
              <TableRow key={row.id}>
                <TableCell className="max-w-[180px] truncate font-medium">
                  {row.emitente}
                </TableCell>
                <TableCell className="max-w-[180px] truncate">
                  {row.tomador}
                </TableCell>
                <TableCell className="font-mono text-xs">{row.cteosNumero}</TableCell>
                <TableCell className="max-w-[180px] truncate font-mono text-xs">
                  {row.chave}
                </TableCell>
                <TableCell className="text-right font-mono">
                  {row.valorServico.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                </TableCell>
                <TableCell>{row.emissao}</TableCell>
                <TableCell>
                  <span
                    className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${statusConfig[row.status].className}`}
                  >
                    {statusConfig[row.status].label}
                  </span>
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-1">
                    <Button variant="ghost" size="icon-xs" title="Visualizar XML" onClick={() => toast.info("Visualização de XML em breve")}>
                      <Eye className="size-3.5" />
                    </Button>
                    <Button variant="ghost" size="icon-xs" title="Download" onClick={() => toast.info("Download do XML em breve")}>
                      <Download className="size-3.5" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
            {paginatedData.length === 0 && (
              <TableRow>
                <TableCell colSpan={8} className="h-24 text-center text-muted-foreground">
                  Nenhum CT-e OS encontrado com os filtros aplicados.
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
