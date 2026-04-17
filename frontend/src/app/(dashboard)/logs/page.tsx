"use client"

import { useState, useEffect, useCallback } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Filter,
  ChevronLeft,
  ChevronRight,
  Activity,
  CheckCircle2,
  FileSearch,
  Clock,
  Inbox,
  Loader2,
} from "lucide-react"
import { useSettings } from "@/hooks/use-settings"
import { getSupabase } from "@/lib/supabase"

type LogResultado = "Sucesso" | "Erro"
type LogTipo = "NF-e" | "CT-e" | "MDF-e" | "NFS-e"
type LogAcao = "Captura" | "Ciencia" | "Download SAP"

interface LogRow {
  id: number
  dataHora: string
  cnpj: string
  tipo: LogTipo
  acao: LogAcao
  resultado: LogResultado
  docsEncontrados: number
  latencia: number
  detalhes: string | null
}

const mockLogs: LogRow[] = [
  { id: 1, dataHora: "17/03/2026 08:00:12", cnpj: "12.345.678/0001-90", tipo: "NF-e", acao: "Captura", resultado: "Sucesso", docsEncontrados: 3, latencia: 1240, detalhes: null },
  { id: 2, dataHora: "17/03/2026 07:45:08", cnpj: "98.765.432/0001-10", tipo: "CT-e", acao: "Captura", resultado: "Sucesso", docsEncontrados: 1, latencia: 890, detalhes: null },
  { id: 3, dataHora: "17/03/2026 07:30:05", cnpj: "12.345.678/0001-90", tipo: "NF-e", acao: "Ciencia", resultado: "Sucesso", docsEncontrados: 2, latencia: 2100, detalhes: null },
  { id: 4, dataHora: "17/03/2026 07:15:02", cnpj: "55.666.777/0001-88", tipo: "NF-e", acao: "Captura", resultado: "Erro", docsEncontrados: 0, latencia: 30200, detalhes: "Timeout: SEFAZ não respondeu em 30s" },
  { id: 5, dataHora: "17/03/2026 07:00:11", cnpj: "12.345.678/0001-90", tipo: "NF-e", acao: "Download SAP", resultado: "Sucesso", docsEncontrados: 5, latencia: 340, detalhes: null },
  { id: 6, dataHora: "17/03/2026 06:45:09", cnpj: "98.765.432/0001-10", tipo: "NF-e", acao: "Captura", resultado: "Sucesso", docsEncontrados: 0, latencia: 780, detalhes: null },
  { id: 7, dataHora: "17/03/2026 06:30:14", cnpj: "11.222.333/0001-44", tipo: "MDF-e", acao: "Captura", resultado: "Sucesso", docsEncontrados: 2, latencia: 1560, detalhes: null },
  { id: 8, dataHora: "17/03/2026 06:15:03", cnpj: "55.666.777/0001-88", tipo: "NF-e", acao: "Captura", resultado: "Erro", docsEncontrados: 0, latencia: 150, detalhes: "Circuit breaker aberto: 3 falhas consecutivas no endpoint SP" },
  { id: 9, dataHora: "17/03/2026 06:00:07", cnpj: "12.345.678/0001-90", tipo: "NF-e", acao: "Captura", resultado: "Sucesso", docsEncontrados: 1, latencia: 1100, detalhes: null },
  { id: 10, dataHora: "17/03/2026 05:45:11", cnpj: "98.765.432/0001-10", tipo: "CT-e", acao: "Ciencia", resultado: "Sucesso", docsEncontrados: 1, latencia: 1890, detalhes: null },
  { id: 11, dataHora: "17/03/2026 05:30:06", cnpj: "11.222.333/0001-44", tipo: "NF-e", acao: "Captura", resultado: "Sucesso", docsEncontrados: 4, latencia: 1340, detalhes: null },
  { id: 12, dataHora: "17/03/2026 05:15:09", cnpj: "55.666.777/0001-88", tipo: "NFS-e", acao: "Captura", resultado: "Erro", docsEncontrados: 0, latencia: 5020, detalhes: "Certificado A1 expirado em 15/03/2026" },
  { id: 13, dataHora: "17/03/2026 05:00:03", cnpj: "12.345.678/0001-90", tipo: "NF-e", acao: "Download SAP", resultado: "Sucesso", docsEncontrados: 8, latencia: 520, detalhes: null },
  { id: 14, dataHora: "17/03/2026 04:45:12", cnpj: "98.765.432/0001-10", tipo: "NF-e", acao: "Captura", resultado: "Sucesso", docsEncontrados: 2, latencia: 980, detalhes: null },
  { id: 15, dataHora: "17/03/2026 04:30:08", cnpj: "11.222.333/0001-44", tipo: "CT-e", acao: "Captura", resultado: "Sucesso", docsEncontrados: 0, latencia: 750, detalhes: null },
  { id: 16, dataHora: "17/03/2026 04:15:05", cnpj: "55.666.777/0001-88", tipo: "NF-e", acao: "Ciencia", resultado: "Sucesso", docsEncontrados: 3, latencia: 2340, detalhes: null },
  { id: 17, dataHora: "17/03/2026 04:00:11", cnpj: "12.345.678/0001-90", tipo: "MDF-e", acao: "Captura", resultado: "Sucesso", docsEncontrados: 1, latencia: 1670, detalhes: null },
  { id: 18, dataHora: "17/03/2026 03:45:07", cnpj: "98.765.432/0001-10", tipo: "NF-e", acao: "Captura", resultado: "Erro", docsEncontrados: 0, latencia: 30100, detalhes: "Timeout: SEFAZ não respondeu em 30s" },
  { id: 19, dataHora: "17/03/2026 03:30:02", cnpj: "11.222.333/0001-44", tipo: "NF-e", acao: "Download SAP", resultado: "Sucesso", docsEncontrados: 12, latencia: 890, detalhes: null },
  { id: 20, dataHora: "17/03/2026 03:15:10", cnpj: "55.666.777/0001-88", tipo: "NF-e", acao: "Captura", resultado: "Sucesso", docsEncontrados: 2, latencia: 1120, detalhes: null },
  { id: 21, dataHora: "17/03/2026 03:00:04", cnpj: "12.345.678/0001-90", tipo: "CT-e", acao: "Captura", resultado: "Sucesso", docsEncontrados: 0, latencia: 670, detalhes: null },
  { id: 22, dataHora: "17/03/2026 02:45:08", cnpj: "98.765.432/0001-10", tipo: "NF-e", acao: "Ciencia", resultado: "Sucesso", docsEncontrados: 1, latencia: 1980, detalhes: null },
  { id: 23, dataHora: "17/03/2026 02:30:13", cnpj: "11.222.333/0001-44", tipo: "NFS-e", acao: "Captura", resultado: "Sucesso", docsEncontrados: 3, latencia: 2450, detalhes: null },
  { id: 24, dataHora: "17/03/2026 02:15:06", cnpj: "55.666.777/0001-88", tipo: "NF-e", acao: "Captura", resultado: "Erro", docsEncontrados: 0, latencia: 200, detalhes: "Circuit breaker aberto: endpoint MG indisponível" },
  { id: 25, dataHora: "17/03/2026 02:00:09", cnpj: "12.345.678/0001-90", tipo: "NF-e", acao: "Captura", resultado: "Sucesso", docsEncontrados: 1, latencia: 1050, detalhes: null },
]

