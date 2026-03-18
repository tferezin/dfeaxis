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
  const [realLoading, setRealLoading] = useState(false)

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
        .select('credits_balance')
        .limit(1)
        .single()

      if (tenantData) setRealCredits(tenantData.credits_balance)
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
        <FinancialCard
          title="NF-e"
          icon={<FileText className="h-4 w-4 text-blue-600" />}
          totalLabel="Total Líquido"
          totalValue={showMock ? "R$ 2.847.320,45" : "R$ 0,00"}
          period="Mar 2026"
          items={[
            {
              label: "Autorizadas",
              value: showMock ? "R$ 2.847.320,45" : "R$ 0,00",
              amount: showMock ? 2847320 : 0,
              color: "text-emerald-600",
              bgColor: "bg-emerald-500",
            },
            {
              label: "Canceladas",
              value: showMock ? "R$ 63.250,00" : "R$ 0,00",
              amount: showMock ? 63250 : 0,
              color: "text-gray-500",
              bgColor: "bg-gray-400",
            },
          ]}
        />
        <VolumeChart empty={!showMock} />
      </div>

      {/* Recent documents */}
      <RecentDocuments empty={!showMock} />
    </div>
  )
}
