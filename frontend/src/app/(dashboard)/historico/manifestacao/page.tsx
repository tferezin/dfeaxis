"use client"

import { useCallback, useEffect, useState } from "react"
import { FileCheck, Loader2, Search, Filter, ChevronLeft, ChevronRight } from "lucide-react"
import {
  Card,
  CardContent,
  CardDescription,
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
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { apiFetch } from "@/lib/api"

/**
 * Histórico de manifestação — consome GET /manifestacao/historico.
 *
 * Mostra todos os eventos de manifestação enviados (ciência, confirmação,
 * desconhecimento, não realizada) com origem (auto/manual/api), status
 * SEFAZ (cstat/xmotivo), e protocolo.
 *
 * Filtros: chave_acesso, tipo_evento, limit.
 */

type TipoEvento = "" | "210210" | "210200" | "210220" | "210240"

interface ManifestacaoEvent {
  chave_acesso: string
  tipo_evento: string
  descricao: string
  cstat: string
  xmotivo: string
  protocolo: string | null
  source: string
  latency_ms: number | null
  created_at: string
}

interface HistoricoResponse {
  total: number
  events: ManifestacaoEvent[]
}

const TIPO_EVENTO_LABELS: Record<string, { label: string; color: string }> = {
  "210210": { label: "Ciência", color: "bg-blue-50 text-blue-700 ring-blue-600/20" },
  "210200": { label: "Confirmada", color: "bg-emerald-50 text-emerald-700 ring-emerald-600/20" },
  "210220": { label: "Desconhecida", color: "bg-amber-50 text-amber-700 ring-amber-600/20" },
  "210240": { label: "Não realizada", color: "bg-red-50 text-red-700 ring-red-600/20" },
}

const SOURCE_LABELS: Record<string, string> = {
  auto_capture: "Automático",
  dashboard: "Painel",
  api: "API",
  sap: "SAP DRC",
}

function isSefazSuccess(cstat: string): boolean {
  // cstat 135 = evento registrado, 136 = vinculado, 573 = duplicidade
  return ["135", "136", "573"].includes(cstat)
}

export default function HistoricoManifestacaoPage() {
  const [events, setEvents] = useState<ManifestacaoEvent[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Filtros
  const [filterChave, setFilterChave] = useState("")
  const [filterTipo, setFilterTipo] = useState<TipoEvento>("")
  const [limit] = useState(100)

  // Paginação client-side: backend já limita a 100 eventos; aqui dividimos
  // em páginas de 20 pra facilitar a leitura. Filtro no backend reduz o
  // dataset antes da paginação local.
  const [currentPage, setCurrentPage] = useState(1)
  const itemsPerPage = 20

  const chaveTrimmed = filterChave.trim()
  const chaveInvalida = chaveTrimmed.length > 0 && chaveTrimmed.length !== 44

  const loadHistory = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      // Backend exige exatamente 44 dígitos — só envia se completo,
      // senão devolve 422 e a UI mostra erro feio.
      if (chaveTrimmed.length === 44) params.set("chave_acesso", chaveTrimmed)
      if (filterTipo) params.set("tipo_evento", filterTipo)
      params.set("limit", String(limit))

      const res = await apiFetch<HistoricoResponse>(
        `/manifestacao/historico?${params.toString()}`
      )
      setEvents(res.events || [])
      setTotal(res.total || 0)
      setCurrentPage(1)  // reset paginação ao aplicar novo filtro
    } catch (e) {
      console.error("[DFeAxis] historico manifestacao error:", e)
      setError(
        e instanceof Error ? e.message : "Erro ao carregar histórico"
      )
      setEvents([])
    } finally {
      setLoading(false)
    }
  }, [chaveTrimmed, filterTipo, limit])

  useEffect(() => {
    loadHistory()
  }, [loadHistory])

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
            <FileCheck className="size-6 text-primary" />
            Histórico de Manifestação
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Todos os eventos de manifestação enviados — ciência automática,
            confirmação via painel, API ou SAP.
          </p>
        </div>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Filter className="size-4" />
            Filtros
          </CardTitle>
          <CardDescription>
            Busque por chave de acesso ou tipo de evento SEFAZ.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-[1fr_200px_auto]">
            <div className="relative">
              <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
              <Input
                type="text"
                placeholder="Chave de acesso (44 dígitos)"
                value={filterChave}
                onChange={(e) => setFilterChave(e.target.value.replace(/\D/g, ""))}
                className={cn(
                  "pl-9 font-mono text-xs",
                  chaveInvalida && "border-amber-500 focus-visible:ring-amber-500"
                )}
                maxLength={44}
                aria-invalid={chaveInvalida}
              />
              {chaveInvalida && (
                <p className="text-[10px] text-amber-600 mt-1 ml-0.5">
                  Digite os 44 dígitos ({chaveTrimmed.length}/44)
                </p>
              )}
            </div>
            <select
              value={filterTipo}
              onChange={(e) => setFilterTipo(e.target.value as TipoEvento)}
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              aria-label="Filtrar por tipo de evento"
            >
              <option value="">Todos os eventos</option>
              <option value="210210">210210 — Ciência</option>
              <option value="210200">210200 — Confirmação</option>
              <option value="210220">210220 — Desconhecimento</option>
              <option value="210240">210240 — Não realizada</option>
            </select>
            <Button onClick={loadHistory} disabled={loading} size="default">
              {loading ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                "Buscar"
              )}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base">Eventos</CardTitle>
              <CardDescription>
                {loading
                  ? "Carregando..."
                  : `${total.toLocaleString("pt-BR")} evento${total === 1 ? "" : "s"} encontrado${total === 1 ? "" : "s"}`}
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="px-0">
          {error ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <p className="text-sm text-destructive font-medium">{error}</p>
              <Button
                variant="outline"
                size="sm"
                onClick={loadHistory}
                className="mt-3"
              >
                Tentar novamente
              </Button>
            </div>
          ) : loading && events.length === 0 ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="size-6 animate-spin text-muted-foreground" />
            </div>
          ) : events.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <FileCheck className="size-12 text-muted-foreground/30 mb-3" />
              <p className="text-sm text-muted-foreground">
                Nenhum evento de manifestação encontrado.
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                Eventos aparecem aqui conforme você captura documentos (ciência automática) ou envia manifestos manualmente.
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="pl-4">Data / Hora</TableHead>
                  <TableHead>Evento</TableHead>
                  <TableHead>Origem</TableHead>
                  <TableHead>Chave de Acesso</TableHead>
                  <TableHead>Protocolo</TableHead>
                  <TableHead className="pr-4">Status SEFAZ</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {events.slice(
                  (currentPage - 1) * itemsPerPage,
                  currentPage * itemsPerPage,
                ).map((ev, i) => {
                  const eventMeta = TIPO_EVENTO_LABELS[ev.tipo_evento] || {
                    label: ev.tipo_evento,
                    color: "bg-gray-50 text-gray-700 ring-gray-600/20",
                  }
                  const success = isSefazSuccess(ev.cstat)
                  return (
                    <TableRow key={`${ev.chave_acesso}-${ev.created_at}-${i}`} className="group">
                      <TableCell className="pl-4 text-xs text-muted-foreground">
                        {new Date(ev.created_at).toLocaleString("pt-BR", {
                          day: "2-digit",
                          month: "2-digit",
                          year: "numeric",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </TableCell>
                      <TableCell>
                        <div>
                          <span
                            className={cn(
                              "inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold ring-1 ring-inset",
                              eventMeta.color
                            )}
                          >
                            {eventMeta.label}
                          </span>
                          <p className="text-[10px] text-muted-foreground mt-0.5">
                            {ev.tipo_evento}
                          </p>
                        </div>
                      </TableCell>
                      <TableCell>
                        <span className="text-xs text-muted-foreground">
                          {SOURCE_LABELS[ev.source] || ev.source}
                        </span>
                      </TableCell>
                      <TableCell className="font-mono text-[10px] text-muted-foreground">
                        {ev.chave_acesso.slice(0, 14)}...{ev.chave_acesso.slice(-6)}
                      </TableCell>
                      <TableCell className="font-mono text-[10px] text-muted-foreground">
                        {ev.protocolo || "—"}
                      </TableCell>
                      <TableCell className="pr-4">
                        <div>
                          <span
                            className={cn(
                              "inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ring-1 ring-inset",
                              success
                                ? "bg-emerald-50 text-emerald-700 ring-emerald-600/20"
                                : "bg-red-50 text-red-700 ring-red-600/20"
                            )}
                          >
                            cStat {ev.cstat}
                          </span>
                          <p className="text-[10px] text-muted-foreground mt-0.5 max-w-[200px] truncate">
                            {ev.xmotivo}
                          </p>
                        </div>
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          )}

          {/* Pagination — só renderiza se houver mais de 1 página */}
          {!loading && !error && events.length > itemsPerPage && (
            <div className="flex items-center justify-between px-4 py-3 border-t">
              <p className="text-sm text-muted-foreground">
                Mostrando {(currentPage - 1) * itemsPerPage + 1} a{" "}
                {Math.min(currentPage * itemsPerPage, events.length)} de{" "}
                {events.length} eventos
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
                {Array.from(
                  { length: Math.ceil(events.length / itemsPerPage) },
                  (_, i) => i + 1,
                ).map((page) => (
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
                  disabled={
                    currentPage === Math.ceil(events.length / itemsPerPage)
                  }
                  onClick={() => setCurrentPage((p) => p + 1)}
                >
                  <ChevronRight className="size-4" />
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
