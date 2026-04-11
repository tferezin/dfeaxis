"use client"

import { cn } from "@/lib/utils"

interface ReadOnlyBadgeProps {
  className?: string
  label?: string
}

/**
 * Small presentational badge indicating a component/section is locked.
 * Pure presentational — callers decide when to render it.
 */
export function ReadOnlyBadge({
  className,
  label = "Somente leitura",
}: ReadOnlyBadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border border-red-200 bg-red-50 px-2 py-0.5 text-[11px] font-medium text-red-700",
        className
      )}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-red-600" />
      {label}
    </span>
  )
}
