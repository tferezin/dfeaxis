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
import { Separator } from "@/components/ui/separator"

export default function DashboardPage() {
  return (
    <div className="space-y-6">
      {/* Top controls */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            Visao geral dos seus documentos fiscais
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* Company selector */}
          <button className="inline-flex items-center gap-2 rounded-lg border bg-background px-3 py-2 text-sm font-medium shadow-sm transition-colors hover:bg-muted">
            <Building2 className="h-4 w-4 text-muted-foreground" />
            <span>Tech Solutions Ltda</span>
            <span className="hidden text-xs text-muted-foreground sm:inline">
              12.345.678/0001-90
            </span>
            <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
          </button>
          {/* Date range */}
          <button className="inline-flex items-center gap-2 rounded-lg border bg-background px-3 py-2 text-sm font-medium shadow-sm transition-colors hover:bg-muted">
            <CalendarDays className="h-4 w-4 text-muted-foreground" />
            <span>Mar 2026</span>
            <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
          </button>
        </div>
      </div>

      {/* Stat cards grid */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="NF-e"
          value="1.247"
          icon={<FileText className="h-5 w-5" />}
          period="Ultimos 30 dias"
          trend={{ value: 12.5, label: "vs. mes anterior" }}
          color="text-blue-600"
          subCounts={[
            { label: "Entrada", value: 843, color: "bg-blue-50 text-blue-700" },
            { label: "Saida", value: 404, color: "bg-indigo-50 text-indigo-700" },
          ]}
        />
        <StatCard
          title="CT-e"
          value="384"
          icon={<Truck className="h-5 w-5" />}
          period="Ultimos 30 dias"
          trend={{ value: 8.3, label: "vs. mes anterior" }}
          color="text-violet-600"
          subCounts={[
            { label: "Recebidos", value: 312, color: "bg-violet-50 text-violet-700" },
            { label: "Emitidos", value: 72, color: "bg-purple-50 text-purple-700" },
          ]}
        />
        <StatCard
          title="MDF-e"
          value="56"
          icon={<FileCheck className="h-5 w-5" />}
          period="Ultimos 30 dias"
          trend={{ value: -3.2, label: "vs. mes anterior" }}
          color="text-emerald-600"
          subCounts={[
            { label: "Encerrados", value: 48, color: "bg-emerald-50 text-emerald-700" },
            { label: "Abertos", value: 8, color: "bg-teal-50 text-teal-700" },
          ]}
        />
        <StatCard
          title="NFS-e"
          value="--"
          icon={<Receipt className="h-5 w-5" />}
          period=""
          badge="Em breve"
          color="text-amber-600"
        />
      </div>

      <Separator />

      {/* Financial cards */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <FinancialCard
          title="Resumo Financeiro NF-e"
          icon={<FileText className="h-5 w-5 text-blue-600" />}
          totalLabel="Total Liquido"
          totalValue="R$ 2.847.320,45"
          period="Mar 2026"
          items={[
            {
              label: "Recebidas",
              value: "R$ 1.923.450,30",
              amount: 1923450,
              color: "text-emerald-600",
              bgColor: "bg-emerald-500",
            },
            {
              label: "Emitidas",
              value: "R$ 987.120,15",
              amount: 987120,
              color: "text-blue-600",
              bgColor: "bg-blue-500",
            },
            {
              label: "Canceladas",
              value: "R$ 63.250,00",
              amount: 63250,
              color: "text-gray-500",
              bgColor: "bg-gray-400",
            },
          ]}
        />
        <FinancialCard
          title="Resumo Financeiro CT-e"
          icon={<Truck className="h-5 w-5 text-violet-600" />}
          totalLabel="Total Liquido"
          totalValue="R$ 456.780,90"
          period="Mar 2026"
          items={[
            {
              label: "Recebidos",
              value: "R$ 342.560,70",
              amount: 342560,
              color: "text-emerald-600",
              bgColor: "bg-emerald-500",
            },
            {
              label: "Emitidos",
              value: "R$ 128.430,20",
              amount: 128430,
              color: "text-blue-600",
              bgColor: "bg-blue-500",
            },
            {
              label: "Cancelados",
              value: "R$ 14.210,00",
              amount: 14210,
              color: "text-gray-500",
              bgColor: "bg-gray-400",
            },
          ]}
        />
      </div>

      <Separator />

      {/* Volume chart */}
      <VolumeChart />

      <Separator />

      {/* Recent documents table */}
      <RecentDocuments />
    </div>
  )
}
