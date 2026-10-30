"use client"

import React, { Suspense } from "react"
import { PageHeader } from "@/components/page-header"
import { useComparisonsList } from "@/features/comparisons/hooks"
import { useCurrentUser } from "@/features/auth/hooks"
import { hasPermission } from "@/lib/permissions"
import { StatusBadge } from "@/components/status-badge"
import { DateTime } from "@/components/date-time"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/error-state"
import { Button } from "@/components/ui/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { GitCompare, Plus, ExternalLink } from "lucide-react"
import Link from "next/link"

import { useRouter } from "next/navigation"
import type { ComparisonOut } from "@/features/comparisons/api"
import { kindLabel } from "@/features/comparisons/labels"

function docNames(c: ComparisonOut): string {
  const docs = c.documents ?? []
  const left = docs.filter((d) => d.side === "left").map((d) => d.filename)
  const right = docs.filter((d) => d.side === "right").map((d) => d.filename)
  const l =
    left.length > 2 ? `${left[0]} + ${left.length - 1} more` : left.join(", ")
  return [l, right.join(", ")].filter(Boolean).join("  ↔  ")
}

function SummaryChips({ c }: { c: ComparisonOut }) {
  const s = (c.summary_json ?? {}) as Record<string, number | undefined>
  if (c.status === "QUEUED" || c.status === "RUNNING")
    return <span className="text-muted-foreground">In progress…</span>
  if (c.status === "FAILED")
    return <span className="text-destructive">Did not finish</span>
  const missing =
    (s.missing_left_count ?? s.missing_in_pdf_count ?? 0) +
    (s.missing_right_count ?? s.missing_in_spreadsheet_count ?? 0)
  const chips: [number, string, string][] = [
    [s.matched_count ?? 0, "matched", "text-emerald-600 dark:text-emerald-400"],
    [s.mismatched_count ?? 0, "different", "text-rose-600 dark:text-rose-400"],
    [
      s.ambiguous_count ?? 0,
      "to confirm",
      "text-violet-600 dark:text-violet-400",
    ],
    [missing, "missing", "text-amber-600 dark:text-amber-400"],
  ]
  return (
    <span className="flex flex-wrap gap-x-3 gap-y-0.5">
      {chips
        .filter(([n], i) => n > 0 || i === 0)
        .map(([n, label, tone]) => (
          <span key={label} className={`font-medium ${tone}`}>
            {n} {label}
          </span>
        ))}
    </span>
  )
}

function CompareContent() {
  const router = useRouter()
  const { data: user } = useCurrentUser()
  const { data, isLoading, isError, error, refetch } = useComparisonsList({
    limit: 50,
  })
  const comparisons = data?.items ?? []

  return (
    <div className="space-y-6">
      <PageHeader
        title="Comparisons"
        description="Check two documents against each other, or check invoices against a spreadsheet register."
      >
        {hasPermission(user?.role, "COMPARE_RUN") && (
          <Link href="/compare/new">
            <Button className="gap-2">
              <Plus className="h-4 w-4" />
              <span>New comparison</span>
            </Button>
          </Link>
        )}
      </PageHeader>

      {isLoading ? (
        <div className="space-y-2 rounded-lg border p-4">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="h-10 animate-pulse rounded bg-muted" />
          ))}
        </div>
      ) : isError ? (
        <ErrorState
          message={(error as any)?.message || "Failed to load comparisons"}
          requestId={(error as any)?.requestId}
          onRetry={() => refetch()}
        />
      ) : comparisons.length === 0 ? (
        <EmptyState
          icon={GitCompare}
          title="No comparisons yet"
          description="Create a PDF-to-PDF comparison or reconcile invoices against a spreadsheet register."
          actionLabel={
            hasPermission(user?.role, "COMPARE_RUN")
              ? "Start a comparison"
              : undefined
          }
          onAction={
            hasPermission(user?.role, "COMPARE_RUN")
              ? () => router.push("/compare/new")
              : undefined
          }
        />
      ) : (
        <div className="space-y-4">
          {/* Mobile / Tablet Container Cards */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:hidden">
            {comparisons.map((c) => {
              return (
                <div
                  key={c.id}
                  className="flex flex-col justify-between space-y-3 rounded-lg border bg-card p-4 transition-colors hover:border-primary/40"
                >
                  <div className="space-y-2">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <span className="text-xs font-semibold text-foreground">
                          {kindLabel(c.comparison_type)}
                        </span>
                        <p className="mt-0.5 truncate text-[11px] text-muted-foreground">
                          {docNames(c)}
                        </p>
                      </div>
                      <StatusBadge status={c.status} />
                    </div>

                    <div className="pt-1 text-xs">
                      <SummaryChips c={c} />
                    </div>
                  </div>

                  <div className="flex items-center justify-between border-t pt-2 text-[11px] text-muted-foreground">
                    <DateTime value={c.created_at} />
                    <Link href={`/compare/${c.id}`}>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 gap-1 px-2 text-xs"
                      >
                        Open <ExternalLink className="h-3 w-3" />
                      </Button>
                    </Link>
                  </div>
                </div>
              )
            })}
          </div>

          {/* Desktop Table View */}
          <div className="hidden overflow-hidden rounded-lg border bg-card lg:block">
            <Table>
              <TableHeader className="bg-muted/40">
                <TableRow>
                  <TableHead>Type</TableHead>
                  <TableHead>Documents</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Summary</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {comparisons.map((c) => {
                  return (
                    <TableRow
                      key={c.id}
                      className="transition-colors hover:bg-muted/30"
                    >
                      <TableCell className="text-xs font-medium whitespace-nowrap">
                        {kindLabel(c.comparison_type)}
                      </TableCell>
                      <TableCell className="max-w-[340px] truncate text-xs text-muted-foreground">
                        {docNames(c)}
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={c.status} />
                      </TableCell>
                      <TableCell className="text-xs">
                        <SummaryChips c={c} />
                      </TableCell>
                      <TableCell>
                        <DateTime value={c.created_at} />
                      </TableCell>
                      <TableCell className="text-right">
                        <Link href={`/compare/${c.id}`}>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-8 gap-1 text-xs"
                          >
                            Open <ExternalLink className="h-3.5 w-3.5" />
                          </Button>
                        </Link>
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        </div>
      )}
    </div>
  )
}

export default function ComparePage() {
  return (
    <Suspense
      fallback={<div className="h-96 animate-pulse rounded-lg bg-card" />}
    >
      <CompareContent />
    </Suspense>
  )
}
