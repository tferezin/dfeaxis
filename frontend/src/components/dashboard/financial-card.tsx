"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { cn } from "@/lib/utils"

interface FinancialItem {
  label: string
  value: string
  amount: number
  color: string
  bgColor: string
}

interface FinancialCardProps {
  title: string
  icon: React.ReactNode
  totalLabel: string
  totalValue: string
  period: string
  items: FinancialItem[]
}

export function FinancialCard({
  title,
  icon,
  totalLabel,
  totalValue,
  period,
  items,
}: FinancialCardProps) {
  const maxAmount = Math.max(...items.map((i) => i.amount))

  return (
    <Card className="transition-shadow hover:shadow-md">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {icon}
            <CardTitle className="text-base font-semibold">{title}</CardTitle>
          </div>
          <span className="text-xs text-muted-foreground">{period}</span>
        </div>
      </CardHeader>
      <CardContent>
        <div className="mb-5">
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            {totalLabel}
          </p>
          <p className="mt-1 text-2xl font-bold tracking-tight">{totalValue}</p>
        </div>
        <div className="space-y-3">
          {items.map((item) => (
            <div key={item.label} className="space-y-1.5">
              <div className="flex items-center justify-between text-sm">
                <div className="flex items-center gap-2">
                  <div className={cn("h-2.5 w-2.5 rounded-full", item.bgColor)} />
                  <span className="text-muted-foreground">{item.label}</span>
                </div>
                <span className="font-semibold tabular-nums">{item.value}</span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                <div
                  className={cn("h-full rounded-full transition-all", item.bgColor)}
                  style={{
                    width: `${maxAmount > 0 ? (item.amount / maxAmount) * 100 : 0}%`,
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
