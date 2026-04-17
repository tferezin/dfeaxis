"use client"

import { useState, useEffect, useCallback } from "react"
import Link from "next/link"
import {
  Users,
  DollarSign,
  FileText,
  TrendingUp,
  AlertTriangle,
  Search,
  ExternalLink,
  RefreshCw,
  ShieldAlert,
  Clock,
  Loader2,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Megaphone,
} from "lucide-react"
import { apiFetch } from "@/lib/api"

// ── Types ────────────────────────────────────────────────────────────
interface KPIs {
  total_tenants: number
  tenants_by_status: {
    trialing: number
    active: number
    past_due: number
    cancelled: number
    other: number
  }
  mrr_cents: number
  docs_today: number
  docs_this_month: number
  conversion_rate_30d: number
}

interface PlanDistribution {
  plan: string
  count: number
}

interface DocsByType {
  tipo: string
  count: number
}

interface PollingError {
  id: string
  tenant_id: string
  tipo: string
  error: string
  created_at: string
}

interface SefazEndpoint {
  name: string
  status: "online" | "offline" | "degraded"
  last_check: string
}

interface TrialFunnel {
  signups_7d: number
  signups_30d: number
  conversions_7d: number
  conversions_30d: number
  conversion_rate_7d: number
  conversion_rate_30d: number
}

interface UtmRow {
  source: string
  count: number
}

interface CampaignRow {
  campaign: string
  count: number
}

interface TenantRow {
  id: string
  company_name: string | null
  email: string
  plan: string | null
  subscription_status: string | null
  docs_consumidos_mes: number
  created_at: string
  utm_source: string | null
}

interface CertAlert {
  tenant_id: string
  company_name: string | null
  cnpj: string
  expires_at: string
}

interface Alert {
  type: "cert_expiring" | "chat_escalated" | "past_due"
  message: string
  tenant_id?: string
  count?: number
}

interface DashboardData {
  kpis: KPIs
  plan_distribution: PlanDistribution[]
  docs_by_type: DocsByType[]
  polling_errors: PollingError[]
  sefaz_health: SefazEndpoint[]
  trial_funnel: TrialFunnel
  top_utm_sources: UtmRow[]
  top_campaigns: CampaignRow[]
  alerts: Alert[]
  cert_alerts: CertAlert[]
}

interface TenantsData {
  tenants: TenantRow[]
  total: number
}

// ── Helpers ──────────────────────────────────────────────────────────
const brl = (cents: number) =>
  new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(cents / 100)

const fmtNum = (n: number) => new Intl.NumberFormat("pt-BR").format(n)

const fmtPct = (n: number) => `${(n * 100).toFixed(1)}%`

const fmtDate = (iso: string) =>
  new Date(iso).toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
  })

const fmtDateTime = (iso: string) =>
  new Date(iso).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })

const statusColor: Record<string, string> = {
  trialing: "bg-blue-500/20 text-blue-400",
  active: "bg-emerald-500/20 text-emerald-400",
  past_due: "bg-amber-500/20 text-amber-400",
  cancelled: "bg-red-500/20 text-red-400",
  other: "bg-slate-500/20 text-slate-400",
}

const statusLabel: Record<string, string> = {
  trialing: "Trial",
  active: "Ativo",
  past_due: "Inadimplente",
  cancelled: "Cancelado",
  other: "Outro",
}

const sefazStatusIcon: Record<string, React.ReactNode> = {
  online: <CheckCircle2 className="size-4 text-emerald-400" />,
  offline: <XCircle className="size-4 text-red-400" />,
  degraded: <AlertCircle className="size-4 text-amber-400" />,
}

// ── Skeleton ─────────────────────────────────────────────────────────
function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      className={`animate-pulse rounded-md bg-slate-700/50 ${className}`}
    />
  )
}

function KPISkeleton() {
  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="rounded-xl border border-slate-800 bg-slate-900 p-4">
          <Skeleton className="mb-2 h-4 w-24" />
          <Skeleton className="mb-1 h-8 w-20" />
          <Skeleton className="h-3 w-32" />
        </div>
      ))}
    </div>
  )
}

function TableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  )
}

