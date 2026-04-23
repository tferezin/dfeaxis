"use client"

import { Area, AreaChart, CartesianGrid, XAxis, YAxis, Line, LineChart } from "recharts"
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  ChartLegend,
  ChartLegendContent,
  type ChartConfig,
} from "@/components/ui/chart"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Inbox } from "lucide-react"

function generateMockData() {
  const data = []
  const now = new Date()
  for (let i = 29; i >= 0; i--) {
    const date = new Date(now)
    date.setDate(date.getDate() - i)
    const day = date.getDate().toString().padStart(2, "0")
    const month = (date.getMonth() + 1).toString().padStart(2, "0")
    data.push({
      date: `${day}/${month}`,
      nfe: Math.floor(Math.random() * 80 + 40),
      cte: Math.floor(Math.random() * 35 + 10),
    })
  }
  return data
}

const mockChartData = generateMockData()

const areaConfig = {
  nfe: { label: "NF-e", color: "oklch(0.623 0.214 259.815)" },
  cte: { label: "CT-e", color: "oklch(0.696 0.17 162.48)" },
} satisfies ChartConfig

const lineConfig = {
  nfe: { label: "NF-e", color: "#3b82f6" },
  cte: { label: "CT-e", color: "#8b5cf6" },
  cteos: { label: "CT-e OS", color: "#d946ef" },
  mdfe: { label: "MDF-e", color: "#10b981" },
  nfse: { label: "NFS-e", color: "#f59e0b" },
  overlap: { label: "Sobreposição", color: "#ef4444" },
} satisfies ChartConfig

export interface VolumeDataPoint {
  date: string
  nfe: number
  cte: number
  cteos: number
  mdfe: number
  nfse: number
}

interface ChartDataPoint extends VolumeDataPoint {
  overlap: number
}

function buildMonthDays(rawData: VolumeDataPoint[], competenciaId?: string): ChartDataPoint[] {
  const result: ChartDataPoint[] = []
  // Use competencia month if provided (e.g., "2026-03"), otherwise current month
  let year: number, month: number
  if (competenciaId && /^\d{4}-\d{2}$/.test(competenciaId)) {
    const [y, m] = competenciaId.split("-").map(Number)
    year = y
    month = m - 1 // JS months are 0-indexed
  } else {
    const now = new Date()
    year = now.getFullYear()
    month = now.getMonth()
  }
  const daysInMonth = new Date(year, month + 1, 0).getDate()

  const dataMap: Record<string, VolumeDataPoint> = {}
  for (const d of rawData) dataMap[d.date] = d

  for (let day = 1; day <= daysInMonth; day++) {
    const date = new Date(year, month, day)
    const key = date.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })
    const d = dataMap[key] || { date: key, nfe: 0, cte: 0, cteos: 0, mdfe: 0, nfse: 0 }
    // Find values that are shared by multiple types (same value > 0)
    const vals = [d.nfe, d.cte, d.cteos, d.mdfe, d.nfse].filter(v => v > 0)
    // Group by value to find overlapping ones
    const valueCounts: Record<number, number> = {}
    for (const v of vals) valueCounts[v] = (valueCounts[v] || 0) + 1
    // Find the value where overlap occurs (multiple types with same count)
    const overlappingValues = Object.entries(valueCounts).filter(([, count]) => count > 1)
    const overlap = overlappingValues.length > 0 ? Number(overlappingValues[0][0]) : 0
    result.push({ ...d, overlap })
  }
  return result
}

