"use client"

import React, { Suspense } from "react"
import { useQueryState, parseAsString, parseAsInteger } from "nuqs"
import { PageHeader } from "@/components/page-header"
import { useJobList } from "@/features/jobs/hooks"
import { StatusBadge } from "@/components/status-badge"
import { DateTime } from "@/components/date-time"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/error-state"
import { Progress } from "@/components/ui/progress"
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
import { ExternalLink, ChevronLeft, ChevronRight } from "lucide-react"
import Link from "next/link"

function JobsContent() {
  const [stateFilter, setStateFilter] = useQueryState("state", parseAsString.withDefault("all"))
  const [page, setPage] = useQueryState("page", parseAsInteger.withDefault(1))

  const limit = 20
  const offset = (page - 1) * limit

  const queryParams = {
    limit,
    offset,
    state: stateFilter !== "all" ? stateFilter : undefined,
  }

  const { data, isLoading, isError, error, refetch } = useJobList(queryParams)
  const jobs = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = Math.ceil(total / limit) || 1

  return (
    <div className="space-y-6">
      <PageHeader
        title="Processing Jobs"
        description="Monitor asynchronous document parsing, invoice extraction, and validation runs."
      />

      {/* Filter toolbar */}
      <div className="flex items-center justify-between gap-4">
        <Select
          value={stateFilter}
          onValueChange={(val) => {
            setStateFilter(val)
            setPage(1)
          }}
        >
          <SelectTrigger className="w-[180px] h-9 text-xs">
            <SelectValue placeholder="Job State" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All States</SelectItem>
            <SelectItem value="PENDING">Pending</SelectItem>
            <SelectItem value="RUNNING">Running</SelectItem>
            <SelectItem value="COMPLETED">Completed</SelectItem>
            <SelectItem value="FAILED">Failed</SelectItem>
            <SelectItem value="CANCELLED">Cancelled</SelectItem>
          </SelectContent>
        </Select>

        <div className="text-xs text-muted-foreground font-mono">
          Showing {total === 0 ? 0 : offset + 1}–{Math.min(offset + limit, total)} of {total}
        </div>
      </div>

      {/* Main Table */}
      {isLoading ? (
        <div className="space-y-2 border rounded-lg p-4">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="h-10 bg-muted animate-pulse rounded" />
          ))}
        </div>
      ) : isError ? (
        <ErrorState
          message={(error as any)?.message || "Failed to load processing jobs"}
          requestId={(error as any)?.requestId}
          onRetry={() => refetch()}
        />
      ) : jobs.length === 0 ? (
        <EmptyState title="No jobs found" description="No processing runs match the selected criteria." />
      ) : (
        <div className="border rounded-lg overflow-hidden bg-card">
          <Table>
            <TableHeader className="bg-muted/40">
              <TableRow>
                <TableHead>Job ID</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>State</TableHead>
                <TableHead className="w-[160px]">Progress</TableHead>
                <TableHead>Pages</TableHead>
                <TableHead>Attempt</TableHead>
                <TableHead>Created</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {jobs.map((job) => {
                const pct = parseFloat(job.progress_percent) || 0
                return (
                  <TableRow key={job.id} className="hover:bg-muted/30 transition-colors">
                    <TableCell className="font-mono text-xs font-medium">
                      <Link href={`/jobs/${job.id}`} className="hover:text-primary transition-colors">
                        {job.id.slice(0, 8)}...
                      </Link>
                    </TableCell>
                    <TableCell className="font-mono text-xs uppercase">{job.job_type}</TableCell>
                    <TableCell>
                      <StatusBadge status={job.state} />
                    </TableCell>
                    <TableCell>
                      <div className="space-y-1">
                        <div className="flex justify-between text-[10px] font-mono">
                          <span>{pct}%</span>
                        </div>
                        <Progress value={pct} className="h-1.5" />
                      </div>
                    </TableCell>
                    <TableCell className="text-xs font-mono">
                      {job.pages_completed} / {job.pages_total}
                    </TableCell>
                    <TableCell className="font-mono text-xs">#{job.attempt_number}</TableCell>
                    <TableCell>
                      <DateTime value={job.created_at} />
                    </TableCell>
                    <TableCell className="text-right">
                      <Link href={`/jobs/${job.id}`}>
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

          {/* Pagination bar */}
          <div className="flex items-center justify-between px-4 py-3 border-t bg-muted/20">
            <div className="text-xs text-muted-foreground font-mono">
              Page {page} of {totalPages}
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="h-8 gap-1 text-xs"
              >
                <ChevronLeft className="h-3.5 w-3.5" /> Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="h-8 gap-1 text-xs"
              >
                Next <ChevronRight className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default function JobsPage() {
  return (
    <Suspense fallback={<div className="h-96 rounded-lg bg-card animate-pulse" />}>
      <JobsContent />
    </Suspense>
  )
}

