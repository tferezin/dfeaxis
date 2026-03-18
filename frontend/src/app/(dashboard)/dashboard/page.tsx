"use client"

import { useState, useEffect, useCallback } from "react"
import {
  FileText,
  Truck,
  FileCheck,
  Receipt,
  Building2,
  CalendarDays,
  ChevronDown,
} from "lucide-react"
import { StatCard } from "@/components/dashboard/stat-card"
import { FinancialCard } from "@/components/dashboard/financial-card"
import { VolumeChart } from "@/components/dashboard/volume-chart"
import { RecentDocuments } from "@/components/dashboard/recent-documents"
import { useSettings } from "@/hooks/use-settings"
import { getSupabase } from "@/lib/supabase"

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

  const [realCounts, setRealCounts] = useState<DashboardCounts>({ nfe: 0, cte: 0, mdfe: 0, nfse: 0 })
  const [realActivity, setRealActivity] = useState<ActivityEntry[]>([])
  const [realCredits, setRealCredits] = useState<number | null>(null)
  const [realDocuments, setRealDocuments] = useState<Array<{ tipo: string; chave_acesso: string; cnpj: string; nsu: string; status: string; fetched_at: string }>>([])
  const [realNfeTotal, setRealNfeTotal] = useState(0)
  const [realCteTotal, setRealCteTotal] = useState(0)
  const [realMdfeTotal, setRealMdfeTotal] = useState(0)
  const [realNfseTotal, setRealNfseTotal] = useState(0)
  const [realLoading, setRealLoading] = useState(false)

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

      // Count documents by tipo with status='available'
      const [nfeRes, cteRes, mdfeRes, nfseRes] = await Promise.all([
        sb.from('documents').select('id', { count: 'exact', head: true }).eq('tipo', 'NFE').eq('status', 'available'),
        sb.from('documents').select('id', { count: 'exact', head: true }).eq('tipo', 'CTE').eq('status', 'available'),
        sb.from('documents').select('id', { count: 'exact', head: true }).eq('tipo', 'MDFE').eq('status', 'available'),
        sb.from('documents').select('id', { count: 'exact', head: true }).eq('tipo', 'NFSE').eq('status', 'available'),
      ])

      setRealCounts({
        nfe: nfeRes.count ?? 0,
        cte: cteRes.count ?? 0,
        mdfe: mdfeRes.count ?? 0,
        nfse: nfseRes.count ?? 0,
      })

      // Recent documents with XML for value extraction
      const { data: recentDocs } = await sb
        .from('documents')
        .select('tipo, chave_acesso, cnpj, nsu, status, fetched_at, xml_content')
        .eq('status', 'available')
        .order('fetched_at', { ascending: false })
        .limit(20)

      if (recentDocs) {
        setRealDocuments(recentDocs)

        // Sum values by type
        let nfeSum = 0, cteSum = 0, mdfeSum = 0, nfseSum = 0
        for (const doc of recentDocs) {
          const val = extractXmlValue(doc.xml_content || "", doc.tipo)
          if (doc.tipo === "NFE") nfeSum += val
          if (doc.tipo === "CTE") cteSum += val
          if (doc.tipo === "MDFE") mdfeSum += val
          if (doc.tipo === "NFSE") nfseSum += val
        }
        setRealNfeTotal(nfeSum)
        setRealCteTotal(cteSum)
        setRealMdfeTotal(mdfeSum)
        setRealNfseTotal(nfseSum)
      }

      // Last 5 polling_log entries for activity feed
      const { data: activityData } = await sb
        .from('polling_log')
        .select('id, tipo, cnpj, status, docs_found, created_at')
        .order('created_at', { ascending: false })
        .limit(5)

      if (activityData) setRealActivity(activityData)

      // Credits balance from tenants
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
  }, [])

  useEffect(() => {
    if (!settings.showMockData) loadRealData()
  }, [settings.showMockData, loadRealData])

  const nfeValue = showMock ? "1.247" : realCounts.nfe.toLocaleString("pt-BR")
  const cteValue = showMock ? "384" : realCounts.cte.toLocaleString("pt-BR")
  const mdfeValue = showMock ? "56" : realCounts.mdfe.toLocaleString("pt-BR")
  const nfseValue = showMock ? "12" : realCounts.nfse.toLocaleString("pt-BR")

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
          <button className="inline-flex items-center gap-2 rounded-lg border bg-background px-2.5 py-1.5 text-xs font-medium shadow-sm transition-colors hover:bg-muted">
            <Building2 className="h-3.5 w-3.5 text-muted-foreground" />
            <span>Tech Solutions Ltda</span>
            <ChevronDown className="h-3 w-3 text-muted-foreground" />
          </button>
          <button className="inline-flex items-center gap-2 rounded-lg border bg-background px-2.5 py-1.5 text-xs font-medium shadow-sm transition-colors hover:bg-muted">
            <CalendarDays className="h-3.5 w-3.5 text-muted-foreground" />
            <span>Mar 2026</span>
            <ChevronDown className="h-3 w-3 text-muted-foreground" />
          </button>
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard
          title="NF-e Recebidas"
          value={nfeValue}
          icon={<FileText className="h-4 w-4" />}
          period="Últimos 30 dias"
          trend={showMock ? { value: 12.5, label: "vs. mês anterior" } : undefined}
          color="text-blue-600"
        />
        <StatCard
          title="CT-e Recebidos"
          value={cteValue}
          icon={<Truck className="h-4 w-4" />}
          period="Últimos 30 dias"
          trend={showMock ? { value: 8.3, label: "vs. mês anterior" } : undefined}
          color="text-violet-600"
        />
        <StatCard
          title="MDF-e Recebidos"
          value={mdfeValue}
          icon={<FileCheck className="h-4 w-4" />}
          period="Últimos 30 dias"
          trend={showMock ? { value: -3.2, label: "vs. mês anterior" } : undefined}
          color="text-emerald-600"
        />
        <StatCard
          title="NFS-e Recebidas"
          value={nfseValue}
          icon={<Receipt className="h-4 w-4" />}
          period="Últimos 30 dias"
          trend={showMock ? { value: 4.1, label: "vs. mês anterior" } : undefined}
          badge="ADN"
          color="text-amber-600"
        />
      </div>

      {/* Financial + Chart side by side */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        {(() => {
          const allTotal = realNfeTotal + realCteTotal + realMdfeTotal + realNfseTotal
          const fmt = (v: number) => `R$ ${v.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}`
          return (
            <FinancialCard
              title="Documentos Recebidos"
              icon={<FileText className="h-4 w-4 text-blue-600" />}
              totalLabel="Total Geral"
              totalValue={showMock ? "R$ 2.847.320,45" : fmt(allTotal)}
              period="Mar 2026"
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
        <VolumeChart empty={!showMock} />
      </div>

      {/* Recent documents */}
      <RecentDocuments empty={showMock ? false : realDocuments.length === 0} documents={showMock ? undefined : realDocuments} />
    </div>
  )
}
