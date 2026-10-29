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

function CompareContent() {
  const router = useRouter()
  const { data: user } = useCurrentUser()
  const { data, isLoading, isError, error, refetch } = useComparisonsList({ limit: 50 })
  const comparisons = data?.items ?? []

  return (
    <div className="space-y-6">
      <PageHeader
        title="Comparisons & Reconciliations"
        description="Verify document pairs (PDF ↔ PDF price checks) or reconcile batches against financial registers (PDF ↔ Spreadsheet)."
      >
        {hasPermission(user?.role, "COMPARE_RUN") && (
          <Link href="/compare/new">
            <Button className="gap-2">
              <Plus className="h-4 w-4" />
              <span>New Comparison / Reconciliation</span>
            </Button>
          </Link>
        )}
      </PageHeader>

      {isLoading ? (
        <div className="space-y-2 border rounded-lg p-4">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="h-10 bg-muted animate-pulse rounded" />
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
          actionLabel={hasPermission(user?.role, "COMPARE_RUN") ? "Start Comparison Wizard" : undefined}
          onAction={hasPermission(user?.role, "COMPARE_RUN") ? () => router.push("/compare/new") : undefined}
        />
      ) : (
        <div className="border rounded-lg overflow-hidden bg-card">
          <Table>
            <TableHeader className="bg-muted/40">
              <TableRow>
                <TableHead>Type</TableHead>
                <TableHead>Strategy</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Summary</TableHead>
                <TableHead>Created</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {comparisons.map((c) => {
                const s = (c.summary_json || {}) as Record<string, any>
                const matched = s.matched_count ?? s.match_count ?? 0
                const mismatched = s.mismatched_count ?? s.mismatch_count ?? 0
                return (
                  <TableRow key={c.id} className="hover:bg-muted/30 transition-colors">
                    <TableCell className="font-mono text-xs font-medium">
                      <span className="uppercase">{c.comparison_type}</span>
                    </TableCell>
                    <TableCell className="text-xs font-mono text-muted-foreground">
                      {c.matching_strategy}
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={c.status} />
                    </TableCell>
                    <TableCell className="text-xs">
                      <span className="text-emerald-600 font-medium">{matched} matched</span>
                      {mismatched > 0 && (
                        <span className="text-rose-600 font-medium ml-2">
                          {mismatched} mismatched
                        </span>
                      )}
                    </TableCell>
                    <TableCell>
                      <DateTime value={c.created_at} />
                    </TableCell>
                    <TableCell className="text-right">
                      <Link href={`/compare/${c.id}`}>
                        <Button variant="ghost" size="sm" className="h-8 gap-1 text-xs">
                          Inspect <ExternalLink className="h-3.5 w-3.5" />
                        </Button>
                      </Link>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}

export default function ComparePage() {
  return (
    <Suspense fallback={<div className="h-96 rounded-lg bg-card animate-pulse" />}>
      <CompareContent />
    </Suspense>
  )
}
