"use client"

import { Card, CardContent } from "@/components/ui/card"
import { TrendingUp, TrendingDown } from "lucide-react"
import { cn } from "@/lib/utils"

interface StatCardProps {
  title: string
  value: string | number
  icon: React.ReactNode
  period: string
  trend?: { value: number; label: string }
  badge?: string
  color?: string
  subCounts?: { label: string; value: number; color: string }[]
}

export function StatCard({
  title,
  value,
  icon,
  period,
  trend,
  badge,
  color = "text-primary",
  subCounts,
}: StatCardProps) {
  return (
    <Card className="relative overflow-hidden transition-shadow hover:shadow-md">
      <CardContent className="pt-1">
        <div className="flex items-start justify-between">
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <span className={cn("text-muted-foreground", color)}>{icon}</span>
              <p className="text-sm font-medium text-muted-foreground">{title}</p>
              {badge && (
                <span className="inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-700">
                  {badge}
                </span>
              )}
            </div>
            <div className="flex items-baseline gap-2">
              <p className="text-3xl font-bold tracking-tight">{value}</p>
              {trend && (
                <span
                  className={cn(
                    "inline-flex items-center gap-0.5 text-xs font-medium",
                    trend.value >= 0 ? "text-emerald-600" : "text-red-500"
                  )}
                >
                  {trend.value >= 0 ? (
                    <TrendingUp className="h-3 w-3" />
                  ) : (
                    <TrendingDown className="h-3 w-3" />
                  )}
                  {trend.value >= 0 ? "+" : ""}
                  {trend.value}%
                </span>
              )}
            </div>
            <p className="text-xs text-muted-foreground">{period}</p>
          </div>
        </div>
        {subCounts && subCounts.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2 border-t pt-3">
            {subCounts.map((sub) => (
              <span
                key={sub.label}
                className={cn(
                  "inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-medium",
                  sub.color
                )}
              >
                <span className="font-semibold">{sub.value}</span>
                {sub.label}
              </span>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
