"use client"

import React, { useEffect } from "react"
import { Button } from "@/components/ui/button"
import { AlertCircle, RefreshCw, Home } from "lucide-react"
import Link from "next/link"

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    console.error("Unhandled runtime error:", error)
  }, [error])

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background p-6 text-center">
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-rose-100 text-rose-600 dark:bg-rose-950 dark:text-rose-400">
        <AlertCircle className="h-6 w-6 stroke-[1.5]" />
      </div>
      <h2 className="text-xl font-bold tracking-tight">Something went wrong</h2>
      <p className="mt-2 max-w-md text-sm text-muted-foreground">
        {error.message ||
          "An unexpected error occurred while rendering the page."}
      </p>

      {error.digest && (
        <div className="mt-3 rounded bg-muted px-2 py-1 font-mono text-[11px] text-muted-foreground">
          Digest: {error.digest}
        </div>
      )}

      <div className="mt-6 flex items-center gap-3">
        <Button onClick={reset} variant="default" size="sm" className="gap-2">
          <RefreshCw className="h-4 w-4" /> Try again
        </Button>
        <Link href="/">
          <Button variant="outline" size="sm" className="gap-2">
            <Home className="h-4 w-4" /> Go to Dashboard
          </Button>
        </Link>
      </div>
    </div>
  )
}
