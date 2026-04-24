"use client"

import { useState, useEffect, useCallback, useMemo } from "react"
import {
  FileText,
  Truck,
  FileCheck,
  Receipt,
  Building2,
  CalendarDays,
  ChevronDown,
  Loader2,
  Gauge,
} from "lucide-react"
import { StatCard } from "@/components/dashboard/stat-card"
import { FinancialCard } from "@/components/dashboard/financial-card"
import { VolumeChart } from "@/components/dashboard/volume-chart"
import { RecentDocuments } from "@/components/dashboard/recent-documents"
import { TrialCounter } from "@/components/trial-counter"
import { EnvToggle } from "@/components/env-toggle"
import { PendentesPanel } from "@/components/pendentes-panel"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { useSettings } from "@/hooks/use-settings"
import { useTrial } from "@/hooks/use-trial"
import { useMonthlyUsage } from "@/hooks/use-monthly-usage"
import { getSupabase } from "@/lib/supabase"
import { listPlans, type Plan } from "@/lib/billing"
import {
  buildCompetenciaOptions,
  currentCompetencia,
  getCompetenciaRange,
  formatCompetenciaLabel,
  COMPETENCIA_TODOS,
  type CompetenciaId,
} from "@/lib/competencia"

interface DashboardCounts {
  nfe: number
  cte: number
  cteos: number
  mdfe: number
  nfse: number
}

interface ActivityEntry {
  id: string
  tipo: string
  cnpj: string
  status: string
  docs_found: number
  created_at: string
}

