import React from "react"
import { formatBytes } from "@/lib/format"
import { cn } from "@/lib/utils"

interface BytesProps {
  bytes: number | null | undefined
  className?: string
}

export function Bytes({ bytes, className }: BytesProps) {
  return (
    <span className={cn("font-mono text-xs tabular-nums text-muted-foreground", className)}>
      {formatBytes(bytes)}
    </span>
  )
}

