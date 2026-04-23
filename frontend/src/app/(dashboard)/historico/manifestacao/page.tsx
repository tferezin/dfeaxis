"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import {
  AlertTriangle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  FileCheck,
  Filter,
  Loader2,
  Search,
  Send,
} from "lucide-react"
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import { apiFetch } from "@/lib/api"

/**
 * Página de Manifestação — 2 abas:
 *  - Pendentes: NF-e com ciência aceita aguardando decisão definitiva
 *    (Confirmar / Desconhecer / Não Realizada). Checkboxes + envio em lote.
 *  - Histórico: eventos de manifestação já enviados (auditoria).
 */

// ============================================================================
// Tipos compartilhados
// ============================================================================

type TipoEventoDefinitivo = "210200" | "210220" | "210240"
type TipoEventoFiltro = "" | "210210" | "210200" | "210220" | "210240"

interface DocumentoPendente {
  chave: string
  nsu: string
  tipo: string | null
  cnpj_emitente: string | null
  razao_social_emitente: string | null
  cnpj_destinatario: string | null
  numero_documento: string | null
  data_emissao: string | null
  valor_total: number | null
  manifestacao_status: string
  fetched_at: string
}

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

interface BatchResponse {
  total: number
  sucesso: number
  erro: number
  resultados: Array<{
    chave_acesso: string
    tipo_evento: string
    cstat: string
    xmotivo: string
    success: boolean
  }>
}

// ============================================================================
// Helpers
// ============================================================================

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

const EVENTO_DEFINITIVO_OPTIONS: {
  value: TipoEventoDefinitivo
  label: string
  description: string
  requiresJustification: boolean
  tone: "emerald" | "amber" | "red"
}[] = [
  {
    value: "210200",
    label: "Confirmar Operação",
    description:
      "NF-e é válida e a operação aconteceu (ex: mercadoria entregue, serviço prestado).",
    requiresJustification: false,
    tone: "emerald",
  },
  {
    value: "210220",
    label: "Desconhecer Operação",
    description:
      "NF-e emitida indevidamente contra seu CNPJ. Você não reconhece a operação.",
    requiresJustification: true,
    tone: "amber",
  },
  {
    value: "210240",
    label: "Operação não Realizada",
    description:
      "Operação foi cancelada antes do recebimento (ex: devolução antes da entrega).",
    requiresJustification: true,
    tone: "red",
  },
]

function isSefazSuccess(cstat: string): boolean {
  return ["135", "136", "573"].includes(cstat)
}

function formatCurrency(value: number | null): string {
  if (value === null || value === undefined) return "—"
  return value.toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
  })
}

function formatCnpj(cnpj: string | null): string {
  if (!cnpj || cnpj.length !== 14) return cnpj || "—"
  return `${cnpj.slice(0, 2)}.${cnpj.slice(2, 5)}.${cnpj.slice(5, 8)}/${cnpj.slice(8, 12)}-${cnpj.slice(12, 14)}`
}

// ============================================================================
// Aba Pendentes
// ============================================================================

