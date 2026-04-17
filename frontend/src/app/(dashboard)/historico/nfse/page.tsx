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
  AlertTriangle,
  Inbox,
  Loader2,
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

const statusConfig: Record<NfseStatus, { label: string; className: string }> = {
  Emitida: {
    label: "Disponivel",
    className: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
  },
  Cancelada: {
    label: "Cancelada",
    className: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
  },
  Substituida: {
    label: "Substituida",
    className: "bg-gray-100 text-gray-600 dark:bg-gray-800/50 dark:text-gray-400",
  },
  Pendente: {
    label: "Pendente",
    className: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400",
  },
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
  const { settings } = useSettings()
  const [currentPage, setCurrentPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState("Todos")
  const [searchNumero, setSearchNumero] = useState("")
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
        .eq('tipo', 'NFSE')
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
    if (searchNumero && !row.numero.toLowerCase().includes(searchNumero.toLowerCase())) return false
    return true
  })

  const totalPages = Math.ceil(filteredData.length / itemsPerPage)
  const paginatedData = filteredData.slice(
    (currentPage - 1) * itemsPerPage,
    currentPage * itemsPerPage
  )

  if (!settings.showMockData) {
    const statusMap: Record<string, NfseStatus> = {
      available: "Emitida",
      delivered: "Emitida",
      expired: "Cancelada",
    }

    const mappedData = realData.map((doc, i) => ({
      id: i,
      chave: doc.chave_acesso || "",
      cnpj: doc.cnpj || "",
      cnpjEmitente: doc.cnpj_emitente || null,
      razaoSocialEmitente: doc.razao_social_emitente || null,
      status: statusMap[doc.status] || (doc.is_resumo ? "Pendente" : "Emitida"),
      nsu: doc.nsu || "",
      fetchedAt: doc.fetched_at ? new Date(doc.fetched_at).toLocaleString("pt-BR") : "",
    }))

    const filteredReal = mappedData.filter((row) => {
      if (statusFilter !== "Todos" && row.status !== statusFilter) return false
      if (searchNumero && !row.chave.toLowerCase().includes(searchNumero.toLowerCase())) return false
      return true
    })

    const totalPagesReal = Math.ceil(filteredReal.length / itemsPerPage)
    const paginatedReal = filteredReal.slice(
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
              Notas fiscais de serviço recebidas via Ambiente Nacional
            </p>
          </div>
          <Button variant="outline" onClick={loadRealData} disabled={realLoading}>
            {realLoading ? <Loader2 className="size-4 animate-spin" /> : <FileDown className="size-4" />}
            {realLoading ? "Carregando..." : "Atualizar"}
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
            <span className="text-xs font-medium text-muted-foreground">Chave / Número</span>
            <Input
              placeholder="Buscar..."
              className="w-[220px]"
              value={searchNumero}
              onChange={(e) => { setSearchNumero(e.target.value); setCurrentPage(1) }}
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
            <p className="text-sm text-muted-foreground">Nenhuma NFS-e capturada. Configure um certificado e execute uma captura para ver documentos reais.</p>
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
                          <Button variant="ghost" size="icon-xs" title="Visualizar" onClick={() => toast.info("Visualização de XML em breve")}>
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
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">NFS-e Recebidas</h1>
            <Badge variant="outline" className="bg-amber-50 text-amber-700 border-amber-200 text-[10px]">
              ADN
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            Notas fiscais de serviço recebidas via Ambiente Nacional
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
              <SelectItem value="Emitida">Emitida</SelectItem>
              <SelectItem value="Cancelada">Cancelada</SelectItem>
              <SelectItem value="Substituida">Substituída</SelectItem>
              <SelectItem value="Pendente">Pendente</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-muted-foreground">Número NFS-e</span>
          <Input
            placeholder="Buscar por número..."
            className="w-[200px]"
            value={searchNumero}
            onChange={(e) => { setSearchNumero(e.target.value); setCurrentPage(1) }}
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
              <TableHead>Prestador</TableHead>
              <TableHead>Tomador</TableHead>
              <TableHead>Município</TableHead>
              <TableHead>N NFS-e</TableHead>
              <TableHead className="text-right">Valor (R$)</TableHead>
              <TableHead>Competência</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Ações</TableHead>
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
                  <span
                    className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${statusConfig[row.status].className}`}
                  >
                    {statusConfig[row.status].label}
                  </span>
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-1">
                    <Button variant="ghost" size="icon-xs" title="Visualizar" onClick={() => toast.info("Visualização de XML em breve")}>
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
