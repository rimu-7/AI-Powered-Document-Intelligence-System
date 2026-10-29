import React from "react"
import { cn } from "@/lib/utils"

interface StatusBadgeProps {
  status: string | null | undefined
  className?: string
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  if (!status) return null

  const s = status.toUpperCase()

  let colorClasses = "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300 border-zinc-200 dark:border-zinc-700"

  if (["RUNNING", "PROCESSING", "PENDING", "QUEUED", "IN_PROGRESS", "CLAIMED"].includes(s)) {
    colorClasses = "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/60 dark:text-blue-300 dark:border-blue-800"
  } else if (["COMPLETED", "PASSED", "DONE", "APPROVED", "RESOLVED", "MATCHED"].includes(s)) {
    colorClasses = "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-800"
  } else if (["PASSED_WITH_WARNINGS", "WARNING", "ACCEPTED", "AMBIGUOUS", "MISMATCHED"].includes(s)) {
    colorClasses = "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/60 dark:text-amber-300 dark:border-amber-800"
  } else if (["REQUIRES_REVIEW", "OPEN", "REVIEW_REQUIRED"].includes(s)) {
    colorClasses = "bg-purple-50 text-purple-700 border-purple-200 dark:bg-purple-950/60 dark:text-purple-300 dark:border-purple-800"
  } else if (["FAILED", "REJECTED", "ERROR", "CRITICAL", "DUPLICATE"].includes(s)) {
    colorClasses = "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/60 dark:text-rose-300 dark:border-rose-800"
  } else if (["CANCELLED", "STALE", "SUPERSEDED"].includes(s)) {
    colorClasses = "bg-zinc-200 text-zinc-600 border-zinc-300 dark:bg-zinc-800 dark:text-zinc-400 dark:border-zinc-700"
  }

  const label = status.replace(/_/g, " ").toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase())

  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border tracking-wide",
        colorClasses,
        className
      )}
    >
      {label}
    </span>
  )
}
