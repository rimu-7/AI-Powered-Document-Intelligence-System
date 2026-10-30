"use client"

import React from "react"
import Link from "next/link"
import {
  AlertCircle,
  CheckCircle2,
  FileText,
  Loader2,
  TriangleAlert,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { isTerminal, useActiveJobs } from "@/features/jobs/hooks"
import type { ActiveJob } from "@/features/jobs/api"

function stageLabel(job: ActiveJob): string {
  const pages =
    job.pages_total > 0 ? ` ${job.pages_completed}/${job.pages_total}` : ""
  switch (job.state) {
    case "QUEUED":
      return "Queued"
    case "PREPROCESSING":
      return "Checking file"
    case "PARSING":
      return job.pages_total > 0 ? `Reading pages${pages}` : "Reading document"
    case "EXTRACTING":
      return "Extracting invoices"
    case "VALIDATING":
      return "Validating"
    case "INDEXING":
      return "Indexing for search"
    case "COMPARING":
      return "Comparing"
    default:
      return job.state
  }
}

function plural(n: number, word: string) {
  return `${n} ${word}${n === 1 ? "" : "s"}`
}

function elapsed(from: string): string {
  const s = Math.max(
    0,
    Math.round((Date.now() - new Date(from).getTime()) / 1000)
  )
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`
}

function Outcome({ job }: { job: ActiveJob }) {
  if (job.state === "FAILED") {
    return (
      <Link
        href={`/jobs/${job.job_id}`}
        className="inline-flex items-center gap-1 text-rose-600 hover:underline dark:text-rose-400"
      >
        <AlertCircle className="h-3.5 w-3.5" />
        Failed
        {job.sanitized_error_message ? `: ${job.sanitized_error_message}` : ""}
      </Link>
    )
  }
  if (job.state === "CANCELLED") {
    return <span className="text-muted-foreground">Cancelled</span>
  }
  if (job.open_reviews > 0) {
    return (
      <Link
        href={`/documents/${job.document_id}`}
        className="inline-flex items-center gap-1 font-medium text-amber-700 hover:underline dark:text-amber-400"
      >
        <TriangleAlert className="h-3.5 w-3.5" />
        {plural(job.open_reviews, "invoice")} added to the queue
      </Link>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 text-emerald-700 dark:text-emerald-400">
      <CheckCircle2 className="h-3.5 w-3.5" />
      Done
      {job.invoices > 0
        ? ` · ${plural(job.invoices, "invoice")}, no review needed`
        : ""}
    </span>
  )
}

/** Uploads on their way to the review queue, updated live. */
export function ProcessingPanel({ className }: { className?: string }) {
  const { data: jobs = [] } = useActiveJobs()
  if (jobs.length === 0) return null
  const running = jobs.filter((j) => !isTerminal(j.state)).length

  return (
    <section
      aria-label="Documents being processed"
      className={cn("overflow-hidden rounded-lg border bg-card", className)}
    >
      <header className="flex items-center justify-between border-b bg-muted/30 px-4 py-2.5">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          {running > 0 && (
            <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
          )}
          {running > 0
            ? `Processing ${plural(running, "document")}`
            : "Recently processed"}
        </h2>
        <span className="text-[11px] text-muted-foreground">
          Invoices appear in the queue when processing finishes
        </span>
      </header>
      <ul className="divide-y" aria-live="polite">
        {jobs.map((job) => {
          const done = isTerminal(job.state)
          const percent = Math.round(Number(job.progress_percent) || 0)
          return (
            <li
              key={job.job_id}
              className="flex flex-col gap-2 px-4 py-3 text-xs sm:flex-row sm:items-center sm:gap-4"
            >
              <Link
                href={`/documents/${job.document_id}`}
                className="flex min-w-0 items-center gap-2 font-medium hover:underline sm:w-2/5"
                title={job.filename}
              >
                <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                <span className="truncate">{job.filename}</span>
              </Link>
              {done ? (
                <div className="min-w-0 flex-1 truncate">
                  <Outcome job={job} />
                </div>
              ) : (
                <div className="flex min-w-0 flex-1 items-center gap-3">
                  <div
                    className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted"
                    role="progressbar"
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={percent}
                    aria-label={`${job.filename}: ${stageLabel(job)}`}
                  >
                    <div
                      className={cn(
                        "h-full rounded-full bg-primary transition-[width] duration-500",
                        percent === 0 && "w-1/3 animate-pulse"
                      )}
                      style={percent > 0 ? { width: `${percent}%` } : undefined}
                    />
                  </div>
                  <span className="w-36 shrink-0 truncate text-muted-foreground">
                    {stageLabel(job)}
                  </span>
                  <span className="w-12 shrink-0 text-right font-mono text-muted-foreground tabular-nums">
                    {elapsed(job.created_at)}
                  </span>
                </div>
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}
