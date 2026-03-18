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
  nfe: { label: "NF-e", color: "oklch(0.623 0.214 259.815)" },
  cte: { label: "CT-e", color: "oklch(0.558 0.189 281.325)" },
  mdfe: { label: "MDF-e", color: "oklch(0.696 0.17 162.48)" },
  nfse: { label: "NFS-e", color: "oklch(0.705 0.152 71.519)" },
} satisfies ChartConfig

export interface VolumeDataPoint {
  date: string
  nfe: number
  cte: number
  mdfe: number
  nfse: number
}

function buildLast30Days(rawData: VolumeDataPoint[]): VolumeDataPoint[] {
  const result: VolumeDataPoint[] = []
  const now = new Date()
  const dataMap: Record<string, VolumeDataPoint> = {}
  for (const d of rawData) dataMap[d.date] = d

  for (let i = 29; i >= 0; i--) {
    const date = new Date(now)
    date.setDate(date.getDate() - i)
    const key = date.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })
    result.push(dataMap[key] || { date: key, nfe: 0, cte: 0, mdfe: 0, nfse: 0 })
  }
  return result
}

export function VolumeChart({ empty = false, realData }: { empty?: boolean; realData?: VolumeDataPoint[] }) {
  const hasReal = realData && realData.some(d => d.nfe + d.cte + d.mdfe + d.nfse > 0)
  const chartData = hasReal ? buildLast30Days(realData) : null

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
          <LineChart data={chartData} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
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
            <Line dataKey="nfe" type="monotone" stroke="var(--color-nfe)" strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }} />
            <Line dataKey="cte" type="monotone" stroke="var(--color-cte)" strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }} />
            <Line dataKey="mdfe" type="monotone" stroke="var(--color-mdfe)" strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }} />
            <Line dataKey="nfse" type="monotone" stroke="var(--color-nfse)" strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }} />
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