const CNPJS_LOG = [
  "Todos",
  "12.345.678/0001-90",
  "98.765.432/0001-10",
  "11.222.333/0001-44",
  "55.666.777/0001-88",
]

export default function LogsCaptura() {
  const { settings } = useSettings()
  const [currentPage, setCurrentPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState("Todos")
  const [tipoFilter, setTipoFilter] = useState("Todos")
  const [cnpjFilter, setCnpjFilter] = useState("Todos")
  // Dynamic defaults: 1st of current month to today
  const [dateFrom, setDateFrom] = useState(() => {
    const now = new Date()
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-01`
  })
  const [dateTo, setDateTo] = useState(() => {
    const now = new Date()
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`
  })
  const itemsPerPage = 10

  const [realLogs, setRealLogs] = useState<LogRow[]>([])
  const [realLoading, setRealLoading] = useState(false)
  const [realCnpjs, setRealCnpjs] = useState<string[]>(["Todos"])

  const tipoMap: Record<string, LogTipo> = {
    NFE: "NF-e",
    CTE: "CT-e",
    MDFE: "MDF-e",
    NFSE: "NFS-e",
  }

  const loadRealData = useCallback(async () => {
    setRealLoading(true)
    try {
      const sb = getSupabase()
      // Build date range: start of dateFrom to end of dateTo (inclusive)
      const startISO = `${dateFrom}T00:00:00.000Z`
      const endISO = `${dateTo}T23:59:59.999Z`

      const { data, error } = await sb
        .from('polling_log')
        .select('id, tipo, cnpj, status, docs_found, latency_ms, error_message, created_at, triggered_by')
        .gte('created_at', startISO)
        .lte('created_at', endISO)
        .order('created_at', { ascending: false })
        .limit(200)

      if (!error && data) {
        const mapped: LogRow[] = data.map((row: any, i: number) => ({
          id: row.id ?? i,
          dataHora: row.created_at
            ? new Date(row.created_at).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" })
            : "--",
          cnpj: row.cnpj || "--",
          tipo: (tipoMap[row.tipo] || row.tipo || "NF-e") as LogTipo,
          acao: (row.triggered_by === "sap" ? "Download SAP" : "Captura") as LogAcao,
          resultado: (row.status === "success" ? "Sucesso" : "Erro") as LogResultado,
          docsEncontrados: row.docs_found ?? 0,
          latencia: row.latency_ms ?? 0,
          detalhes: row.error_message || null,
        }))
        setRealLogs(mapped)

        // Extract unique CNPJs for filter
        const uniqueCnpjs = Array.from(new Set(mapped.map((r) => r.cnpj).filter((c) => c !== "--")))
        setRealCnpjs(["Todos", ...uniqueCnpjs])
      }
    } catch (e) {
      console.error("[DFeAxis] Error loading logs:", e)
    } finally {
      setRealLoading(false)
    }
  }, [dateFrom, dateTo])

  useEffect(() => {
    if (!settings.showMockData) loadRealData()
  }, [settings.showMockData, loadRealData])

  const showMock = settings.showMockData
  const sourceData = showMock ? mockLogs : realLogs
  const cnpjOptions = showMock ? CNPJS_LOG : realCnpjs

  const filteredData = sourceData.filter((row) => {
    if (statusFilter !== "Todos" && row.resultado !== statusFilter) return false
    if (tipoFilter !== "Todos" && row.tipo !== tipoFilter) return false
    if (cnpjFilter !== "Todos" && row.cnpj !== cnpjFilter) return false
    return true
  }).sort((a, b) => b.dataHora.localeCompare(a.dataHora))

  const totalPages = Math.ceil(filteredData.length / itemsPerPage)
  const paginatedData = filteredData.slice(
    (currentPage - 1) * itemsPerPage,
    currentPage * itemsPerPage
  )

  // Summary computations
  const totalExecucoes = sourceData.length
  const sucessos = sourceData.filter((r) => r.resultado === "Sucesso").length
  const taxaSucesso = totalExecucoes > 0 ? ((sucessos / totalExecucoes) * 100).toFixed(1) : "0"
  const docsCapturados = sourceData.reduce((acc, r) => acc + r.docsEncontrados, 0)
  const ultimaExecucao = sourceData.length > 0 ? (sourceData[0]?.dataHora ?? "--") : "--"

  const hasData = showMock || realLogs.length > 0

  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Logs de Captura</h1>
        <p className="text-sm text-muted-foreground">
          Histórico de execuções dos últimos 120 dias.
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card size="sm">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-1">
            <CardTitle className="text-sm font-medium text-muted-foreground">Total de execuções</CardTitle>
            <Activity className="size-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{totalExecucoes}</div>
            <p className="text-xs text-muted-foreground">Últimos 30 dias</p>
          </CardContent>
        </Card>

        <Card size="sm">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-1">
            <CardTitle className="text-sm font-medium text-muted-foreground">Taxa de sucesso</CardTitle>
            <CheckCircle2 className="size-4 text-green-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{taxaSucesso}%</div>
            <p className="text-xs text-muted-foreground">{sucessos} de {totalExecucoes} execuções</p>
          </CardContent>
        </Card>

        <Card size="sm">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-1">
            <CardTitle className="text-sm font-medium text-muted-foreground">Docs capturados</CardTitle>
            <FileSearch className="size-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{docsCapturados}</div>
            <p className="text-xs text-muted-foreground">Total no período</p>
          </CardContent>
        </Card>

        <Card size="sm">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-1">
            <CardTitle className="text-sm font-medium text-muted-foreground">Última execução</CardTitle>
            <Clock className="size-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-lg font-bold">{ultimaExecucao}</div>
            <p className="text-xs text-muted-foreground">Horário do servidor</p>
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-end gap-3 rounded-lg border p-4">
        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-muted-foreground">CNPJ</span>
          <select
            className="h-9 w-[200px] rounded-md border border-input bg-background px-3 text-sm"
            value={cnpjFilter}
            onChange={(e) => { setCnpjFilter(e.target.value); setCurrentPage(1) }}
          >
            {cnpjOptions.map((cnpj) => (
              <option key={cnpj} value={cnpj}>{cnpj}</option>
            ))}
          </select>
        </div>

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
          <select
            className="h-9 w-[130px] rounded-md border border-input bg-background px-3 text-sm"
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value); setCurrentPage(1) }}
          >
            <option value="Todos">Todos</option>
            <option value="Sucesso">Sucesso</option>
            <option value="Erro">Erro</option>
          </select>
        </div>

        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-muted-foreground">Tipo</span>
          <select
            className="h-9 w-[130px] rounded-md border border-input bg-background px-3 text-sm"
            value={tipoFilter}
            onChange={(e) => { setTipoFilter(e.target.value); setCurrentPage(1) }}
          >
            <option value="Todos">Todos</option>
            <option value="NF-e">NF-e</option>
            <option value="CT-e">CT-e</option>
            <option value="MDF-e">MDF-e</option>
            <option value="NFS-e">NFS-e</option>
          </select>
        </div>

        <Button variant="default" className="gap-1.5" onClick={!showMock ? () => { loadRealData(); setCurrentPage(1) } : undefined} disabled={!showMock && realLoading}>
          <Filter className="size-3.5" />
          Filtrar
        </Button>
      </div>

      {/* Table */}
      {!showMock && realLoading ? (
        <div className="flex flex-col items-center justify-center py-16 gap-3">
          <Loader2 className="size-8 animate-spin text-muted-foreground" />
          <p className="text-sm text-muted-foreground">Carregando logs...</p>
        </div>
      ) : !hasData ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <Inbox className="size-12 text-muted-foreground/30 mb-4" />
          <p className="text-sm text-muted-foreground">Nenhum log de captura registrado.</p>
        </div>
      ) : (<>
      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Data/Hora</TableHead>
              <TableHead>CNPJ</TableHead>
              <TableHead>Tipo</TableHead>
              <TableHead>Ação</TableHead>
              <TableHead>Resultado</TableHead>
              <TableHead className="text-right">Docs encontrados</TableHead>
              <TableHead className="text-right">Latência (ms)</TableHead>
              <TableHead>Detalhes</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {paginatedData.map((row) => (
              <TableRow key={row.id}>
                <TableCell className="font-mono text-xs whitespace-nowrap">{row.dataHora}</TableCell>
                <TableCell className="font-mono text-xs">{row.cnpj}</TableCell>
                <TableCell>
                  <Badge variant="secondary" className="text-xs">
                    {row.tipo}
                  </Badge>
                </TableCell>
                <TableCell className="text-sm">{row.acao}</TableCell>
                <TableCell>
                  {row.resultado === "Sucesso" ? (
                    <span className="inline-flex items-center rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-medium text-green-800 dark:bg-green-900/30 dark:text-green-400">
                      Sucesso
                    </span>
                  ) : (
                    <span className="inline-flex items-center rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-medium text-red-800 dark:bg-red-900/30 dark:text-red-400">
                      Erro
                    </span>
                  )}
                </TableCell>
                <TableCell className="text-right font-mono text-sm">{row.docsEncontrados}</TableCell>
                <TableCell className="text-right font-mono text-sm">
                  <span className={row.latencia > 5000 ? "text-red-600 dark:text-red-400 font-semibold" : ""}>
                    {row.latencia.toLocaleString("pt-BR")}
                  </span>
                </TableCell>
                <TableCell className="max-w-[280px] truncate text-xs text-muted-foreground">
                  {row.detalhes ?? "--"}
                </TableCell>
              </TableRow>
            ))}
            {paginatedData.length === 0 && (
              <TableRow>
                <TableCell colSpan={8} className="h-24 text-center text-muted-foreground">
                  Nenhum log encontrado com os filtros aplicados.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Mostrando {filteredData.length === 0 ? 0 : ((currentPage - 1) * itemsPerPage) + 1} a{" "}
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
          {Array.from({ length: Math.min(totalPages, 10) }, (_, i) => i + 1).map((page) => (
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
            disabled={currentPage === totalPages || totalPages === 0}
            onClick={() => setCurrentPage((p) => p + 1)}
          >
            <ChevronRight className="size-4" />
          </Button>
        </div>
      </div>
      </>)}
    </div>
  )
}
