import React from "react"
import { AlertCircle, Copy, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { toast } from "sonner"
import { cn } from "@/lib/utils"

interface ErrorStateProps {
  message?: string
  requestId?: string
  onRetry?: () => void
  className?: string
}

export function ErrorState({
  message = "Failed to load data",
  requestId,
  onRetry,
  className,
}: ErrorStateProps) {
  const copyRequestId = () => {
    if (requestId) {
      navigator.clipboard.writeText(requestId)
      toast.success("Request ID copied to clipboard")
    }
  }

  return (
    <div
      className={cn(
        "flex min-h-[280px] flex-col items-center justify-center rounded-lg border border-rose-200/50 bg-rose-50/20 dark:bg-rose-950/10 p-8 text-center animate-in fade-in-50",
        className
      )}
    >
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-rose-100 text-rose-600 dark:bg-rose-950 dark:text-rose-400 mb-4">
        <AlertCircle className="h-6 w-6 stroke-[1.5]" />
      </div>
      <h3 className="text-base font-medium text-foreground tracking-tight">Something went wrong</h3>
      <p className="mt-1.5 max-w-sm text-sm text-muted-foreground leading-normal">{message}</p>

      {requestId && (
        <div className="mt-3 flex items-center gap-1.5 rounded-md bg-muted/60 px-2 py-1 font-mono text-xs text-muted-foreground">
          <span>Request ID: {requestId}</span>
          <button
            onClick={copyRequestId}
            type="button"
            className="text-muted-foreground hover:text-foreground transition-colors"
            title="Copy Request ID"
          >
            <Copy className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {onRetry && (
        <Button onClick={onRetry} variant="outline" size="sm" className="mt-4 gap-2">
          <RefreshCw className="h-3.5 w-3.5" />
          Retry
        </Button>
      )}
    </div>
  )
}

