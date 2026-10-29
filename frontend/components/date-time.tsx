import React from "react"
import { formatDate } from "@/lib/format"
import { cn } from "@/lib/utils"

interface DateTimeProps {
  value: string | null | undefined
  className?: string
  pattern?: string
}

export function DateTime({ value, className, pattern = "MMM d, yyyy HH:mm" }: DateTimeProps) {
  if (!value) return <span className="text-muted-foreground">—</span>

  const localText = formatDate(value, pattern)
  let utcText = ""
  try {
    utcText = new Date(value).toUTCString()
  } catch {
    utcText = value
  }

  return (
    <time
      dateTime={value}
      title={`UTC: ${utcText}`}
      className={cn("font-mono text-xs tabular-nums text-muted-foreground cursor-help", className)}
    >
      {localText}
    </time>
  )
}

