"use client"

import React, { use, useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import {
  AlertTriangle,
  ArrowLeftRight,
  Download,
  FileSpreadsheet,
  FileText,
  Loader2,
  RotateCw,
  XCircle,
} from "lucide-react"
import {
  useComparison,
  useComparisonFindings,
  useRerunComparison,
} from "@/features/comparisons/hooks"
import {
  comparisonsApi,
  type ComparisonOut,
  type FindingStatus,
} from "@/features/comparisons/api"
import { RecordCard } from "@/features/comparisons/components/record-card"
import { kindLabel, sideNames, statusMeta } from "@/features/comparisons/labels"
import { useCurrentUser } from "@/features/auth/hooks"
import { hasPermission } from "@/lib/permissions"
import { cn } from "@/lib/utils"
import { PageHeader } from "@/components/page-header"
import { ErrorState } from "@/components/error-state"
import { DateTime } from "@/components/date-time"
import { Button } from "@/components/ui/button"

const PER_PAGE = 25

type Tile = {
  status: FindingStatus
  count: number
  tone: string
}

function tiles(comp: ComparisonOut): Tile[] {
  const s = (comp.summary_json ?? {}) as Record<string, number | undefined>
  const n = (...keys: string[]) => {
    for (const k of keys) if (typeof s[k] === "number") return s[k] as number
    return 0
  }
  const list: Tile[] = [
    {
      status: "MATCH",
      count: n("matched_count"),
      tone: "text-emerald-600 dark:text-emerald-400",
    },
    {
      status: "MISMATCH",
      count: n("mismatched_count"),
      tone: "text-rose-600 dark:text-rose-400",
    },
    {
      status: "AMBIGUOUS",
      count: n("ambiguous_count"),
      tone: "text-violet-600 dark:text-violet-400",
    },
    {
      status: "MISSING_RIGHT",
      count: n("missing_right_count", "missing_in_spreadsheet_count"),
      tone: "text-amber-600 dark:text-amber-400",
    },
    {
      status: "MISSING_LEFT",
      count: n("missing_left_count", "missing_in_pdf_count"),
      tone: "text-amber-600 dark:text-amber-400",
    },
  ]
  if (comp.comparison_type === "PDF_SPREADSHEET")
    list.push({
      status: "DUPLICATE",
      count: n("duplicate_count"),
      tone: "text-zinc-600 dark:text-zinc-300",
    })
  return list
}

function RecordsSection({ comp }: { comp: ComparisonOut }) {
  const [filter, setFilter] = useState<FindingStatus | null>(null)
  const [offset, setOffset] = useState(0)
  const kind = comp.comparison_type
  const sides = sideNames(comp)
  const ready = comp.status === "COMPLETED" || comp.status === "STALE"
  const { data, isLoading, isPlaceholderData } = useComparisonFindings(
    comp.id,
    {
      records_only: true,
      finding_status: filter ?? undefined,
      limit: PER_PAGE,
      offset,
    },
    { ready }
  )
  const records = data?.items ?? []
  const total = data?.total ?? 0
  const all = tiles(comp)
  const recordsTotal = all.reduce((a, t) => a + t.count, 0)

  const choose = (status: FindingStatus | null) => {
    setFilter((f) => (f === status ? null : status))
    setOffset(0)
  }

  return (
    <div className="space-y-4">
      <div
        className={cn(
          "grid grid-cols-2 gap-2 sm:grid-cols-3",
          all.length === 6 ? "lg:grid-cols-6" : "lg:grid-cols-5"
        )}
        role="group"
        aria-label="Filter results"
      >
        {all.map((t) => {
          const meta = statusMeta(t.status, kind)
          const active = filter === t.status
          return (
            <button
              key={t.status}
              type="button"
              onClick={() => choose(t.status)}
              aria-pressed={active}
              title={meta.help}
              className={cn(
                "rounded-lg border bg-card p-3 text-left transition-colors hover:border-primary/40",
                active && "border-primary ring-1 ring-primary/30",
                t.count === 0 && !active && "opacity-60"
              )}
            >
              <div className="truncate text-[11px] font-medium text-muted-foreground">
                {meta.label}
              </div>
              <div
                className={cn(
                  "mt-1 text-xl font-bold tabular-nums",
                  t.count > 0 ? t.tone : "text-muted-foreground"
                )}
              >
                {t.count}
              </div>
            </button>
          )
        })}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
        <span>
          {filter
            ? `${total} ${total === 1 ? "result" : "results"}: ${statusMeta(filter, kind).label}`
            : `${recordsTotal} ${recordsTotal === 1 ? "result" : "results"}. Click a card to see every field.`}
        </span>
        {filter && (
          <button
            type="button"
            onClick={() => choose(null)}
            className="underline underline-offset-2 hover:text-foreground"
          >
            Show all
          </button>
        )}
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-20 animate-pulse rounded-lg bg-muted" />
          ))}
        </div>
      ) : records.length === 0 ? (
        <div className="rounded-lg border bg-card py-12 text-center text-xs text-muted-foreground">
          {filter
            ? `Nothing is "${statusMeta(filter, kind).label}".`
            : "No invoices were found to compare. Check that both documents have extracted invoices."}
        </div>
      ) : (
        <div className={cn("space-y-2", isPlaceholderData && "opacity-60")}>
          {records.map((r) => (
            <RecordCard
              key={r.id}
              comparisonId={comp.id}
              record={r}
              kind={kind}
              sides={sides}
            />
          ))}
        </div>
      )}

      {total > PER_PAGE && (
        <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
          <span>
            {offset + 1}–{Math.min(offset + PER_PAGE, total)} of {total}
          </span>
          <div className="flex gap-1.5">
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-xs"
              disabled={offset === 0 || isPlaceholderData}
              onClick={() => setOffset(Math.max(0, offset - PER_PAGE))}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-xs"
              disabled={offset + PER_PAGE >= total || isPlaceholderData}
              onClick={() => setOffset(offset + PER_PAGE)}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

function DocumentsLine({ comp }: { comp: ComparisonOut }) {
  const docs = comp.documents ?? []
  const left = docs.filter((d) => d.side === "left")
  const right = docs.filter((d) => d.side === "right")
  const chip = (d: (typeof docs)[number]) => {
    const Icon = ["XLSX", "XLS", "CSV"].includes(d.file_kind)
      ? FileSpreadsheet
      : FileText
    return d.deleted ? (
      <span
        key={d.id}
        className="inline-flex items-center gap-1 text-muted-foreground line-through"
      >
        <Icon className="h-3.5 w-3.5" /> {d.filename}
      </span>
    ) : (
      <Link
        key={d.id}
        href={`/documents/${d.id}`}
        className="inline-flex min-w-0 items-center gap-1 font-medium text-foreground hover:underline"
      >
        <Icon className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <span className="truncate">{d.filename}</span>
      </Link>
    )
  }
  if (!docs.length) return null
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-lg border bg-card px-4 py-3 text-xs">
      <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
        {left.map(chip)}
      </div>
      <ArrowLeftRight
        className="h-4 w-4 shrink-0 text-muted-foreground"
        aria-label="compared with"
      />
      <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
        {right.map(chip)}
      </div>
    </div>
  )
}

export default function ComparisonResultsPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = use(params)
  const router = useRouter()
  const { data: user } = useCurrentUser()
  const canRun = hasPermission(user?.role, "COMPARE_RUN")
  const { data: comp, isLoading, isError, error, refetch } = useComparison(id)
  const { mutate: rerun, isPending: rerunning } = useRerunComparison()

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="h-16 animate-pulse rounded-lg bg-muted" />
        <div className="h-20 animate-pulse rounded-lg bg-muted" />
        <div className="h-64 animate-pulse rounded-lg bg-muted" />
      </div>
    )
  }

  if (isError || !comp) {
    return (
      <ErrorState
        message={(error as any)?.message || "Comparison not found"}
        requestId={(error as any)?.requestId}
        onRetry={() => refetch()}
      />
    )
  }

  const running = comp.status === "QUEUED" || comp.status === "RUNNING"
  const done = comp.status === "COMPLETED" || comp.status === "STALE"
  const runAgain = () =>
    rerun(comp.id, {
      onSuccess: (res) => router.push(`/compare/${res.comparison_id}`),
    })
  const rerunButton = canRun && !running && (
    <Button
      size="sm"
      variant={comp.status === "COMPLETED" ? "outline" : "default"}
      className="gap-1.5 text-xs"
      disabled={rerunning}
      onClick={runAgain}
    >
      {rerunning ? (
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
      ) : (
        <RotateCw className="h-3.5 w-3.5" />
      )}
      Run again
    </Button>
  )

  return (
    <div className="space-y-5">
      <PageHeader
        title={kindLabel(comp.comparison_type)}
        description={
          comp.comparison_type === "PDF_SPREADSHEET"
            ? "Every invoice in the PDFs checked against the spreadsheet rows, by invoice number and supplier."
            : "Every invoice in one document checked against the other, by invoice number and supplier."
        }
      >
        {done && (
          <a href={comparisonsApi.getExportCsvUrl(comp.id)} download>
            <Button variant="outline" size="sm" className="gap-1.5 text-xs">
              <Download className="h-3.5 w-3.5" /> Export CSV
            </Button>
          </a>
        )}
        {rerunButton}
      </PageHeader>

      <DocumentsLine comp={comp} />

      <p className="-mt-2 text-[11px] text-muted-foreground">
        Started <DateTime value={comp.created_at} />
        {comp.completed_at && (
          <>
            {" · "}finished <DateTime value={comp.completed_at} />
          </>
        )}
        {comp.parameters_json?.amount_tolerance != null &&
          ` · amounts may differ by up to ${comp.parameters_json.amount_tolerance}`}
      </p>

      {comp.status === "STALE" && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-amber-800 dark:text-amber-300">
          <div className="flex items-start gap-2.5 text-xs">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>
              <strong>Out of date.</strong> The data changed after this ran
              {comp.stale_reason ? ` (${comp.stale_reason})` : ""}. Run it again
              to compare the current values.
            </span>
          </div>
        </div>
      )}

      {running ? (
        <div className="flex flex-col items-center gap-3 rounded-lg border bg-card py-16 text-center">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
          <div className="space-y-1">
            <p className="text-sm font-medium">
              {comp.status === "QUEUED" ? "Waiting to start…" : "Comparing…"}
            </p>
            <p className="text-xs text-muted-foreground">
              Results appear here automatically. You can leave this page.
            </p>
          </div>
        </div>
      ) : comp.status === "FAILED" ? (
        <div className="flex flex-col items-center gap-3 rounded-lg border border-destructive/30 bg-destructive/5 py-12 text-center">
          <XCircle className="h-6 w-6 text-destructive" />
          <div className="max-w-md space-y-1 px-4">
            <p className="text-sm font-medium">The comparison did not finish</p>
            <p className="text-xs text-muted-foreground">
              {comp.error_message}
            </p>
          </div>
          {comp.processing_run_id && (
            <Link
              href={`/jobs/${comp.processing_run_id}`}
              className="text-xs underline underline-offset-2"
            >
              See job details
            </Link>
          )}
        </div>
      ) : (
        <RecordsSection key={comp.id} comp={comp} />
      )}
    </div>
  )
}
