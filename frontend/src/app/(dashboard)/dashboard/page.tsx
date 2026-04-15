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
  type CompetenciaId,
} from "@/lib/competencia"

interface DashboardCounts {
  nfe: number
  cte: number
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
  const { trialActive, subscriptionStatus } = useTrial()
  const showTrialCounter = subscriptionStatus !== "active" && trialActive
  const showUsageCard = subscriptionStatus === "active"

  // Competência (mês calendário) selecionada — default = mês atual.
  // O filtro é aplicado em TODAS as queries do dashboard (stats, documentos
  // recentes, volume chart, totais financeiros). Dropdown mostra até 12
  // meses pra trás.
  const [selectedCompetencia, setSelectedCompetencia] = useState<CompetenciaId>(
    currentCompetencia()
  )
  const competenciaOptions = useMemo(() => buildCompetenciaOptions(11), [])
  const currentRange = useMemo(
    () => getCompetenciaRange(selectedCompetencia),
    [selectedCompetencia]
  )

  // Monthly usage only loads when subscription is active (decoupled from trial state)
  const { docsConsumidosMes, docsIncludedMes, stripePriceId } = useMonthlyUsage(showUsageCard)

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
  const [realCounts, setRealCounts] = useState<DashboardCounts>({ nfe: 0, cte: 0, mdfe: 0, nfse: 0 })
  const [realActivity, setRealActivity] = useState<ActivityEntry[]>([])
  const [realCredits, setRealCredits] = useState<number | null>(null)
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
  }>>([])
  const [realNfeTotal, setRealNfeTotal] = useState(0)
  const [realCteTotal, setRealCteTotal] = useState(0)
  const [realMdfeTotal, setRealMdfeTotal] = useState(0)
  const [realNfseTotal, setRealNfseTotal] = useState(0)
  const [realCnpjCount, setRealCnpjCount] = useState(0)
  const [realVolumeData, setRealVolumeData] = useState<Array<{ date: string; nfe: number; cte: number; mdfe: number; nfse: number }>>([])
  const [realLoading, setRealLoading] = useState(false)
  // Total agregado de docs capturados na competência selecionada (NFE+CTE+MDFE+NFSE).
  // É a base pra cálculo de consumo mensal e overage.
  const [realDocsNaCompetencia, setRealDocsNaCompetencia] = useState(0)

  // Extract value from XML string using regex (no DOM parser needed)
  function extractXmlValue(xml: string, tipo: string): number {
    if (!xml) return 0
    try {
      if (tipo === "NFE") {
        const match = xml.match(/<vNF>([\d.,]+)<\/vNF>/)
        return match ? parseFloat(match[1].replace(",", ".")) : 0
      } else if (tipo === "CTE") {
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
    setRealLoading(true)
    try {
      const sb = getSupabase()
      // Range da competência selecionada (ISO UTC cobrindo o mês SP inteiro)
      const { start, end } = currentRange

      // Counts por tipo — SOMENTE documentos capturados na competência
      const [nfeRes, cteRes, mdfeRes, nfseRes] = await Promise.all([
        sb
          .from('documents')
          .select('id', { count: 'exact', head: true })
          .eq('tipo', 'NFE')
          .gte('fetched_at', start)
          .lte('fetched_at', end),
        sb
          .from('documents')
          .select('id', { count: 'exact', head: true })
          .eq('tipo', 'CTE')
          .gte('fetched_at', start)
          .lte('fetched_at', end),
        sb
          .from('documents')
          .select('id', { count: 'exact', head: true })
          .eq('tipo', 'MDFE')
          .gte('fetched_at', start)
          .lte('fetched_at', end),
        sb
          .from('documents')
          .select('id', { count: 'exact', head: true })
          .eq('tipo', 'NFSE')
          .gte('fetched_at', start)
          .lte('fetched_at', end),
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
        mdfe: mdfeRes.count ?? 0,
        nfse: nfseRes.count ?? 0,
      })

      // Total consolidado dos 4 tipos pra o card "Uso do mês" — é assim
      // que o contador de cobrança funciona: um único número que zera
      // dia 1 e serve de base pro cálculo de excedente (overage).
      const totalCompetencia =
        (nfeRes.count ?? 0) +
        (cteRes.count ?? 0) +
        (mdfeRes.count ?? 0) +
        (nfseRes.count ?? 0)
      setRealDocsNaCompetencia(totalCompetencia)

      // Documentos recentes da competência — até 50 (não "últimos 20")
      // pra a soma de valores refletir a competência completa.
      // Usa as colunas novas de metadata (migration 015) — valor_total e
      // dados do emitente já vêm populados pelo xml_parser.
      //
      // Nota de tipagem: o schema do Supabase TypeScript gerado pode não
      // conhecer as colunas da migration 015 ainda, então fazemos cast
      // explícito pra dict flexível. Em runtime as colunas já existem.
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
      }
      const recentRes = (await sb
        .from('documents')
        .select(
          'tipo, chave_acesso, cnpj, nsu, status, fetched_at, xml_content, ' +
          'cnpj_emitente, razao_social_emitente, numero_documento, data_emissao, valor_total'
        )
        .gte('fetched_at', start)
        .lte('fetched_at', end)
        .order('fetched_at', { ascending: false })
        .limit(50)) as unknown as { data: RecentDocRow[] | null }
      const recentDocs = recentRes.data

      if (recentDocs) {
        setRealDocuments(recentDocs)

        // Soma de valores por tipo usando valor_total (coluna nova do
        // parser). Fallback pra extração via regex no xml_content pra
        // docs antigos que ainda não passaram pelo backfill.
        let nfeSum = 0, cteSum = 0, mdfeSum = 0, nfseSum = 0
        for (const doc of recentDocs) {
          const val =
            doc.valor_total != null
              ? Number(doc.valor_total)
              : extractXmlValue(doc.xml_content || "", doc.tipo)
          if (doc.tipo === "NFE") nfeSum += val
          if (doc.tipo === "CTE") cteSum += val
          if (doc.tipo === "MDFE") mdfeSum += val
          if (doc.tipo === "NFSE") nfseSum += val
        }
        setRealNfeTotal(nfeSum)
        setRealCteTotal(cteSum)
        setRealMdfeTotal(mdfeSum)
        setRealNfseTotal(nfseSum)

        // Volume chart agrupado por dia da competência
        const byDay: Record<string, { nfe: number; cte: number; mdfe: number; nfse: number }> = {}
        for (const doc of recentDocs) {
          const day = new Date(doc.fetched_at).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })
          if (!byDay[day]) byDay[day] = { nfe: 0, cte: 0, mdfe: 0, nfse: 0 }
          const key = doc.tipo.toLowerCase() as "nfe" | "cte" | "mdfe" | "nfse"
          if (key in byDay[day]) byDay[day][key]++
        }
        const volumeData = Object.entries(byDay).map(([date, counts]) => ({ date, ...counts }))
        setRealVolumeData(volumeData)
      } else {
        setRealDocuments([])
        setRealNfeTotal(0)
        setRealCteTotal(0)
        setRealMdfeTotal(0)
        setRealNfseTotal(0)
        setRealVolumeData([])
      }

      // Polling log — últimos 5 (atemporal, feed de atividade recente)
      const { data: activityData } = await sb
        .from('polling_log')
        .select('id, tipo, cnpj, status, docs_found, created_at')
        .order('created_at', { ascending: false })
        .limit(5)

      if (activityData) setRealActivity(activityData)

      // Créditos do tenant (atemporal)
      const { data: tenantData } = await sb
        .from('tenants')
        .select('credits')
        .limit(1)
        .single()

      if (tenantData) setRealCredits(tenantData.credits)
    } catch (e) {
      console.error("[DFeAxis] Error loading dashboard data:", e)
    } finally {
      setRealLoading(false)
    }
  }, [currentRange])

  useEffect(() => {
    if (!settings.showMockData) loadRealData()
  }, [settings.showMockData, loadRealData])

  // Label da competência atual pra exibir no dashboard
  const periodoAtual = currentRange.shortLabel

  const nfeValue = showMock ? "1.247" : realCounts.nfe.toLocaleString("pt-BR")
  const cteValue = showMock ? "384" : realCounts.cte.toLocaleString("pt-BR")
  const mdfeValue = showMock ? "56" : realCounts.mdfe.toLocaleString("pt-BR")
  const nfseValue = showMock ? "12" : realCounts.nfse.toLocaleString("pt-BR")
  const allFinancialTotal = realNfeTotal + realCteTotal + realMdfeTotal + realNfseTotal

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
            <select
              id="competencia-select"
              aria-label="Selecionar competência mensal"
              value={selectedCompetencia}
              onChange={(e) =>
                setSelectedCompetencia(e.target.value as CompetenciaId)
              }
              className="absolute inset-0 cursor-pointer opacity-0"
            >
              {competenciaOptions.map((opt) => (
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
            <StatCard
              title="Créditos"
              value={realCredits?.toLocaleString("pt-BR") ?? "—"}
              icon={<Receipt className="h-4 w-4" />}
              period="Saldo atual"
              color="text-emerald-600"
            />
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
        const limiteTotal = isActive
          ? docsIncludedMes
          : 500 // trial cap fixo
        const pctUso = limiteTotal > 0
          ? Math.min(100, Math.round((realDocsNaCompetencia / limiteTotal) * 100))
          : 0
        const excedenteDocs = Math.max(0, realDocsNaCompetencia - limiteTotal)
        const excedenteValorCents = isActive ? excedenteDocs * overageCentsPerDoc : 0
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
                      ? "bg-amber-500"
                      : pctUso >= 90
                        ? "bg-amber-400"
                        : "bg-emerald-500"
                  }`}
                  style={{ width: `${Math.max(pctUso, excedenteDocs > 0 ? 100 : pctUso)}%` }}
                />
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground">
                  {realDocsNaCompetencia.toLocaleString("pt-BR")} de{" "}
                  {limiteTotal.toLocaleString("pt-BR")} documentos capturados
                  {!isActive && " (limite do trial)"}
                </span>
                {excedenteDocs > 0 ? (
                  isActive ? (
                    <span className="font-semibold text-amber-600">
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
                { label: "Autorizadas", value: "R$ 2.847.320,45", amount: 2847320, color: "text-emerald-600", bgColor: "bg-emerald-500" },
                { label: "Canceladas", value: "R$ 63.250,00", amount: 63250, color: "text-gray-500", bgColor: "bg-gray-400" },
              ] : [
                ...(realNfeTotal > 0 ? [{ label: `NF-e (${realCounts.nfe})`, value: fmt(realNfeTotal), amount: realNfeTotal, color: "text-blue-600", bgColor: "bg-blue-500" }] : []),
                ...(realCteTotal > 0 ? [{ label: `CT-e (${realCounts.cte})`, value: fmt(realCteTotal), amount: realCteTotal, color: "text-violet-600", bgColor: "bg-violet-500" }] : []),
                ...(realMdfeTotal > 0 ? [{ label: `MDF-e (${realCounts.mdfe})`, value: fmt(realMdfeTotal), amount: realMdfeTotal, color: "text-emerald-600", bgColor: "bg-emerald-500" }] : []),
                ...(realNfseTotal > 0 ? [{ label: `NFS-e (${realCounts.nfse})`, value: fmt(realNfseTotal), amount: realNfseTotal, color: "text-amber-600", bgColor: "bg-amber-500" }] : []),
              ]}
            />
          )
        })()}
        <VolumeChart empty={false} realData={showMock ? undefined : realVolumeData} />
      </div>

      {/* Recent documents */}
      <RecentDocuments empty={showMock ? false : realDocuments.length === 0} documents={showMock ? undefined : realDocuments} />
    </div>
  )
}
