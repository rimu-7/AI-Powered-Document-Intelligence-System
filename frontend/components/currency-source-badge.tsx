import React from "react"
import { Sparkles } from "lucide-react"
import type { CurrencySource } from "@/lib/api/types"
import { cn } from "@/lib/utils"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"

const LABELS: Record<
  Exclude<CurrencySource, "HUMAN">,
  { label: string; fallback: string }
> = {
  PRINTED: { label: "printed", fallback: "Read from the invoice" },
  DOCUMENT_CONTEXT: {
    label: "auto · document",
    fallback: "Decided from the supplier's country on the document",
  },
  SUPPLIER_HISTORY: {
    label: "auto · supplier",
    fallback: "Same currency as this supplier's earlier invoices",
  },
  ORGANIZATION_RULE: {
    label: "auto · rule",
    fallback: "Decided by your organization's currency rule",
  },
  LEARNED: {
    label: "auto · learned",
    fallback: "Learned from how reviewers resolved this symbol",
  },
  ORGANIZATION_DEFAULT: {
    label: "auto · default",
    fallback: "Your organization's default currency",
  },
}

export function isAutoCurrency(source: CurrencySource | null | undefined) {
  return !!source && source !== "PRINTED" && source !== "HUMAN"
}

/** Shows how a currency was decided; human corrections use the "corrected" tag instead. */
export function CurrencySourceBadge({
  source,
  reason,
  className,
}: {
  source: CurrencySource | null | undefined
  reason?: string | null
  className?: string
}) {
  if (!source || source === "HUMAN") return null
  const { label, fallback } = LABELS[source]
  const auto = isAutoCurrency(source)
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <span
            className={cn(
              "inline-flex cursor-help items-center gap-0.5 rounded px-1 font-mono text-[10px] font-medium select-none",
              auto
                ? "bg-sky-500/10 text-sky-700 dark:text-sky-400"
                : "bg-muted text-muted-foreground",
              className
            )}
          />
        }
        onClick={(e) => e.stopPropagation()}
      >
        {auto && <Sparkles className="h-2.5 w-2.5" aria-hidden />}
        {label}
      </TooltipTrigger>
      <TooltipContent>{reason || fallback}</TooltipContent>
    </Tooltip>
  )
}
