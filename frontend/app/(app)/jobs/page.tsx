"use client"

import { jobTypeLabel } from "@/lib/labels"
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
  const [stateFilter, setStateFilter] = useQueryState(
    "state",
    parseAsString.withDefault("all")
  )
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
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
        <Select
          value={stateFilter}
          onValueChange={(val) => {
            setStateFilter(val)
            setPage(1)
          }}
        >
          <SelectTrigger className="h-9 w-full text-xs sm:w-[180px]">
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

        <div className="self-start font-mono text-xs text-muted-foreground sm:self-auto">
          Showing {total === 0 ? 0 : offset + 1}–
          {Math.min(offset + limit, total)} of {total}
        </div>
      </div>

      {/* Main Table */}
      {isLoading ? (
        <div className="space-y-2 rounded-lg border p-4">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="h-10 animate-pulse rounded bg-muted" />
          ))}
        </div>
      ) : isError ? (
        <ErrorState
          message={(error as any)?.message || "Failed to load processing jobs"}
          requestId={(error as any)?.requestId}
          onRetry={() => refetch()}
        />
      ) : jobs.length === 0 ? (
        <EmptyState
          title="No jobs found"
          description="No processing runs match the selected criteria."
        />
      ) : (
        <div className="space-y-4">
          {/* Mobile / Tablet Container Cards */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:hidden">
            {jobs.map((job) => {
              const pct = parseFloat(job.progress_percent) || 0
              return (
                <div
                  key={job.id}
                  className="flex flex-col justify-between space-y-3 rounded-lg border bg-card p-4 transition-colors hover:border-primary/40"
                >
                  <div className="space-y-2.5">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <Link
                          href={`/jobs/${job.id}`}
                          className="flex items-center gap-1 font-mono text-xs font-semibold text-foreground transition-colors hover:text-primary"
                        >
                          Job #{job.id.slice(0, 8)}
                          <ExternalLink className="h-3 w-3 text-muted-foreground" />
                        </Link>
                        <span className="mt-1 inline-block rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground uppercase">
                          {jobTypeLabel(job.job_type)} · Attempt #
                          {job.attempt_number}
                        </span>
                      </div>
                      <StatusBadge status={job.state} />
                    </div>

                    <div className="space-y-1">
                      <div className="flex justify-between font-mono text-[11px] text-muted-foreground">
                        <span>
                          Progress ({job.pages_completed}/{job.pages_total}{" "}
                          pages)
                        </span>
                        <span className="font-semibold text-foreground">
                          {pct}%
                        </span>
                      </div>
                      <Progress value={pct} className="h-1.5" />
                    </div>
                  </div>

                  <div className="flex items-center justify-between border-t pt-2 text-[11px] text-muted-foreground">
                    <DateTime value={job.created_at} />
                    <Link href={`/jobs/${job.id}`}>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 gap-1 px-2 text-xs"
                      >
                        Inspect <ExternalLink className="h-3 w-3" />
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
                    <TableRow
                      key={job.id}
                      className="transition-colors hover:bg-muted/30"
                    >
                      <TableCell className="font-mono text-xs font-medium">
                        <Link
                          href={`/jobs/${job.id}`}
                          className="transition-colors hover:text-primary"
                        >
                          {job.id.slice(0, 8)}...
                        </Link>
                      </TableCell>
                      <TableCell className="font-mono text-xs uppercase">
                        {jobTypeLabel(job.job_type)}
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={job.state} />
                      </TableCell>
                      <TableCell>
                        <div className="space-y-1">
                          <div className="flex justify-between font-mono text-[10px]">
                            <span>{pct}%</span>
                          </div>
                          <Progress value={pct} className="h-1.5" />
                        </div>
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        {job.pages_completed} / {job.pages_total}
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        #{job.attempt_number}
                      </TableCell>
                      <TableCell>
                        <DateTime value={job.created_at} />
                      </TableCell>
                      <TableCell className="text-right">
                        <Link href={`/jobs/${job.id}`}>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-8 gap-1 text-xs"
                          >
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

          {/* Pagination bar */}
          <div className="flex items-center justify-between rounded-lg border bg-card px-4 py-3">
            <div className="font-mono text-xs text-muted-foreground">
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
    <Suspense
      fallback={<div className="h-96 animate-pulse rounded-lg bg-card" />}
    >
      <JobsContent />
    </Suspense>
  )
}
