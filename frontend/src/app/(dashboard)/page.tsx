"use client"

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

export default function DashboardPage() {
  const { settings } = useSettings()
  const showMock = settings.showMockData
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
          value={showMock ? "1.247" : "\u2014"}
          icon={<FileText className="h-4 w-4" />}
          period="Últimos 30 dias"
          trend={showMock ? { value: 12.5, label: "vs. mês anterior" } : undefined}
          color="text-blue-600"
        />
        <StatCard
          title="CT-e Recebidos"
          value={showMock ? "384" : "\u2014"}
          icon={<Truck className="h-4 w-4" />}
          period="Últimos 30 dias"
          trend={showMock ? { value: 8.3, label: "vs. mês anterior" } : undefined}
          color="text-violet-600"
        />
        <StatCard
          title="MDF-e Recebidos"
          value={showMock ? "56" : "\u2014"}
          icon={<FileCheck className="h-4 w-4" />}
          period="Últimos 30 dias"
          trend={showMock ? { value: -3.2, label: "vs. mês anterior" } : undefined}
          color="text-emerald-600"
        />
        <StatCard
          title="NFS-e Recebidas"
          value={showMock ? "12" : "\u2014"}
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