export default function DashboardPage() {
  const { settings } = useSettings()
  const showMock = settings.showMockData
  const { trialActive, subscriptionStatus, docsConsumidos: trialDocsConsumidos, trialCap } = useTrial()
  const showTrialCounter = subscriptionStatus !== "active" && trialActive
  const showUsageCard = subscriptionStatus === "active"
  const isTrial = subscriptionStatus === "trial"

  // Competência (mês calendário) selecionada — default = mês atual.
  // O filtro é aplicado em TODAS as queries do dashboard (stats, documentos
  // recentes, volume chart, totais financeiros). Dropdown mostra até 12
  // meses pra trás.
  const [selectedCompetencia, setSelectedCompetencia] = useState<CompetenciaId>(
    currentCompetencia()
  )
  // Dynamic competencia options — fetched from actual document data
  const [competenciaOptions, setCompetenciaOptions] = useState<
    import("@/lib/competencia").CompetenciaRange[]
  >([])

  useEffect(() => {
    async function fetchDistinctMonths() {
      try {
        const sb = getSupabase()
        // Fetch data_emissao (preferred) and fetched_at (fallback) for month list
        const { data, error } = await sb
          .from("documents")
          .select("data_emissao, fetched_at")
        if (error || !data) {
          setCompetenciaOptions(buildCompetenciaOptions(11))
          return
        }
        // Collect unique YYYY-MM from data_emissao (emission date, not capture)
        const monthSet = new Set<string>()
        for (const row of data) {
          const dateStr = row.data_emissao || row.fetched_at
          if (dateStr) {
            const d = new Date(dateStr)
            const sp = new Date(d.getTime() - 3 * 60 * 60 * 1000)
            const id = `${sp.getUTCFullYear()}-${String(sp.getUTCMonth() + 1).padStart(2, "0")}`
            monthSet.add(id)
          }
        }
        if (monthSet.size === 0) {
          // No documents at all — show current month
          setCompetenciaOptions([getCompetenciaRange(currentCompetencia())])
          return
        }
        // Sort descending (newest first), limit to 12 most recent
        const sorted = Array.from(monthSet).sort((a, b) => b.localeCompare(a))
        const recent = sorted.slice(0, 12)
        const older = sorted.slice(12)
        const options = recent.map((id) => getCompetenciaRange(id))
        // If there are older months, add them as a separate group
        if (older.length > 0) {
          for (const id of older) {
            options.push({ ...getCompetenciaRange(id), _older: true } as any)
          }
        }
        setCompetenciaOptions(options)
      } catch {
        setCompetenciaOptions(buildCompetenciaOptions(11))
      }
    }
    fetchDistinctMonths()
  }, [])
  const isAllCompetencia = selectedCompetencia === COMPETENCIA_TODOS
  const currentRange = useMemo(
    () => isAllCompetencia ? null : getCompetenciaRange(selectedCompetencia),
    [selectedCompetencia, isAllCompetencia]
  )

  // Ambiente filter — documents don't have an ambiente column, so when
  // Producao is selected we show an empty state (no prod docs exist yet).
  const sefazAmbiente = settings.sefazAmbiente // "1" = prod, "2" = hom
  const isProd = sefazAmbiente === "1"

  // Monthly usage — always load so "Uso do mês" card works for both trial and active
  const { docsConsumidosMes, docsIncludedMes, stripePriceId, syncError: planSyncError } = useMonthlyUsage(true)

  // Plans (used to resolve overage rate for the current subscription).
  const [plansList, setPlansList] = useState<Plan[]>([])
  useEffect(() => {
    if (!showUsageCard) return
    listPlans()
      .then(setPlansList)
      .catch(() => setPlansList([]))
  }, [showUsageCard])

  const currentPlan = plansList.find(
    (p) => p.price_id_monthly === stripePriceId || p.price_id_yearly === stripePriceId
  )
  const overageCentsPerDoc = currentPlan?.overage_cents_per_doc ?? 0
  const usagePct = docsIncludedMes > 0
    ? Math.min(100, Math.round((docsConsumidosMes / docsIncludedMes) * 100))
    : 0
  const overageDocs = Math.max(0, docsConsumidosMes - docsIncludedMes)
  const overageCents = overageDocs * overageCentsPerDoc
  const overageBRL = (overageCents / 100).toLocaleString("pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })

  const [realCompanyName, setRealCompanyName] = useState("")
  const [realCounts, setRealCounts] = useState<DashboardCounts>({ nfe: 0, cte: 0, cteos: 0, mdfe: 0, nfse: 0 })
  const [realActivity, setRealActivity] = useState<ActivityEntry[]>([])
  // realCredits removed — legacy MercadoPago system replaced by Stripe plan usage
  const [realDocuments, setRealDocuments] = useState<Array<{
    tipo: string
    chave_acesso: string
    cnpj: string
    nsu: string
    status: string
    fetched_at: string
    cnpj_emitente?: string | null
    razao_social_emitente?: string | null
    numero_documento?: string | null
    data_emissao?: string | null
    valor_total?: number | null
    is_resumo?: boolean | null
    manifestacao_status?: string | null
  }>>([])
  const [realNfeTotal, setRealNfeTotal] = useState(0)
  const [realCteTotal, setRealCteTotal] = useState(0)
  const [realCteosTotal, setRealCteosTotal] = useState(0)
  const [realMdfeTotal, setRealMdfeTotal] = useState(0)
  const [realNfseTotal, setRealNfseTotal] = useState(0)
  const [realCnpjCount, setRealCnpjCount] = useState(0)
  const [realVolumeData, setRealVolumeData] = useState<Array<{ date: string; nfe: number; cte: number; cteos: number; mdfe: number; nfse: number }>>([])
  const [realLoading, setRealLoading] = useState(false)
  // Total agregado de docs capturados na competência selecionada (NFE+CTE+CTEOS+MDFE+NFSE).
  // É a base pra cálculo de consumo mensal e overage.
  const [realDocsNaCompetencia, setRealDocsNaCompetencia] = useState(0)

  // Extract value from XML string using regex (no DOM parser needed)
  function extractXmlValue(xml: string, tipo: string): number {
    if (!xml) return 0
    try {
      if (tipo === "NFE") {
        const match = xml.match(/<vNF>([\d.,]+)<\/vNF>/)
        return match ? parseFloat(match[1].replace(",", ".")) : 0
      } else if (tipo === "CTE" || tipo === "CTEOS") {
        const match = xml.match(/<vTPrest>([\d.,]+)<\/vTPrest>/)
        return match ? parseFloat(match[1].replace(",", ".")) : 0
      } else if (tipo === "MDFE") {
        const match = xml.match(/<vCarga>([\d.,]+)<\/vCarga>/)
        return match ? parseFloat(match[1].replace(",", ".")) : 0
      } else if (tipo === "NFSE") {
        const match = xml.match(/<ValorServicos>([\d.,]+)<\/ValorServicos>/)
        return match ? parseFloat(match[1].replace(",", ".")) : 0
      }
    } catch { /* ignore */ }
    return 0
  }

  const loadRealData = useCallback(async () => {
    // When Producao is selected, documents don't have an ambiente column
    // so we show empty state — skip all queries.
    if (isProd) {
      setRealCounts({ nfe: 0, cte: 0, cteos: 0, mdfe: 0, nfse: 0 })
      setRealDocsNaCompetencia(0)
      setRealDocuments([])
      setRealNfeTotal(0)
      setRealCteTotal(0)
      setRealCteosTotal(0)
      setRealMdfeTotal(0)
      setRealNfseTotal(0)
      setRealVolumeData([])
      setRealActivity([])
      // Still load company name & CNPJ count (atemporal)
      const sb = getSupabase()
      const { data: certData } = await sb
        .from('certificates')
        .select('cnpj, company_name')
        .eq('is_active', true)
      setRealCnpjCount(certData?.length ?? 0)
      if (certData && certData.length > 0 && certData[0].company_name) {
        const name = certData[0].company_name.split(':')[0].trim()
        setRealCompanyName(name)
      }
      return
    }

    setRealLoading(true)
    try {
      const sb = getSupabase()

      // Helper to apply optional date range filter based on data_emissao
      // (emission date, not capture date — matches fiscal competency period).
      // Falls back to fetched_at for docs without data_emissao populated.
      // When "Todos" is selected (currentRange === null), no date filter is applied.
      function applyDateFilter<T extends { gte: (col: string, val: string) => T; lte: (col: string, val: string) => T; or: (filter: string) => T }>(query: T): T {
        if (currentRange) {
          // Use data_emissao when available, fallback to fetched_at for old docs
          return query.or(`and(data_emissao.gte.${currentRange.start},data_emissao.lte.${currentRange.end}),and(data_emissao.is.null,fetched_at.gte.${currentRange.start},fetched_at.lte.${currentRange.end})`)
        }
        return query
      }

      // Counts por tipo — documentos capturados na competência (ou todos se "Todos")
      const [nfeRes, cteRes, cteosRes, mdfeRes, nfseRes] = await Promise.all([
        applyDateFilter(
          sb.from('documents').select('id', { count: 'exact', head: true }).eq('tipo', 'NFE')
        ),
        applyDateFilter(
          sb.from('documents').select('id', { count: 'exact', head: true }).eq('tipo', 'CTE')
        ),
        applyDateFilter(
          sb.from('documents').select('id', { count: 'exact', head: true }).eq('tipo', 'CTEOS')
        ),
        applyDateFilter(
          sb.from('documents').select('id', { count: 'exact', head: true }).eq('tipo', 'MDFE')
        ),
        applyDateFilter(
          sb.from('documents').select('id', { count: 'exact', head: true }).eq('tipo', 'NFSE')
        ),
      ])

      // CNPJs + nome da empresa (atemporal — não depende de competência)
      const { data: certData } = await sb
        .from('certificates')
        .select('cnpj, company_name')
        .eq('is_active', true)
      setRealCnpjCount(certData?.length ?? 0)
      if (certData && certData.length > 0 && certData[0].company_name) {
        const name = certData[0].company_name.split(':')[0].trim()
        setRealCompanyName(name)
      }

      setRealCounts({
        nfe: nfeRes.count ?? 0,
        cte: cteRes.count ?? 0,
        cteos: cteosRes.count ?? 0,
        mdfe: mdfeRes.count ?? 0,
        nfse: nfseRes.count ?? 0,
      })

      // Total consolidado dos 5 tipos pra o card "Uso do mês" — é assim
      // que o contador de cobrança funciona: um único número que zera
      // dia 1 e serve de base pro cálculo de excedente (overage).
      const totalCompetencia =
        (nfeRes.count ?? 0) +
        (cteRes.count ?? 0) +
        (cteosRes.count ?? 0) +
        (mdfeRes.count ?? 0) +
        (nfseRes.count ?? 0)
      setRealDocsNaCompetencia(totalCompetencia)

      // Estratégia de duas queries:
      //
      // Query A (displayDocs, limit 20): os 20 docs mais recentes pra
      //   mostrar na tabela "Documentos Recentes" do dashboard.
      //
      // Query B (aggregationRows, sem limit, só colunas leves): TODOS
      //   os documents da competência (tipo + valor_total + fetched_at)
      //   pra soma de valores e volume chart refletirem o total real,
      //   não só os 20 exibidos. Como o xml_content não vem, o payload
      //   continua leve mesmo com milhares de rows.
      //
      // Nota de tipagem: o schema do Supabase TypeScript gerado pode não
      // conhecer as colunas da migration 015 ainda, então fazemos cast
      // explícito. Em runtime as colunas já existem.
      type RecentDocRow = {
        tipo: string
        chave_acesso: string
        cnpj: string
        nsu: string
        status: string
        fetched_at: string
        xml_content?: string | null
        cnpj_emitente?: string | null
        razao_social_emitente?: string | null
        numero_documento?: string | null
        data_emissao?: string | null
        valor_total?: number | null
        is_resumo?: boolean | null
        manifestacao_status?: string | null
      }
      type AggregationRow = {
        tipo: string
        fetched_at: string
        data_emissao: string | null
        valor_total: number | null
        xml_content: string | null
      }

      const [displayRes, aggregationRes] = await Promise.all([
        applyDateFilter(
          sb
            .from('documents')
            .select(
              'tipo, chave_acesso, cnpj, nsu, status, fetched_at, xml_content, ' +
              'cnpj_emitente, razao_social_emitente, numero_documento, data_emissao, valor_total, ' +
              'is_resumo, manifestacao_status'
            )
        )
          .order('fetched_at', { ascending: false })
          .limit(20) as unknown as Promise<{ data: RecentDocRow[] | null }>,
        applyDateFilter(
          sb
            .from('documents')
            .select('tipo, fetched_at, data_emissao, valor_total, xml_content')
        ) as unknown as Promise<{ data: AggregationRow[] | null }>,
      ])

      const displayDocs = displayRes.data ?? []
      const aggregationRows = aggregationRes.data ?? []

      setRealDocuments(displayDocs)

      // Soma total sobre TODOS os documents da competência (não só
      // os 20 exibidos). Usa valor_total (coluna nova do parser) com
      // fallback pra extração via regex pro xml_content dos docs antigos
      // pré-backfill.
      let nfeSum = 0, cteSum = 0, cteosSum = 0, mdfeSum = 0, nfseSum = 0
      for (const doc of aggregationRows) {
        const val =
          doc.valor_total != null
            ? Number(doc.valor_total)
            : extractXmlValue(doc.xml_content || "", doc.tipo)
        if (doc.tipo === "NFE") nfeSum += val
        if (doc.tipo === "CTE") cteSum += val
        if (doc.tipo === "CTEOS") cteosSum += val
        if (doc.tipo === "MDFE") mdfeSum += val
        if (doc.tipo === "NFSE") nfseSum += val
      }
      setRealNfeTotal(nfeSum)
      setRealCteTotal(cteSum)
      setRealCteosTotal(cteosSum)
      setRealMdfeTotal(mdfeSum)
      setRealNfseTotal(nfseSum)

      // Volume chart agrupado por dia sobre TODOS os documents da competência
      const byDay: Record<string, { nfe: number; cte: number; cteos: number; mdfe: number; nfse: number }> = {}
      for (const doc of aggregationRows) {
        const dateStr = doc.data_emissao || doc.fetched_at
        const day = new Date(dateStr).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })
        if (!byDay[day]) byDay[day] = { nfe: 0, cte: 0, cteos: 0, mdfe: 0, nfse: 0 }
        const key = doc.tipo.toLowerCase() as "nfe" | "cte" | "cteos" | "mdfe" | "nfse"
        if (key in byDay[day]) byDay[day][key]++
      }
      const volumeData = Object.entries(byDay)
        .map(([date, counts]) => ({ date, ...counts }))
        .sort((a, b) => {
          // Ordena por data DD/MM (pt-BR) convertendo pra comparable
          const [da, ma] = a.date.split("/").map(Number)
          const [db, mb] = b.date.split("/").map(Number)
          return (ma ?? 0) - (mb ?? 0) || (da ?? 0) - (db ?? 0)
        })
      setRealVolumeData(volumeData)

      // Polling log — últimos 5 (atemporal, feed de atividade recente)
      const { data: activityData } = await sb
        .from('polling_log')
        .select('id, tipo, cnpj, status, docs_found, created_at')
        .order('created_at', { ascending: false })
        .limit(5)

      if (activityData) setRealActivity(activityData)

      // Legacy credits query removed — billing now uses Stripe plan limits
    } catch (e) {
      console.error("[DFeAxis] Error loading dashboard data:", e)
    } finally {
      setRealLoading(false)
    }
  }, [currentRange, isProd])

  useEffect(() => {
    if (!settings.showMockData) loadRealData()
  }, [settings.showMockData, loadRealData, sefazAmbiente])

  // Label da competência atual pra exibir no dashboard
  const periodoAtual = isAllCompetencia ? "Todos" : currentRange!.shortLabel

  const nfeValue = showMock ? "1.247" : realCounts.nfe.toLocaleString("pt-BR")
  const cteValue = showMock ? "384" : realCounts.cte.toLocaleString("pt-BR")
  const mdfeValue = showMock ? "56" : realCounts.mdfe.toLocaleString("pt-BR")
  const nfseValue = showMock ? "12" : realCounts.nfse.toLocaleString("pt-BR")
  const allFinancialTotal = realNfeTotal + realCteTotal + realCteosTotal + realMdfeTotal + realNfseTotal

  if (!showMock && realLoading) {
    return (
      <div className="flex items-center justify-center py-32">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="size-8 animate-spin text-muted-foreground" />
          <p className="text-sm text-muted-foreground">Carregando dados...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {/* Banner: plano sem sincronização com Stripe — evita exibir valores
          hardcoded (fallback antigo PLAN_DEFAULTS causava risco de cobranca
          com limite errado se o webhook falhasse ou plano mudasse). */}
      {planSyncError && !showMock && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-200">
          <strong>Sincronizando com Stripe…</strong> o limite de documentos do
          seu plano ainda não foi recebido do gateway. Se o aviso persistir,
          contate o suporte — não exibimos valor estimado pra não induzir
          cobrança incorreta.
        </div>
      )}

      {/* Top controls */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-xs text-muted-foreground">
            Visão geral dos documentos recebidos
          </p>
        </div>
        <div className="flex items-center gap-2">
          <EnvToggle />
          <button className="inline-flex items-center gap-2 rounded-lg border bg-background px-2.5 py-1.5 text-xs font-medium shadow-sm transition-colors hover:bg-muted">
            <Building2 className="h-3.5 w-3.5 text-muted-foreground" />
            <span>{showMock ? "Tech Solutions Ltda" : (realCompanyName || "Empresa")}</span>
            <ChevronDown className="h-3 w-3 text-muted-foreground" />
          </button>
          <label
            htmlFor="competencia-select"
            className="relative inline-flex items-center gap-2 rounded-lg border bg-background px-2.5 py-1.5 text-xs font-medium shadow-sm transition-colors hover:bg-muted cursor-pointer"
          >
            <CalendarDays className="h-3.5 w-3.5 text-muted-foreground" />
            <span>{periodoAtual}</span>
            <ChevronDown className="h-3 w-3 text-muted-foreground" />
            <select
              id="competencia-select"
              aria-label="Selecionar competência mensal"
              value={selectedCompetencia}
              onChange={(e) =>
                setSelectedCompetencia(e.target.value as CompetenciaId)
              }
              className="absolute inset-0 cursor-pointer opacity-0"
            >
              <option value={COMPETENCIA_TODOS}>Todos</option>
              {competenciaOptions.filter((o: any) => !o._older).map((opt) => (
                <option key={opt.id} value={opt.id}>
                  {opt.shortLabel}
                </option>
              ))}
              {competenciaOptions.some((o: any) => o._older) && (
                <option disabled>── Período anterior ──</option>
              )}
              {competenciaOptions.filter((o: any) => o._older).map((opt) => (
                <option key={opt.id} value={opt.id}>
                  {opt.shortLabel}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {/* Trial counter */}
      {showTrialCounter && <TrialCounter />}

      {/* Pendentes panel (quando aplicável) */}
      <PendentesPanel />

      {/* Empty state for Producao — documents don't have an ambiente column */}
      {isProd && !showMock && (
        <Card size="sm">
          <CardContent className="py-8 text-center">
            <p className="text-sm font-medium text-muted-foreground">
              Nenhum documento capturado em produção
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              Alterne para Homologação para visualizar os documentos capturados durante os testes.
            </p>
          </CardContent>
        </Card>
      )}

      {/* Stat cards — all in one row */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
        <StatCard
          title="NF-e"
          value={nfeValue}
          icon={<FileText className="h-4 w-4" />}
          period={`Competência ${periodoAtual}`}
          trend={showMock ? { value: 12.5, label: "vs. mês anterior" } : undefined}
          color="text-blue-600"
        />
        <StatCard
          title="CT-e"
          value={cteValue}
          icon={<Truck className="h-4 w-4" />}
          period={`Competência ${periodoAtual}`}
          trend={showMock ? { value: 8.3, label: "vs. mês anterior" } : undefined}
          color="text-violet-600"
        />
        <StatCard
          title="MDF-e"
          value={mdfeValue}
          icon={<FileCheck className="h-4 w-4" />}
          period={`Competência ${periodoAtual}`}
          trend={showMock ? { value: -3.2, label: "vs. mês anterior" } : undefined}
          color="text-emerald-600"
        />
        <StatCard
          title="NFS-e"
          value={nfseValue}
          icon={<Receipt className="h-4 w-4" />}
          period={`Competência ${periodoAtual}`}
          trend={showMock ? { value: 4.1, label: "vs. mês anterior" } : undefined}
          badge="ADN"
          color="text-amber-600"
        />
        {!showMock && (
          <>
            <StatCard
              title="CNPJs"
              value={realCnpjCount.toString()}
              icon={<Building2 className="h-4 w-4" />}
              period="Certificados ativos"
              color="text-slate-600"
            />
            {(() => {
              const isActivePlan = subscriptionStatus === "active"
              // Use real doc count from current competencia (more accurate than
              // docs_consumidos_mes which only tracks the billing cycle)
              const realTotal = realCounts.nfe + realCounts.cte + realCounts.cteos + realCounts.mdfe + realCounts.nfse
              const used = isActivePlan
                ? (realTotal > 0 ? realTotal : docsConsumidosMes)
                : (realTotal > 0 ? realTotal : trialDocsConsumidos)
              const limit = isActivePlan ? docsIncludedMes : trialCap
              const pct = limit > 0 ? Math.round((used / limit) * 100) : 0
              const over = Math.max(0, used - limit)
              const overageRate = isActivePlan ? overageCentsPerDoc : 0
              const overCostBRL = over > 0 && overageRate > 0
                ? (over * overageRate / 100).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
                : null
              const barColor = over > 0
                ? "bg-red-500"
                : pct >= 80
                  ? "bg-amber-500"
                  : "bg-emerald-500"
              const barWidth = Math.min(100, Math.max(pct, over > 0 ? 100 : pct))

              return (
                <Card className="relative overflow-hidden transition-shadow hover:shadow-md col-span-2 sm:col-span-1">
                  <CardContent className="pt-1">
                    <div className="space-y-2">
                      <div className="flex items-center gap-2">
                        <span className="text-indigo-600"><Gauge className="h-4 w-4" /></span>
                        <p className="text-sm font-medium text-muted-foreground">Uso do Plano</p>
                      </div>
                      <p className="text-2xl font-bold tracking-tight">
                        {used.toLocaleString("pt-BR")} <span className="text-base font-normal text-muted-foreground">/ {limit.toLocaleString("pt-BR")}</span>
                      </p>
                      <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
                        <div
                          className={`h-full rounded-full transition-all ${barColor}`}
                          style={{ width: `${barWidth}%`, minWidth: used > 0 && barWidth < 4 ? "4px" : undefined }}
                        />
                      </div>
                      {over > 0 ? (
                        <p className="text-xs font-semibold text-red-600">
                          {over.toLocaleString("pt-BR")} documentos excedentes
                          {overCostBRL && ` · ~R$ ${overCostBRL}`}
                        </p>
                      ) : (
                        <p className="text-xs text-muted-foreground">
                          {isTrial
                            ? `${used} de ${limit} documentos (trial)`
                            : "documentos este mês"
                          }
                        </p>
                      )}
                    </div>
                  </CardContent>
                </Card>
              )
            })()}
          </>
        )}
      </div>

      {/* Uso do mês — SEMPRE visível (trial e active). O número mostrado
          vem da contagem real dos documents na competência selecionada,
          não do `docs_consumidos_mes` do tenant — isso permite o usuário
          navegar competências passadas e ver o consumo histórico.
          Pra `subscription_status='active'`, exibe barra de progresso +
          excedente previsto contra o plano contratado. Pra trial, exibe
          contra o trial cap (500 docs) quando aplicável. */}
      {(() => {
        const isActive = subscriptionStatus === "active"
        // Active subscription: docs_included_mes vem do webhook do Stripe.
        // Se == 0 com sub ativa, o hook setou syncError=true — UI mostra
        // aviso "Sincronizando..." em vez de chutar valor (ver card abaixo).
        // Trial: usa trialCap real do tenant.
        const limiteTotal = showMock ? 3000 : (isActive ? docsIncludedMes : trialCap)
        const usoAtual = showMock ? 1791 : realDocsNaCompetencia
        const pctUso = limiteTotal > 0
          ? Math.min(100, Math.round((usoAtual / limiteTotal) * 100))
          : 0
        const excedenteDocs = Math.max(0, usoAtual - limiteTotal)
        const excedenteValorCents = (showMock || isActive) ? excedenteDocs * overageCentsPerDoc : 0
        const excedenteBRL = (excedenteValorCents / 100).toLocaleString("pt-BR", {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        })

        return (
          <Card size="sm">
            <CardHeader>
              <CardTitle>Uso do mês — {periodoAtual}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
                <div
                  className={`h-full rounded-full transition-all ${
                    excedenteDocs > 0
                      ? "bg-red-500"
                      : pctUso >= 80
                        ? "bg-amber-500"
                        : "bg-emerald-500"
                  }`}
                  style={{
                    width: `${Math.max(pctUso, excedenteDocs > 0 ? 100 : pctUso)}%`,
                    minWidth: usoAtual > 0 && pctUso < 4 ? "4px" : undefined,
                  }}
                />
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground">
                  {usoAtual.toLocaleString("pt-BR")} de{" "}
                  {limiteTotal.toLocaleString("pt-BR")} documentos capturados
                  {!showMock && !isActive && " (limite do trial)"}
                </span>
                {excedenteDocs > 0 ? (
                  (showMock || isActive) ? (
                    <span className="font-semibold text-red-600">
                      Excedente previsto: {excedenteDocs.toLocaleString("pt-BR")} docs · R$ {excedenteBRL}
                    </span>
                  ) : (
                    <span className="font-semibold text-red-600">
                      Trial excedido — {excedenteDocs.toLocaleString("pt-BR")} docs acima
                    </span>
                  )
                ) : (
                  <span className="font-semibold text-emerald-600">
                    Dentro do limite
                  </span>
                )}
              </div>
            </CardContent>
          </Card>
        )
      })()}

      {/* Financial + Chart side by side */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        {(() => {
          const allTotal = allFinancialTotal
          const fmt = (v: number) => `R$ ${v.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}`
          return (
            <FinancialCard
              title="Documentos Recebidos"
              icon={<FileText className="h-4 w-4 text-blue-600" />}
              totalLabel="Total Geral"
              totalValue={showMock ? "R$ 2.847.320,45" : fmt(allTotal)}
              period={periodoAtual}
              items={showMock ? [
                { label: "NF-e (1.247)", value: "R$ 2.550.000,00", amount: 2550000, color: "text-blue-600", bgColor: "bg-blue-500" },
                { label: "CT-e (384)", value: "R$ 180.000,00", amount: 180000, color: "text-violet-600", bgColor: "bg-violet-500" },
                { label: "CT-e OS (92)", value: "R$ 75.000,00", amount: 75000, color: "text-fuchsia-600", bgColor: "bg-fuchsia-500" },
                { label: "MDF-e (56)", value: "—", amount: 0, color: "text-emerald-600", bgColor: "bg-emerald-500", hideBar: true },
                { label: "NFS-e (12)", value: "R$ 42.320,45", amount: 42320, color: "text-amber-600", bgColor: "bg-amber-500" },
              ] : [
                ...(realCounts.nfe > 0 ? [{ label: `NF-e (${realCounts.nfe})`, value: realNfeTotal > 0 ? fmt(realNfeTotal) : "aguardando XML", amount: realNfeTotal, color: "text-blue-600", bgColor: "bg-blue-500", hideBar: realNfeTotal === 0 }] : []),
                ...(realCounts.cte > 0 ? [{ label: `CT-e (${realCounts.cte})`, value: realCteTotal > 0 ? fmt(realCteTotal) : "aguardando XML", amount: realCteTotal, color: "text-violet-600", bgColor: "bg-violet-500", hideBar: realCteTotal === 0 }] : []),
                ...(realCounts.cteos > 0 ? [{ label: `CT-e OS (${realCounts.cteos})`, value: realCteosTotal > 0 ? fmt(realCteosTotal) : "aguardando XML", amount: realCteosTotal, color: "text-fuchsia-600", bgColor: "bg-fuchsia-500", hideBar: realCteosTotal === 0 }] : []),
                ...(realCounts.mdfe > 0 ? [{ label: `MDF-e (${realCounts.mdfe})`, value: realMdfeTotal > 0 ? fmt(realMdfeTotal) : "aguardando XML", amount: realMdfeTotal, color: "text-emerald-600", bgColor: "bg-emerald-500", hideBar: realMdfeTotal === 0 }] : []),
                ...(realCounts.nfse > 0 ? [{ label: `NFS-e (${realCounts.nfse})`, value: realNfseTotal > 0 ? fmt(realNfseTotal) : "aguardando XML", amount: realNfseTotal, color: "text-amber-600", bgColor: "bg-amber-500", hideBar: realNfseTotal === 0 }] : []),
              ]}
            />
          )
        })()}
        <VolumeChart empty={false} realData={showMock ? undefined : realVolumeData} competenciaId={isAllCompetencia ? undefined : selectedCompetencia} />
      </div>

      {/* Recent documents */}
      <RecentDocuments empty={showMock ? false : realDocuments.length === 0} documents={showMock ? undefined : realDocuments} />
    </div>
  )
}
