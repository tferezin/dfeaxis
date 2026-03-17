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

const chartData = generateMockData()

const chartConfig = {
  nfe: {
    label: "NF-e",
    color: "oklch(0.623 0.214 259.815)",
  },
  cte: {
    label: "CT-e",
    color: "oklch(0.696 0.17 162.48)",
  },
} satisfies ChartConfig

export function VolumeChart({ empty = false }: { empty?: boolean }) {
  return (
    <Card className="transition-shadow hover:shadow-md">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-base font-semibold">
              Volume de Documentos
            </CardTitle>
            <CardDescription>
              NF-e e CT-e recebidos nos últimos 30 dias
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {empty ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <Inbox className="size-12 text-muted-foreground/30 mb-4" />
            <p className="text-sm text-muted-foreground">Nenhum dado disponível.</p>
          </div>
        ) : (
        <ChartContainer config={chartConfig} className="h-[300px] w-full">
          <AreaChart
            data={chartData}
            margin={{ top: 4, right: 4, bottom: 0, left: -20 }}
          >
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
            <XAxis
              dataKey="date"
              tickLine={false}
              axisLine={false}
              tickMargin={8}
              interval="preserveStartEnd"
              tick={{ fontSize: 11 }}
            />
            <YAxis
              tickLine={false}
              axisLine={false}
              tickMargin={4}
              tick={{ fontSize: 11 }}
            />
            <ChartTooltip
              content={<ChartTooltipContent indicator="dot" />}
            />
            <ChartLegend content={<ChartLegendContent />} />
            <Area
              dataKey="nfe"
              type="monotone"
              fill="url(#fillNfe)"
              stroke="var(--color-nfe)"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, strokeWidth: 0 }}
            />
            <Area
              dataKey="cte"
              type="monotone"
              fill="url(#fillCte)"
              stroke="var(--color-cte)"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, strokeWidth: 0 }}
            />
          </AreaChart>
        </ChartContainer>
        )}
      </CardContent>
    </Card>
  )
}
