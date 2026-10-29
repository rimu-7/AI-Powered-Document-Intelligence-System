"use client"

import React, { use, useState } from "react"
import { useComparison, useComparisonFindings } from "@/features/comparisons/hooks"
import { comparisonsApi } from "@/features/comparisons/api"
import { PageHeader } from "@/components/page-header"
import { StatusBadge } from "@/components/status-badge"
import { ErrorState } from "@/components/error-state"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Download,
  AlertTriangle,
  RotateCw,
} from "lucide-react"
import Link from "next/link"

export default function ComparisonResultsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  const [statusFilter, setStatusFilter] = useState<string>("all")

  const { data: comp, isLoading, isError, error, refetch } = useComparison(id)
  const { data: findingsData, isLoading: findingsLoading } = useComparisonFindings(id, {
    status: statusFilter !== "all" ? statusFilter : undefined,
    limit: 100,
  })

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="h-24 bg-muted animate-pulse rounded-lg" />
        <div className="h-64 bg-muted animate-pulse rounded-lg" />
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

  const s = (comp.summary_json || {}) as Record<string, any>
  const matched = Number(s.matched_count ?? s.match_count ?? 0)
  const mismatched = Number(s.mismatched_count ?? s.mismatch_count ?? 0)
  const missingLeft = Number(s.missing_in_pdf_count ?? s.missing_in_left_count ?? 0)
  const missingRight = Number(s.missing_in_spreadsheet_count ?? s.missing_in_right_count ?? 0)
  const ambiguous = Number(s.ambiguous_count ?? 0)
  const duplicate = Number(s.duplicate_count ?? 0)

  const isStale = comp.status === "STALE"
  const isReconciliation = comp.comparison_type === "PDF_SPREADSHEET"
  const findings = findingsData?.items ?? []

  return (
    <div className="space-y-6">
      {/* Stale Warning Banner (§6.4) */}
      {isStale && (
        <div className="p-4 rounded-lg bg-amber-500/15 border border-amber-500/30 text-amber-800 dark:text-amber-300 flex items-center justify-between gap-4">
          <div className="flex items-center gap-2.5 text-xs font-medium">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <span>
              This comparison is <strong>stale</strong> because an invoice was corrected after this run was completed.
            </span>
          </div>
          <Link href="/compare/new">
            <Button size="sm" variant="outline" className="h-8 gap-1.5 text-xs border-amber-500/40">
              <RotateCw className="h-3.5 w-3.5" /> Run Again
            </Button>
          </Link>
        </div>
      )}

      {/* Page Header */}
      <PageHeader
        title={`Comparison: ${comp.comparison_type}`}
        description={`Matching Strategy: ${comp.matching_strategy} • Created on ${new Date(comp.created_at).toLocaleDateString()}`}
      >
        {isReconciliation && (
          <a
            href={comparisonsApi.getExportCsvUrl(id)}
            download={`reconciliation-${id}.csv`}
          >
            <Button variant="outline" size="sm" className="gap-1.5 text-xs">
              <Download className="h-3.5 w-3.5" /> Export Findings (CSV)
            </Button>
          </a>
        )}
      </PageHeader>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
        <Card className="p-3">
          <div className="text-[11px] font-medium text-muted-foreground">Matched</div>
          <div className="text-xl font-bold text-emerald-600 dark:text-emerald-400 mt-1">
            {matched}
          </div>
        </Card>
        <Card className="p-3">
          <div className="text-[11px] font-medium text-muted-foreground">Mismatched</div>
          <div className="text-xl font-bold text-rose-600 dark:text-rose-400 mt-1">
            {mismatched}
          </div>
        </Card>
        <Card className="p-3">
          <div className="text-[11px] font-medium text-muted-foreground">Missing in Left</div>
          <div className="text-xl font-bold text-amber-600 dark:text-amber-400 mt-1">
            {missingLeft}
          </div>
        </Card>
        <Card className="p-3">
          <div className="text-[11px] font-medium text-muted-foreground">Missing in Right</div>
          <div className="text-xl font-bold text-amber-600 dark:text-amber-400 mt-1">
            {missingRight}
          </div>
        </Card>
        <Card className="p-3">
          <div className="text-[11px] font-medium text-muted-foreground">Ambiguous</div>
          <div className="text-xl font-bold text-purple-600 dark:text-purple-400 mt-1">
            {ambiguous}
          </div>
        </Card>
        <Card className="p-3">
          <div className="text-[11px] font-medium text-muted-foreground">Duplicate</div>
          <div className="text-xl font-bold text-zinc-600 dark:text-zinc-400 mt-1">
            {duplicate}
          </div>
        </Card>
      </div>

      {/* Findings Table Toolbar */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <Select value={statusFilter} onValueChange={(val) => setStatusFilter(val || "all")}>
            <SelectTrigger className="w-[180px] h-8 text-xs">
              <SelectValue placeholder="Filter Findings" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Findings</SelectItem>
              <SelectItem value="MATCHED">Matched</SelectItem>
              <SelectItem value="MISMATCHED">Mismatched</SelectItem>
              <SelectItem value="MISSING_IN_LEFT">Missing in Left</SelectItem>
              <SelectItem value="MISSING_IN_RIGHT">Missing in Right</SelectItem>
              <SelectItem value="AMBIGUOUS">Ambiguous</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <span className="text-xs text-muted-foreground font-mono">
          {findings.length} findings listed
        </span>
      </div>

      {/* Findings Table */}
      <div className="border rounded-lg overflow-hidden bg-card">
        {findingsLoading ? (
          <div className="p-4 space-y-2">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="h-10 bg-muted animate-pulse rounded" />
            ))}
          </div>
        ) : findings.length === 0 ? (
          <div className="py-12 text-center text-xs text-muted-foreground">
            No findings for the selected filter.
          </div>
        ) : (
          <Table>
            <TableHeader className="bg-muted/40">
              <TableRow>
                <TableHead>Field / Record</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Left Value (PDF)</TableHead>
                <TableHead>Right Value (Register)</TableHead>
                <TableHead>Difference</TableHead>
                <TableHead>Evidence</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {findings.map((f) => {
                const isRecord = f.field_name === "__record__"
                return (
                  <TableRow
                    key={f.id}
                    className={`text-xs ${isRecord ? "bg-muted/20 font-semibold" : ""}`}
                  >
                    <TableCell className="font-mono">
                      {isRecord ? (
                        <span>Record: {f.record_key || `#${f.position}`}</span>
                      ) : (
                        <span className="pl-4 text-muted-foreground">{f.field_name}</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={f.status} />
                    </TableCell>
                    <TableCell className="font-mono">
                      {f.left_value_json !== null && f.left_value_json !== undefined
                        ? String(f.left_value_json)
                        : "—"}
                    </TableCell>
                    <TableCell className="font-mono">
                      {f.right_value_json !== null && f.right_value_json !== undefined
                        ? String(f.right_value_json)
                        : "—"}
                    </TableCell>
                    <TableCell className="font-mono text-muted-foreground">
                      {f.difference_json !== null && f.difference_json !== undefined
                        ? String(f.difference_json)
                        : "—"}
                    </TableCell>
                    <TableCell className="font-mono text-[11px] text-muted-foreground">
                      {f.evidence_json && Object.keys(f.evidence_json).length > 0 ? (
                        <span>
                          {f.evidence_json.page ? `P.${f.evidence_json.page}` : ""}
                          {f.evidence_json.row ? `Row ${f.evidence_json.row}` : ""}
                        </span>
                      ) : (
                        "—"
                      )}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        )}
      </div>
    </div>
  )
}
