import React from "react"
import { formatMoney } from "@/lib/format"
import { cn } from "@/lib/utils"

interface MoneyProps {
  value: string | number | null | undefined
  currency?: string | null
  className?: string
}

export function Money({ value, currency = "EUR", className }: MoneyProps) {
  const formatted = formatMoney(value, currency || "EUR")

  return (
    <span className={cn("font-mono tabular-nums font-medium text-foreground", className)}>
      {formatted}
    </span>
  )
}

