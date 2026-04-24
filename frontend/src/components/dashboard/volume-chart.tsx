"use client"

import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts"
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

function generateMockData(): VolumeDataPoint[] {
  const data: VolumeDataPoint[] = []
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
      cteos: Math.floor(Math.random() * 15 + 3),
      mdfe: Math.floor(Math.random() * 10 + 2),
      nfse: Math.floor(Math.random() * 20 + 5),
    })
  }
  return data
}

const areaConfig = {
  nfe: { label: "NF-e", color: "#3b82f6" },
  cte: { label: "CT-e", color: "#8b5cf6" },
  cteos: { label: "CT-e OS", color: "#d946ef" },
  mdfe: { label: "MDF-e", color: "#10b981" },
  nfse: { label: "NFS-e", color: "#f59e0b" },
} satisfies ChartConfig

export interface VolumeDataPoint {
  date: string
  nfe: number
  cte: number
  cteos: number
  mdfe: number
  nfse: number
}

function buildMonthDays(rawData: VolumeDataPoint[], competenciaId?: string): VolumeDataPoint[] {
  const result: VolumeDataPoint[] = []
  let year: number, month: number
  if (competenciaId && /^\d{4}-\d{2}$/.test(competenciaId)) {
    const [y, m] = competenciaId.split("-").map(Number)
    year = y
    month = m - 1
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
    result.push(d)
  }
  return result
}

const mockChartData = generateMockData()

export function VolumeChart({ empty = false, realData, competenciaId }: { empty?: boolean; realData?: VolumeDataPoint[]; competenciaId?: string }) {
  const hasReal = realData && realData.some(d => d.nfe + d.cte + d.cteos + d.mdfe + d.nfse > 0)
  const chartData: VolumeDataPoint[] = hasReal ? buildMonthDays(realData, competenciaId) : mockChartData

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
        ) : (
        <ChartContainer config={areaConfig} className="h-[300px] w-full">
          <AreaChart data={chartData} margin={{ top: 4, right: 30, bottom: 0, left: -20 }}>
            <defs>
              <linearGradient id="fillNfe" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--color-nfe)" stopOpacity={0.7} />
                <stop offset="100%" stopColor="var(--color-nfe)" stopOpacity={0.2} />
              </linearGradient>
              <linearGradient id="fillCte" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--color-cte)" stopOpacity={0.7} />
                <stop offset="100%" stopColor="var(--color-cte)" stopOpacity={0.2} />
              </linearGradient>
              <linearGradient id="fillCteos" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--color-cteos)" stopOpacity={0.7} />
                <stop offset="100%" stopColor="var(--color-cteos)" stopOpacity={0.2} />
              </linearGradient>
              <linearGradient id="fillMdfe" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--color-mdfe)" stopOpacity={0.7} />
                <stop offset="100%" stopColor="var(--color-mdfe)" stopOpacity={0.2} />
              </linearGradient>
              <linearGradient id="fillNfse" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--color-nfse)" stopOpacity={0.7} />
                <stop offset="100%" stopColor="var(--color-nfse)" stopOpacity={0.2} />
              </linearGradient>
            </defs>
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
            <Area dataKey="nfe" type="monotone" stackId="1" fill="url(#fillNfe)" stroke="var(--color-nfe)" strokeWidth={1.5} />
            <Area dataKey="cte" type="monotone" stackId="1" fill="url(#fillCte)" stroke="var(--color-cte)" strokeWidth={1.5} />
            <Area dataKey="cteos" type="monotone" stackId="1" fill="url(#fillCteos)" stroke="var(--color-cteos)" strokeWidth={1.5} />
            <Area dataKey="mdfe" type="monotone" stackId="1" fill="url(#fillMdfe)" stroke="var(--color-mdfe)" strokeWidth={1.5} />
            <Area dataKey="nfse" type="monotone" stackId="1" fill="url(#fillNfse)" stroke="var(--color-nfse)" strokeWidth={1.5} />
          </AreaChart>
        </ChartContainer>
        )}
      </CardContent>
    </Card>
  )
}