// ── Component ────────────────────────────────────────────────────────
export default function AdminDashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [tenants, setTenants] = useState<TenantsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState("")
  const [statusFilter, setStatusFilter] = useState<string>("all")
  const [refreshing, setRefreshing] = useState(false)

  const loadData = useCallback(async () => {
    try {
      const [dashRes, tenantsRes] = await Promise.all([
        apiFetch<DashboardData>("/admin/dashboard").catch(() => null),
        apiFetch<TenantsData>("/admin/tenants").catch(() => null),
      ])
      if (!dashRes && !tenantsRes) {
        throw new Error("403")
      }
      setData(dashRes)
      setTenants(tenantsRes)
      setError(null)
    } catch (e: unknown) {
      const msg =
        e instanceof Error && e.message.includes("403")
          ? "Acesso nao autorizado"
          : "Erro ao carregar dados do admin"
      setError(msg)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    loadData()
  }, [loadData])

  const handleRefresh = () => {
    setRefreshing(true)
    loadData()
  }

  // ── Error state ──
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-32 text-center">
        <ShieldAlert className="mb-4 size-12 text-red-400" />
        <h2 className="mb-2 text-lg font-semibold text-slate-200">{error}</h2>
        <p className="mb-4 text-sm text-slate-400">
          Verifique suas permissoes ou tente novamente.
        </p>
        <button
          onClick={handleRefresh}
          className="rounded-lg bg-slate-800 px-4 py-2 text-sm text-slate-200 transition-colors hover:bg-slate-700"
        >
          Tentar novamente
        </button>
      </div>
    )
  }

  // ── Filter tenants ──
  const filteredTenants = (tenants?.tenants ?? []).filter((t) => {
    const matchesSearch =
      !search ||
      (t.company_name ?? "").toLowerCase().includes(search.toLowerCase()) ||
      t.email.toLowerCase().includes(search.toLowerCase()) ||
      (t.utm_source ?? "").toLowerCase().includes(search.toLowerCase())
    const matchesStatus =
      statusFilter === "all" || t.subscription_status === statusFilter
    return matchesSearch && matchesStatus
  })

  const kpis = data?.kpis

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-white">
            Painel Administrativo
          </h1>
          <p className="text-sm text-slate-400">
            Visao geral do negocio DFeAxis
          </p>
        </div>
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 transition-colors hover:bg-slate-700 disabled:opacity-50"
        >
          <RefreshCw
            className={`size-4 ${refreshing ? "animate-spin" : ""}`}
          />
          Atualizar
        </button>
      </div>

      {/* ── Section 1: KPI Cards ── */}
      {loading ? (
        <KPISkeleton />
      ) : kpis ? (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {/* Total Tenants */}
          <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
            <div className="mb-1 flex items-center gap-2 text-sm text-slate-400">
              <Users className="size-4" />
              Total de Tenants
            </div>
            <p className="text-2xl font-bold text-white">
              {fmtNum(kpis.total_tenants)}
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {Object.entries(kpis.tenants_by_status).map(([key, val]) =>
                val > 0 ? (
                  <span
                    key={key}
                    className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${statusColor[key] ?? statusColor.other}`}
                  >
                    {val} {statusLabel[key] ?? key}
                  </span>
                ) : null
              )}
            </div>
          </div>

          {/* MRR */}
          <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
            <div className="mb-1 flex items-center gap-2 text-sm text-slate-400">
              <DollarSign className="size-4" />
              MRR
            </div>
            <p className="text-2xl font-bold text-emerald-400">
              {brl(kpis.mrr_cents)}
            </p>
            <p className="mt-1 text-xs text-slate-500">
              Receita Recorrente Mensal
            </p>
          </div>

          {/* Docs Captured */}
          <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
            <div className="mb-1 flex items-center gap-2 text-sm text-slate-400">
              <FileText className="size-4" />
              Documentos Capturados
            </div>
            <p className="text-2xl font-bold text-white">
              {fmtNum(kpis.docs_this_month)}
            </p>
            <p className="mt-1 text-xs text-slate-500">
              Hoje: {fmtNum(kpis.docs_today)}
            </p>
          </div>

          {/* Conversion Rate */}
          <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
            <div className="mb-1 flex items-center gap-2 text-sm text-slate-400">
              <TrendingUp className="size-4" />
              Conversao Trial → Pago
            </div>
            <p className="text-2xl font-bold text-blue-400">
              {fmtPct(kpis.conversion_rate_30d)}
            </p>
            <p className="mt-1 text-xs text-slate-500">Ultimos 30 dias</p>
          </div>
        </div>
      ) : null}

      {/* ── Section 2: Revenue & Plans ── */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
          <h3 className="mb-3 text-sm font-semibold text-slate-300">
            Distribuicao por Plano
          </h3>
          {loading ? (
            <TableSkeleton rows={3} />
          ) : data?.plan_distribution && data.plan_distribution.length > 0 ? (
            <div className="space-y-2">
              {data.plan_distribution.map((p) => {
                const total = data.plan_distribution.reduce(
                  (s, x) => s + x.count,
                  0
                )
                const pct = total > 0 ? (p.count / total) * 100 : 0
                return (
                  <div key={p.plan} className="flex items-center gap-3">
                    <span className="w-24 text-sm text-slate-300">
                      {p.plan || "Sem plano"}
                    </span>
                    <div className="flex-1">
                      <div className="h-2 w-full overflow-hidden rounded-full bg-slate-700">
                        <div
                          className="h-full rounded-full bg-emerald-500 transition-all"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                    <span className="w-12 text-right text-sm font-medium text-slate-200">
                      {p.count}
                    </span>
                  </div>
                )
              })}
            </div>
          ) : (
            <p className="text-sm text-slate-500">Nenhum dado disponivel</p>
          )}
        </div>

        {/* MRR placeholder — can expand with history */}
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
          <h3 className="mb-3 text-sm font-semibold text-slate-300">
            MRR Atual
          </h3>
          {loading ? (
            <Skeleton className="h-20 w-full" />
          ) : kpis ? (
            <div className="flex flex-col items-center justify-center py-6">
              <p className="text-3xl font-bold text-emerald-400">
                {brl(kpis.mrr_cents)}
              </p>
              <p className="mt-2 text-xs text-slate-500">
                {fmtNum(kpis.tenants_by_status.active)} tenants ativos
              </p>
            </div>
          ) : (
            <p className="text-sm text-slate-500">Nenhum dado disponivel</p>
          )}
        </div>
      </div>

      {/* ── Section 3: Document Capture ── */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Docs by type */}
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
          <h3 className="mb-3 text-sm font-semibold text-slate-300">
            Documentos por Tipo (mes)
          </h3>
          {loading ? (
            <TableSkeleton rows={4} />
          ) : data?.docs_by_type && data.docs_by_type.length > 0 ? (
            <div className="space-y-2">
              {data.docs_by_type.map((d) => (
                <div
                  key={d.tipo}
                  className="flex items-center justify-between rounded-lg bg-slate-800/50 px-3 py-2"
                >
                  <span className="text-sm font-medium text-slate-200">
                    {d.tipo}
                  </span>
                  <span className="text-sm font-bold text-white">
                    {fmtNum(d.count)}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-500">Nenhum documento capturado</p>
          )}
        </div>

        {/* Polling errors */}
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
          <h3 className="mb-3 text-sm font-semibold text-slate-300">
            Erros de Polling Recentes
          </h3>
          {loading ? (
            <TableSkeleton rows={4} />
          ) : data?.polling_errors && data.polling_errors.length > 0 ? (
            <div className="max-h-60 space-y-2 overflow-y-auto">
              {data.polling_errors.map((e) => (
                <div
                  key={e.id}
                  className="rounded-lg border border-red-900/30 bg-red-950/20 px-3 py-2"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-red-300">
                      {e.tipo}
                    </span>
                    <span className="text-xs text-slate-500">
                      {fmtDateTime(e.created_at)}
                    </span>
                  </div>
                  <p className="mt-1 truncate text-xs text-slate-400">
                    {e.error}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex flex-col items-center py-6 text-center">
              <CheckCircle2 className="mb-2 size-6 text-emerald-400" />
              <p className="text-sm text-slate-400">Nenhum erro recente</p>
            </div>
          )}
        </div>

        {/* SEFAZ Health */}
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
          <h3 className="mb-3 text-sm font-semibold text-slate-300">
            Status SEFAZ
          </h3>
          {loading ? (
            <TableSkeleton rows={4} />
          ) : data?.sefaz_health && data.sefaz_health.length > 0 ? (
            <div className="space-y-2">
              {data.sefaz_health.map((ep) => (
                <div
                  key={ep.name}
                  className="flex items-center justify-between rounded-lg bg-slate-800/50 px-3 py-2"
                >
                  <div className="flex items-center gap-2">
                    {sefazStatusIcon[ep.status]}
                    <span className="text-sm text-slate-200">{ep.name}</span>
                  </div>
                  <span className="text-xs text-slate-500">
                    {fmtDateTime(ep.last_check)}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-500">
              Dados de saude indisponiveis
            </p>
          )}
        </div>
      </div>

      {/* ── Section 4: Trial Funnel ── */}
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
        <h3 className="mb-4 text-sm font-semibold text-slate-300">
          Funil de Trial
        </h3>
        {loading ? (
          <Skeleton className="h-16 w-full" />
        ) : data?.trial_funnel ? (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
            <div>
              <p className="text-xs text-slate-500">Signups 7d</p>
              <p className="text-lg font-bold text-white">
                {fmtNum(data.trial_funnel.signups_7d)}
              </p>
            </div>
            <div>
              <p className="text-xs text-slate-500">Signups 30d</p>
              <p className="text-lg font-bold text-white">
                {fmtNum(data.trial_funnel.signups_30d)}
              </p>
            </div>
            <div>
              <p className="text-xs text-slate-500">Conversoes 7d</p>
              <p className="text-lg font-bold text-emerald-400">
                {fmtNum(data.trial_funnel.conversions_7d)}
              </p>
            </div>
            <div>
              <p className="text-xs text-slate-500">Conversoes 30d</p>
              <p className="text-lg font-bold text-emerald-400">
                {fmtNum(data.trial_funnel.conversions_30d)}
              </p>
            </div>
            <div>
              <p className="text-xs text-slate-500">Taxa 7d</p>
              <p className="text-lg font-bold text-blue-400">
                {fmtPct(data.trial_funnel.conversion_rate_7d)}
              </p>
            </div>
            <div>
              <p className="text-xs text-slate-500">Taxa 30d</p>
              <p className="text-lg font-bold text-blue-400">
                {fmtPct(data.trial_funnel.conversion_rate_30d)}
              </p>
            </div>
          </div>
        ) : (
          <p className="text-sm text-slate-500">Nenhum dado disponivel</p>
        )}
      </div>

      {/* ── Section 5: Campaign Attribution ── */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Top UTM Sources */}
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
          <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-300">
            <Megaphone className="size-4" />
            Top UTM Sources
          </h3>
          {loading ? (
            <TableSkeleton rows={5} />
          ) : data?.top_utm_sources && data.top_utm_sources.length > 0 ? (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700 text-left">
                  <th className="pb-2 text-xs font-medium text-slate-500">
                    Source
                  </th>
                  <th className="pb-2 text-right text-xs font-medium text-slate-500">
                    Signups
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.top_utm_sources.map((u) => (
                  <tr key={u.source} className="border-b border-slate-800/50">
                    <td className="py-2 text-slate-200">
                      {u.source || "(direto)"}
                    </td>
                    <td className="py-2 text-right font-medium text-white">
                      {fmtNum(u.count)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="text-sm text-slate-500">Sem dados de UTM</p>
          )}
        </div>

        {/* Top Campaigns */}
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
          <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-300">
            <Megaphone className="size-4" />
            Top Campanhas
          </h3>
          {loading ? (
            <TableSkeleton rows={5} />
          ) : data?.top_campaigns && data.top_campaigns.length > 0 ? (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700 text-left">
                  <th className="pb-2 text-xs font-medium text-slate-500">
                    Campanha
                  </th>
                  <th className="pb-2 text-right text-xs font-medium text-slate-500">
                    Signups
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.top_campaigns.map((c) => (
                  <tr key={c.campaign} className="border-b border-slate-800/50">
                    <td className="py-2 text-slate-200">
                      {c.campaign || "(sem campanha)"}
                    </td>
                    <td className="py-2 text-right font-medium text-white">
                      {fmtNum(c.count)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="text-sm text-slate-500">Sem dados de campanha</p>
          )}
        </div>
      </div>

      {/* ── Section 6: Tenant List ── */}
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <h3 className="text-sm font-semibold text-slate-300">
            Tenants ({fmtNum(filteredTenants.length)})
          </h3>
          <div className="flex flex-col gap-2 sm:flex-row">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-slate-500" />
              <input
                type="text"
                placeholder="Buscar empresa, email, UTM..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full rounded-lg border border-slate-700 bg-slate-800 py-1.5 pl-8 pr-3 text-sm text-slate-200 placeholder:text-slate-500 outline-none focus:border-slate-600 sm:w-64"
              />
            </div>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 outline-none focus:border-slate-600"
            >
              <option value="all">Todos os status</option>
              <option value="trialing">Trial</option>
              <option value="active">Ativo</option>
              <option value="past_due">Inadimplente</option>
              <option value="cancelled">Cancelado</option>
            </select>
          </div>
        </div>

        {loading ? (
          <TableSkeleton rows={8} />
        ) : filteredTenants.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700 text-left">
                  <th className="pb-2 text-xs font-medium text-slate-500">
                    Empresa
                  </th>
                  <th className="pb-2 text-xs font-medium text-slate-500">
                    Email
                  </th>
                  <th className="pb-2 text-xs font-medium text-slate-500">
                    Plano
                  </th>
                  <th className="pb-2 text-xs font-medium text-slate-500">
                    Status
                  </th>
                  <th className="pb-2 text-right text-xs font-medium text-slate-500">
                    Docs/mes
                  </th>
                  <th className="pb-2 text-xs font-medium text-slate-500">
                    Criado
                  </th>
                  <th className="pb-2 text-xs font-medium text-slate-500">
                    UTM
                  </th>
                  <th className="pb-2 text-xs font-medium text-slate-500" />
                </tr>
              </thead>
              <tbody>
                {filteredTenants.map((t) => (
                  <tr
                    key={t.id}
                    className="border-b border-slate-800/50 transition-colors hover:bg-slate-800/30"
                  >
                    <td className="max-w-[180px] truncate py-2 font-medium text-slate-200">
                      {t.company_name || "-"}
                    </td>
                    <td className="max-w-[200px] truncate py-2 text-slate-400">
                      {t.email}
                    </td>
                    <td className="py-2 text-slate-300">{t.plan || "-"}</td>
                    <td className="py-2">
                      <span
                        className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${statusColor[t.subscription_status ?? "other"] ?? statusColor.other}`}
                      >
                        {statusLabel[t.subscription_status ?? "other"] ??
                          t.subscription_status ??
                          "-"}
                      </span>
                    </td>
                    <td className="py-2 text-right font-mono text-slate-200">
                      {fmtNum(t.docs_consumidos_mes)}
                    </td>
                    <td className="py-2 text-slate-400">
                      {fmtDate(t.created_at)}
                    </td>
                    <td className="py-2 text-slate-500">
                      {t.utm_source || "-"}
                    </td>
                    <td className="py-2">
                      <Link
                        href={`/admin/tenants/${t.id}`}
                        className="text-blue-400 transition-colors hover:text-blue-300"
                        title="Ver detalhes"
                      >
                        <ExternalLink className="size-4" />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="py-8 text-center">
            <Users className="mx-auto mb-2 size-8 text-slate-600" />
            <p className="text-sm text-slate-500">
              Nenhum tenant encontrado com os filtros atuais
            </p>
          </div>
        )}
      </div>

      {/* ── Section 7: Alerts ── */}
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
        <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-300">
          <AlertTriangle className="size-4 text-amber-400" />
          Alertas
        </h3>
        {loading ? (
          <TableSkeleton rows={3} />
        ) : (data?.alerts && data.alerts.length > 0) ||
          (data?.cert_alerts && data.cert_alerts.length > 0) ? (
          <div className="space-y-2">
            {/* Certificate alerts */}
            {data?.cert_alerts?.map((c, i) => (
              <div
                key={`cert-${i}`}
                className="flex items-start gap-3 rounded-lg border border-amber-900/30 bg-amber-950/20 px-3 py-2"
              >
                <Clock className="mt-0.5 size-4 shrink-0 text-amber-400" />
                <div>
                  <p className="text-sm text-amber-200">
                    Certificado expirando: {c.cnpj}
                  </p>
                  <p className="text-xs text-slate-400">
                    {c.company_name ?? "Tenant " + c.tenant_id} — expira em{" "}
                    {fmtDate(c.expires_at)}
                  </p>
                </div>
              </div>
            ))}
            {/* General alerts */}
            {data?.alerts?.map((a, i) => {
              const colors: Record<string, string> = {
                cert_expiring:
                  "border-amber-900/30 bg-amber-950/20 text-amber-200",
                chat_escalated:
                  "border-blue-900/30 bg-blue-950/20 text-blue-200",
                past_due: "border-red-900/30 bg-red-950/20 text-red-200",
              }
              const icons: Record<string, React.ReactNode> = {
                cert_expiring: (
                  <Clock className="mt-0.5 size-4 shrink-0 text-amber-400" />
                ),
                chat_escalated: (
                  <AlertCircle className="mt-0.5 size-4 shrink-0 text-blue-400" />
                ),
                past_due: (
                  <AlertTriangle className="mt-0.5 size-4 shrink-0 text-red-400" />
                ),
              }
              return (
                <div
                  key={`alert-${i}`}
                  className={`flex items-start gap-3 rounded-lg border px-3 py-2 ${colors[a.type] ?? "border-slate-700 bg-slate-800 text-slate-300"}`}
                >
                  {icons[a.type] ?? (
                    <AlertCircle className="mt-0.5 size-4 shrink-0 text-slate-400" />
                  )}
                  <p className="text-sm">{a.message}</p>
                </div>
              )
            })}
          </div>
        ) : (
          <div className="flex flex-col items-center py-6 text-center">
            <CheckCircle2 className="mb-2 size-6 text-emerald-400" />
            <p className="text-sm text-slate-400">
              Nenhum alerta no momento
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