function PendentesTab() {
  const [pendentes, setPendentes] = useState<DocumentoPendente[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Seleção múltipla
  const [selectedChaves, setSelectedChaves] = useState<Set<string>>(new Set())

  // Modal de aplicar manifestação
  const [modalOpen, setModalOpen] = useState(false)
  const [modalEvento, setModalEvento] = useState<TipoEventoDefinitivo>("210200")
  const [modalJustificativa, setModalJustificativa] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [batchResult, setBatchResult] = useState<BatchResponse | null>(null)

  const loadPendentes = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await apiFetch<DocumentoPendente[]>(
        `/manifestacao/pendentes?status=ciencia`,
      )
      setPendentes(Array.isArray(res) ? res : [])
      setSelectedChaves(new Set())
    } catch (e) {
      console.error("[DFeAxis] pendentes error:", e)
      setError(
        e instanceof Error ? e.message : "Falha ao carregar pendentes",
      )
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadPendentes()
  }, [loadPendentes])

  // Seleção
  const toggleChave = (chave: string) => {
    const copy = new Set(selectedChaves)
    if (copy.has(chave)) copy.delete(chave)
    else copy.add(chave)
    setSelectedChaves(copy)
  }

  const toggleAll = () => {
    if (selectedChaves.size === pendentes.length) {
      setSelectedChaves(new Set())
    } else {
      setSelectedChaves(new Set(pendentes.map((p) => p.chave)))
    }
  }

  const eventoConfig = EVENTO_DEFINITIVO_OPTIONS.find(
    (o) => o.value === modalEvento,
  )!

  const canSubmit = useMemo(() => {
    if (selectedChaves.size === 0) return false
    if (
      eventoConfig.requiresJustification &&
      modalJustificativa.trim().length < 15
    ) {
      return false
    }
    return true
  }, [selectedChaves.size, eventoConfig, modalJustificativa])

  const applyBatch = async () => {
    setSubmitting(true)
    setBatchResult(null)
    try {
      const res = await apiFetch<BatchResponse>("/manifestacao/batch", {
        method: "POST",
        body: JSON.stringify({
          chaves: Array.from(selectedChaves),
          tipo_evento: modalEvento,
          justificativa: modalJustificativa.trim(),
        }),
      })
      setBatchResult(res)
      if (res.sucesso > 0) {
        await loadPendentes()
      }
    } catch (e) {
      setBatchResult({
        total: selectedChaves.size,
        sucesso: 0,
        erro: selectedChaves.size,
        resultados: [],
      })
      console.error("[DFeAxis] batch manifestar error:", e)
    } finally {
      setSubmitting(false)
    }
  }

  const closeModal = () => {
    if (submitting) return
    setModalOpen(false)
    setTimeout(() => {
      setModalJustificativa("")
      setBatchResult(null)
    }, 200)
  }

  return (
    <div className="space-y-4">
      {/* Disclaimer */}
      <Card className="border-amber-500/30 bg-amber-50/50 dark:bg-amber-950/20">
        <CardContent className="pt-4 pb-4">
          <div className="flex gap-3">
            <AlertTriangle className="size-5 text-amber-700 dark:text-amber-300 shrink-0 mt-0.5" />
            <div className="text-xs text-amber-900 dark:text-amber-100 leading-relaxed">
              <strong>Responsabilidade do cliente.</strong> A decisão de
              confirmar, desconhecer ou declarar operação não realizada é sua.
              O DFeAxis apenas transmite o evento à SEFAZ em seu nome. Revise
              os documentos antes de aplicar a manifestação em lote.
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <CardTitle className="text-base">
                NF-e aguardando manifestação definitiva
              </CardTitle>
              <CardDescription>
                Ciência já foi enviada à SEFAZ. Selecione os documentos e
                aplique <strong>Confirmar</strong>, <strong>Desconhecer</strong> ou{" "}
                <strong>Operação não Realizada</strong>.
              </CardDescription>
            </div>
            {selectedChaves.size > 0 && (
              <Button
                onClick={() => setModalOpen(true)}
                className="gap-2"
                size="sm"
              >
                <Send className="size-4" />
                Manifestar {selectedChaves.size} selecionada
                {selectedChaves.size === 1 ? "" : "s"}
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent className="px-0">
          {error ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <p className="text-sm text-destructive font-medium">{error}</p>
              <Button
                variant="outline"
                size="sm"
                onClick={loadPendentes}
                className="mt-3"
              >
                Tentar novamente
              </Button>
            </div>
          ) : loading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="size-6 animate-spin text-muted-foreground" />
            </div>
          ) : pendentes.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center px-4">
              <CheckCircle2 className="size-12 text-emerald-500/60 mb-3" />
              <p className="text-sm text-muted-foreground">
                Nenhuma NF-e aguardando manifestação definitiva no momento.
              </p>
              <p className="text-xs text-muted-foreground mt-1 max-w-md">
                As NF-e aparecem aqui após a ciência automática ser aceita pela
                SEFAZ. Você tem até 180 dias após a emissão para confirmar,
                desconhecer ou declarar não realizada.
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="pl-4 w-10">
                    <input
                      type="checkbox"
                      className="size-4 rounded border-input"
                      checked={
                        selectedChaves.size === pendentes.length &&
                        pendentes.length > 0
                      }
                      onChange={toggleAll}
                      aria-label="Selecionar todos"
                    />
                  </TableHead>
                  <TableHead>Fornecedor</TableHead>
                  <TableHead>NF-e</TableHead>
                  <TableHead>Emissão</TableHead>
                  <TableHead>Valor</TableHead>
                  <TableHead className="pr-4">Chave</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {pendentes.map((doc) => {
                  const checked = selectedChaves.has(doc.chave)
                  return (
                    <TableRow
                      key={doc.chave}
                      className={cn(
                        "group cursor-pointer",
                        checked && "bg-primary/5",
                      )}
                      onClick={() => toggleChave(doc.chave)}
                    >
                      <TableCell className="pl-4">
                        <input
                          type="checkbox"
                          className="size-4 rounded border-input"
                          checked={checked}
                          onChange={() => toggleChave(doc.chave)}
                          onClick={(e) => e.stopPropagation()}
                          aria-label={`Selecionar NF-e ${doc.numero_documento}`}
                        />
                      </TableCell>
                      <TableCell>
                        <div>
                          <p className="text-sm font-medium">
                            {doc.razao_social_emitente || "—"}
                          </p>
                          <p className="text-[10px] font-mono text-muted-foreground">
                            {formatCnpj(doc.cnpj_emitente)}
                          </p>
                        </div>
                      </TableCell>
                      <TableCell className="text-sm">
                        {doc.numero_documento || "—"}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {doc.data_emissao
                          ? new Date(doc.data_emissao).toLocaleDateString(
                              "pt-BR",
                            )
                          : "—"}
                      </TableCell>
                      <TableCell className="text-sm font-medium">
                        {formatCurrency(doc.valor_total)}
                      </TableCell>
                      <TableCell className="font-mono text-[10px] text-muted-foreground pr-4">
                        {doc.chave.slice(0, 14)}...{doc.chave.slice(-6)}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Modal de confirmação */}
      <Dialog open={modalOpen} onOpenChange={(open) => !open && closeModal()}>
        <DialogContent className="max-w-lg">
          {!batchResult ? (
            <>
              <DialogHeader>
                <DialogTitle>Aplicar manifestação em lote</DialogTitle>
                <DialogDescription>
                  {selectedChaves.size} NF-e{" "}
                  {selectedChaves.size === 1 ? "selecionada" : "selecionadas"}.
                  Escolha o tipo de evento e confirme.
                </DialogDescription>
              </DialogHeader>

              <div className="space-y-4">
                {/* Dropdown de evento */}
                <div className="space-y-2">
                  <label className="text-sm font-medium">
                    Tipo de manifestação
                  </label>
                  <div className="grid gap-2">
                    {EVENTO_DEFINITIVO_OPTIONS.map((opt) => (
                      <label
                        key={opt.value}
                        className={cn(
                          "flex items-start gap-3 rounded-lg border p-3 cursor-pointer transition-colors",
                          modalEvento === opt.value
                            ? "border-primary bg-primary/5"
                            : "hover:bg-muted/50",
                        )}
                      >
                        <input
                          type="radio"
                          name="tipo_evento"
                          value={opt.value}
                          checked={modalEvento === opt.value}
                          onChange={() => setModalEvento(opt.value)}
                          className="mt-0.5"
                        />
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium">
                              {opt.label}
                            </span>
                            <Badge
                              variant="outline"
                              className="text-[10px] font-mono"
                            >
                              {opt.value}
                            </Badge>
                          </div>
                          <p className="text-xs text-muted-foreground mt-1">
                            {opt.description}
                          </p>
                        </div>
                      </label>
                    ))}
                  </div>
                </div>

                {/* Justificativa (obrigatória pra 210220/210240) */}
                {eventoConfig.requiresJustification && (
                  <div className="space-y-2">
                    <label className="text-sm font-medium">
                      Justificativa{" "}
                      <span className="text-destructive">*</span>
                      <span className="text-xs font-normal text-muted-foreground ml-2">
                        (mínimo 15 caracteres)
                      </span>
                    </label>
                    <textarea
                      className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm min-h-[80px] resize-none"
                      placeholder="Explique o motivo (ex: mercadoria não foi entregue, nota emitida indevidamente...)"
                      maxLength={255}
                      value={modalJustificativa}
                      onChange={(e) => setModalJustificativa(e.target.value)}
                    />
                    <p className="text-[10px] text-muted-foreground">
                      {modalJustificativa.trim().length} / 255
                    </p>
                  </div>
                )}

                {/* Aviso final */}
                <div className="rounded-lg bg-amber-50 border border-amber-200 p-3 dark:bg-amber-950/30 dark:border-amber-800">
                  <p className="text-xs text-amber-900 dark:text-amber-100">
                    <strong>Confirmação:</strong> esta ação será enviada à
                    SEFAZ e não pode ser revertida. Total de{" "}
                    <strong>{selectedChaves.size}</strong> NF-e será{" "}
                    <strong>{eventoConfig.label.toLowerCase()}</strong>.
                  </p>
                </div>
              </div>

              <DialogFooter>
                <Button
                  variant="outline"
                  onClick={closeModal}
                  disabled={submitting}
                >
                  Cancelar
                </Button>
                <Button
                  onClick={applyBatch}
                  disabled={!canSubmit || submitting}
                  className="gap-2"
                >
                  {submitting ? (
                    <>
                      <Loader2 className="size-4 animate-spin" />
                      Enviando...
                    </>
                  ) : (
                    <>
                      <Send className="size-4" />
                      Confirmar envio
                    </>
                  )}
                </Button>
              </DialogFooter>
            </>
          ) : (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2">
                  {batchResult.erro === 0 ? (
                    <>
                      <CheckCircle2 className="size-5 text-emerald-600" />
                      Manifestação enviada com sucesso
                    </>
                  ) : batchResult.sucesso === 0 ? (
                    <>
                      <AlertTriangle className="size-5 text-destructive" />
                      Nenhuma NF-e foi manifestada
                    </>
                  ) : (
                    <>
                      <AlertTriangle className="size-5 text-amber-600" />
                      Resultado parcial
                    </>
                  )}
                </DialogTitle>
                <DialogDescription>
                  {batchResult.sucesso} de {batchResult.total} NF-e enviadas
                  com sucesso. {batchResult.erro > 0 && `${batchResult.erro} falharam.`}
                </DialogDescription>
              </DialogHeader>
              {batchResult.resultados.some((r) => !r.success) && (
                <div className="max-h-[200px] overflow-y-auto space-y-1 text-xs">
                  {batchResult.resultados
                    .filter((r) => !r.success)
                    .map((r) => (
                      <div
                        key={r.chave_acesso}
                        className="rounded border border-red-200 bg-red-50 p-2 dark:bg-red-950/20 dark:border-red-800"
                      >
                        <p className="font-mono text-[10px] text-red-900 dark:text-red-200">
                          {r.chave_acesso.slice(0, 14)}...{r.chave_acesso.slice(-6)}
                        </p>
                        <p className="text-red-800 dark:text-red-300 mt-0.5">
                          cStat {r.cstat}: {r.xmotivo}
                        </p>
                      </div>
                    ))}
                </div>
              )}
              <DialogFooter>
                <Button onClick={closeModal}>Fechar</Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ============================================================================
// Aba Histórico
// ============================================================================

function HistoricoTab() {
  const [events, setEvents] = useState<ManifestacaoEvent[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [filterChave, setFilterChave] = useState("")
  const [filterTipo, setFilterTipo] = useState<TipoEventoFiltro>("")
  const [limit] = useState(100)

  const [currentPage, setCurrentPage] = useState(1)
  const itemsPerPage = 20

  const chaveTrimmed = filterChave.trim()
  const chaveInvalida = chaveTrimmed.length > 0 && chaveTrimmed.length !== 44

  const loadHistory = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      if (chaveTrimmed.length === 44) params.set("chave_acesso", chaveTrimmed)
      if (filterTipo) params.set("tipo_evento", filterTipo)
      params.set("limit", String(limit))

      const res = await apiFetch<HistoricoResponse>(
        `/manifestacao/historico?${params.toString()}`,
      )
      setEvents(res.events || [])
      setTotal(res.total || 0)
      setCurrentPage(1)
    } catch (e) {
      console.error("[DFeAxis] historico manifestacao error:", e)
      setError(
        e instanceof Error ? e.message : "Falha ao carregar histórico",
      )
    } finally {
      setLoading(false)
    }
  }, [chaveTrimmed, filterTipo, limit])

  useEffect(() => {
    loadHistory()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="space-y-4">
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
                onChange={(e) =>
                  setFilterChave(e.target.value.replace(/\D/g, ""))
                }
                className={cn(
                  "pl-9 font-mono text-xs",
                  chaveInvalida &&
                    "border-amber-500 focus-visible:ring-amber-500",
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
              onChange={(e) => setFilterTipo(e.target.value as TipoEventoFiltro)}
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
              {loading ? <Loader2 className="size-4 animate-spin" /> : "Buscar"}
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
                Eventos aparecem aqui conforme você captura documentos (ciência
                automática) ou envia manifestos manualmente.
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
                {events
                  .slice(
                    (currentPage - 1) * itemsPerPage,
                    currentPage * itemsPerPage,
                  )
                  .map((ev, i) => {
                    const eventMeta = TIPO_EVENTO_LABELS[ev.tipo_evento] || {
                      label: ev.tipo_evento,
                      color: "bg-gray-50 text-gray-700 ring-gray-600/20",
                    }
                    const success = isSefazSuccess(ev.cstat)
                    return (
                      <TableRow
                        key={`${ev.chave_acesso}-${ev.created_at}-${i}`}
                        className="group"
                      >
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
                                eventMeta.color,
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
                          {ev.chave_acesso.slice(0, 14)}...
                          {ev.chave_acesso.slice(-6)}
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
                                  : "bg-red-50 text-red-700 ring-red-600/20",
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

// ============================================================================
// Página principal
// ============================================================================

export default function ManifestacaoPage() {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold flex items-center gap-2">
            <FileCheck className="size-6 text-primary" />
            Manifestação
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Aprove, desconheça ou declare operação não realizada das NF-e
            cientificadas automaticamente pelo DFeAxis.
          </p>
        </div>
      </div>

      <Tabs defaultValue="pendentes">
        <TabsList>
          <TabsTrigger value="pendentes">Pendentes</TabsTrigger>
          <TabsTrigger value="historico">Histórico</TabsTrigger>
        </TabsList>
        <TabsContent value="pendentes" className="mt-4">
          <PendentesTab />
        </TabsContent>
        <TabsContent value="historico" className="mt-4">
          <HistoricoTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}