export function VolumeChart({ empty = false, realData, competenciaId }: { empty?: boolean; realData?: VolumeDataPoint[]; competenciaId?: string }) {
  const hasReal = realData && realData.some(d => d.nfe + d.cte + d.cteos + d.mdfe + d.nfse > 0)
  const chartData = hasReal ? buildMonthDays(realData, competenciaId) : null

  return (
    <Card className="transition-shadow hover:shadow-md">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-base font-semibold">
              Volume de Documentos
            </CardTitle>
            <CardDescription>
              Documentos capturados nos últimos 30 dias
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {empty && !hasReal ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <Inbox className="size-12 text-muted-foreground/30 mb-4" />
            <p className="text-sm text-muted-foreground">Nenhum dado disponível.</p>
          </div>
        ) : chartData ? (
        <ChartContainer config={lineConfig} className="h-[300px] w-full">
          <LineChart data={chartData} margin={{ top: 4, right: 30, bottom: 0, left: -20 }}>
            <CartesianGrid vertical={false} strokeDasharray="3 3" className="stroke-muted" />
            <XAxis
              dataKey="date"
              tickLine={false}
              axisLine={false}
              tickMargin={8}
              interval={4}
              tick={{ fontSize: 11 }}
            />
            <YAxis
              tickLine={false}
              axisLine={false}
              tickMargin={4}
              tick={{ fontSize: 11 }}
              allowDecimals={false}
            />
            <ChartTooltip content={<ChartTooltipContent />} />
            <ChartLegend content={<ChartLegendContent />} />
            <Line dataKey="nfse" type="monotone" stroke="var(--color-nfse)" strokeWidth={2} dot={{ r: 3, fill: "var(--color-nfse)", strokeWidth: 0 }} activeDot={{ r: 6 }} connectNulls={false} />
            <Line dataKey="mdfe" type="monotone" stroke="var(--color-mdfe)" strokeWidth={2} dot={{ r: 3, fill: "var(--color-mdfe)", strokeWidth: 0 }} activeDot={{ r: 6 }} connectNulls={false} />
            <Line dataKey="cteos" type="monotone" stroke="var(--color-cteos)" strokeWidth={2} dot={{ r: 3, fill: "var(--color-cteos)", strokeWidth: 0 }} activeDot={{ r: 6 }} connectNulls={false} />
            <Line dataKey="cte" type="monotone" stroke="var(--color-cte)" strokeWidth={2.5} dot={{ r: 3, fill: "var(--color-cte)", strokeWidth: 0 }} activeDot={{ r: 7 }} connectNulls={false} />
            <Line dataKey="nfe" type="monotone" stroke="var(--color-nfe)" strokeWidth={2.5} dot={{ r: 3, fill: "var(--color-nfe)", strokeWidth: 0 }} activeDot={{ r: 7 }} connectNulls={false} />
            <Line dataKey="overlap" type="monotone" stroke="var(--color-overlap)" strokeWidth={0} dot={{ r: 6, fill: "var(--color-overlap)", strokeWidth: 2, stroke: "#fff" }} activeDot={{ r: 8 }} connectNulls={false} />
          </LineChart>
        </ChartContainer>
        ) : (
        <ChartContainer config={areaConfig} className="h-[300px] w-full">
          <AreaChart data={mockChartData} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
            <defs>
              <linearGradient id="fillNfe" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--color-nfe)" stopOpacity={0.3} />
                <stop offset="95%" stopColor="var(--color-nfe)" stopOpacity={0.02} />
              </linearGradient>
              <linearGradient id="fillCte" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--color-cte)" stopOpacity={0.3} />
                <stop offset="95%" stopColor="var(--color-cte)" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid vertical={false} strokeDasharray="3 3" className="stroke-muted" />
            <XAxis dataKey="date" tickLine={false} axisLine={false} tickMargin={8} interval="preserveStartEnd" tick={{ fontSize: 11 }} />
            <YAxis tickLine={false} axisLine={false} tickMargin={4} tick={{ fontSize: 11 }} />
            <ChartTooltip content={<ChartTooltipContent indicator="dot" />} />
            <ChartLegend content={<ChartLegendContent />} />
            <Area dataKey="nfe" type="monotone" fill="url(#fillNfe)" stroke="var(--color-nfe)" strokeWidth={2} dot={false} activeDot={{ r: 4, strokeWidth: 0 }} />
            <Area dataKey="cte" type="monotone" fill="url(#fillCte)" stroke="var(--color-cte)" strokeWidth={2} dot={false} activeDot={{ r: 4, strokeWidth: 0 }} />
          </AreaChart>
        </ChartContainer>
        )}
      </CardContent>
    </Card>
  )
}
