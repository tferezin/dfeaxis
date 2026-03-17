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
import { OnboardingGuide } from "@/components/dashboard/onboarding-guide"
import { StatCard } from "@/components/dashboard/stat-card"
import { FinancialCard } from "@/components/dashboard/financial-card"
import { VolumeChart } from "@/components/dashboard/volume-chart"
import { RecentDocuments } from "@/components/dashboard/recent-documents"
import { Separator } from "@/components/ui/separator"
import { useSettings } from "@/hooks/use-settings"

export default function DashboardPage() {
  const { settings } = useSettings()
  const showMock = settings.showMockData
  return (
    <div className="space-y-6">
      {/* Onboarding guide — shows when mock data is off (real testing mode) */}
      <OnboardingGuide />

      {/* Top controls */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            Visao geral dos documentos recebidos
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
          title="NF-e Recebidas"
          value={showMock ? "1.247" : "\u2014"}
          icon={<FileText className="h-5 w-5" />}
          period="Ultimos 30 dias"
          trend={showMock ? { value: 12.5, label: "vs. mes anterior" } : undefined}
          color="text-blue-600"
          subCounts={showMock ? [
            { label: "Autorizadas", value: 1105, color: "bg-blue-50 text-blue-700" },
            { label: "Canceladas", value: 142, color: "bg-indigo-50 text-indigo-700" },
          ] : undefined}
        />
        <StatCard
          title="CT-e Recebidos"
          value={showMock ? "384" : "\u2014"}
          icon={<Truck className="h-5 w-5" />}
          period="Ultimos 30 dias"
          trend={showMock ? { value: 8.3, label: "vs. mes anterior" } : undefined}
          color="text-violet-600"
          subCounts={showMock ? [
            { label: "Autorizados", value: 352, color: "bg-violet-50 text-violet-700" },
            { label: "Cancelados", value: 32, color: "bg-purple-50 text-purple-700" },
          ] : undefined}
        />
        <StatCard
          title="MDF-e Recebidos"
          value={showMock ? "56" : "\u2014"}
          icon={<FileCheck className="h-5 w-5" />}
          period="Ultimos 30 dias"
          trend={showMock ? { value: -3.2, label: "vs. mes anterior" } : undefined}
          color="text-emerald-600"
          subCounts={showMock ? [
            { label: "Encerrados", value: 48, color: "bg-emerald-50 text-emerald-700" },
            { label: "Abertos", value: 8, color: "bg-teal-50 text-teal-700" },
          ] : undefined}
        />
        <StatCard
          title="NFS-e Recebidas"
          value={showMock ? "12" : "\u2014"}
          icon={<Receipt className="h-5 w-5" />}
          period="Ultimos 30 dias"
          trend={showMock ? { value: 4.1, label: "vs. mes anterior" } : undefined}
          badge="ADN"
          color="text-amber-600"
          subCounts={showMock ? [
            { label: "Autorizadas", value: 10, color: "bg-amber-50 text-amber-700" },
            { label: "Canceladas", value: 2, color: "bg-orange-50 text-orange-700" },
          ] : undefined}
        />
      </div>

      <Separator />

      {/* Financial cards */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <FinancialCard
          title="Resumo Financeiro NF-e"
          icon={<FileText className="h-5 w-5 text-blue-600" />}
          totalLabel="Total Liquido"
          totalValue={showMock ? "R$ 2.847.320,45" : "R$ 0,00"}
          period="Mar 2026"
          items={showMock ? [
            {
              label: "Autorizadas",
              value: "R$ 2.847.320,45",
              amount: 2847320,
              color: "text-emerald-600",
              bgColor: "bg-emerald-500",
            },
            {
              label: "Canceladas",
              value: "R$ 63.250,00",
              amount: 63250,
              color: "text-gray-500",
              bgColor: "bg-gray-400",
            },
          ] : [
            {
              label: "Autorizadas",
              value: "R$ 0,00",
              amount: 0,
              color: "text-emerald-600",
              bgColor: "bg-emerald-500",
            },
            {
              label: "Canceladas",
              value: "R$ 0,00",
              amount: 0,
              color: "text-gray-500",
              bgColor: "bg-gray-400",
            },
          ]}
        />
        <FinancialCard
          title="Resumo Financeiro CT-e"
          icon={<Truck className="h-5 w-5 text-violet-600" />}
          totalLabel="Total Liquido"
          totalValue={showMock ? "R$ 456.780,90" : "R$ 0,00"}
          period="Mar 2026"
          items={showMock ? [
            {
              label: "Autorizados",
              value: "R$ 442.570,90",
              amount: 442570,
              color: "text-emerald-600",
              bgColor: "bg-emerald-500",
            },
            {
              label: "Cancelados",
              value: "R$ 14.210,00",
              amount: 14210,
              color: "text-gray-500",
              bgColor: "bg-gray-400",
            },
          ] : [
            {
              label: "Autorizados",
              value: "R$ 0,00",
              amount: 0,
              color: "text-emerald-600",
              bgColor: "bg-emerald-500",
            },
            {
              label: "Cancelados",
              value: "R$ 0,00",
              amount: 0,
              color: "text-gray-500",
              bgColor: "bg-gray-400",
            },
          ]}
        />
      </div>

      <Separator />

      {/* Volume chart */}
      <VolumeChart empty={!showMock} />

      <Separator />

      {/* Recent documents table */}
      <RecentDocuments empty={!showMock} />
    </div>
  )
}
