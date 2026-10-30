import React from "react"
import { formatMoney } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { CurrencyCode } from "@/lib/api/types"
import { Badge } from "@/components/ui/badge"
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from "@/components/ui/tooltip"

export interface MoneyProps {
  value: string | number | null | undefined
  currency: CurrencyCode | null
  raw?: string | null
  className?: string
}

export function Money({ value, currency, raw, className }: MoneyProps) {
  const formatted = formatMoney(value, currency, raw)

  if (
    currency === null &&
    value !== null &&
    value !== undefined &&
    value !== ""
  ) {
    const symbol = raw || ""
    const tooltipText = symbol
      ? `Currency not confirmed – symbol '${symbol}' is used by several currencies`
      : "Currency not confirmed"

    return (
      <span
        className={cn(
          "inline-flex items-center gap-1.5 font-mono font-medium text-foreground tabular-nums",
          className
        )}
      >
        <span>{formatted}</span>
        <Tooltip>
          <TooltipTrigger
            render={
              <Badge
                variant="outline"
                className="h-4 cursor-help border-muted-foreground/30 px-1 py-0 font-sans text-[9px] font-normal text-muted-foreground select-none hover:bg-muted"
              />
            }
          >
            unconfirmed
          </TooltipTrigger>
          <TooltipContent>{tooltipText}</TooltipContent>
        </Tooltip>
      </span>
    )
  }

  return (
    <span
      className={cn(
        "font-mono font-medium text-foreground tabular-nums",
        className
      )}
    >
      {formatted}
    </span>
  )
}
