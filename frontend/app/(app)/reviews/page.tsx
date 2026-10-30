"use client"

import React, { Suspense } from "react"
import { useQueryState, parseAsString, parseAsInteger } from "nuqs"
import { PageHeader } from "@/components/page-header"
import { useReviewQueue, useClaimReview } from "@/features/reviews/hooks"
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Eye,
  Hand,
  ChevronLeft,
  ChevronRight,
  CheckCircle2,
} from "lucide-react"
import Link from "next/link"
import { useRouter } from "next/navigation"

function ReviewsContent() {
  const router = useRouter()
  const { data: user } = useCurrentUser()
  const { mutate: claimTask, isPending: isClaiming } = useClaimReview()

  const [filterType, setFilterType] = useQueryState(
    "filter",
    parseAsString.withDefault("all")
  )
  const [page, setPage] = useQueryState("page", parseAsInteger.withDefault(1))

  const limit = 20
  const offset = (page - 1) * limit

  const queryParams = {
    limit,
    offset,
    assigned_to_me: filterType === "mine" ? true : undefined,
    unassigned: filterType === "unassigned" ? true : undefined,
  }

  const { data, isLoading, isError, error, refetch } =
    useReviewQueue(queryParams)
  const items = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = Math.ceil(total / limit) || 1

  const handleClaim = (taskId: string, invoiceId?: string | null) => {
    claimTask(
      { id: taskId },
      {
        onSuccess: () => {
          if (invoiceId) {
            router.push(`/invoices/${invoiceId}`)
          }
        },
      }
    )
  }

  const handleOpenNext = () => {
    const unassigned = items.find((i) => !i.assigned_to) || items[0]
    if (unassigned) {
      if (unassigned.invoice_record_id) {
        if (!unassigned.assigned_to) {
          claimTask({ id: unassigned.id })
        }
        router.push(`/invoices/${unassigned.invoice_record_id}`)
      }
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Review Queue"
        description="Verify extracted invoices with validation warnings, calculation discrepancies, or low-confidence fields."
      >
        {items.length > 0 && hasPermission(user?.role, "REVIEW_CLAIM") && (
          <Button onClick={handleOpenNext} className="gap-2">
            <CheckCircle2 className="h-4 w-4" />
            <span>Open Next Review Task</span>
          </Button>
        )}
      </PageHeader>

      {/* Filter tabs */}
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
        <div className="flex w-full items-center gap-2 sm:w-auto">
          <Select
            value={filterType}
            onValueChange={(val) => {
              setFilterType(val)
              setPage(1)
            }}
          >
            <SelectTrigger className="h-9 w-full text-xs sm:w-[180px]">
              <SelectValue placeholder="Queue Filter" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Open Tasks</SelectItem>
              <SelectItem value="mine">Assigned to Me</SelectItem>
              <SelectItem value="unassigned">Unassigned Tasks</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="self-start font-mono text-xs text-muted-foreground sm:self-auto">
          Showing {total === 0 ? 0 : offset + 1}–
          {Math.min(offset + limit, total)} of {total}
        </div>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="space-y-2 rounded-lg border p-4">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="h-10 animate-pulse rounded bg-muted" />
          ))}
        </div>
      ) : isError ? (
        <ErrorState
          message={(error as any)?.message || "Failed to load review queue"}
          requestId={(error as any)?.requestId}
          onRetry={() => refetch()}
        />
      ) : items.length === 0 ? (
        <EmptyState
          title="Review queue empty"
          description="There are currently no invoices awaiting manual verification or review."
        />
      ) : (
        <div className="space-y-4">
          {/* Mobile / Tablet Container Cards */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:hidden">
            {items.map((item) => (
              <div
                key={item.id}
                className="flex flex-col justify-between space-y-3 rounded-lg border bg-card p-4 transition-colors hover:border-primary/40"
              >
                <div className="space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p
                        className="truncate text-sm font-medium text-foreground"
                        title={item.document_filename}
                      >
                        {item.document_filename}
                      </p>
                      <p className="mt-0.5 font-mono text-xs text-muted-foreground">
                        Invoice:{" "}
                        <span className="text-foreground">
                          {item.invoice?.invoice_number || "—"}
                        </span>
                      </p>
                    </div>
                    <StatusBadge status={item.status} />
                  </div>

                  <div className="flex items-center justify-between pt-1 text-xs">
                    <span className="rounded border border-amber-200 bg-amber-50 px-2 py-0.5 font-semibold text-amber-600 dark:border-amber-900 dark:bg-amber-950/60 dark:text-amber-400">
                      {item.open_issue_count} issue
                      {item.open_issue_count === 1 ? "" : "s"}
                    </span>
                    <span className="font-mono text-[11px] text-muted-foreground">
                      {item.assigned_to ? (
                        item.assigned_to === user?.id ? (
                          <span className="font-medium text-primary">
                            Assigned to You
                          </span>
                        ) : (
                          `Assigned: ${item.assigned_to.slice(0, 8)}...`
                        )
                      ) : (
                        <span className="text-zinc-400 italic">Unassigned</span>
                      )}
                    </span>
                  </div>
                </div>

                <div className="flex items-center justify-between border-t pt-2 text-[11px]">
                  <DateTime value={item.created_at} />
                  <div className="flex shrink-0 items-center gap-1.5">
                    {!item.assigned_to &&
                      hasPermission(user?.role, "REVIEW_CLAIM") && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() =>
                            handleClaim(item.id, item.invoice_record_id)
                          }
                          disabled={isClaiming}
                          className="h-7 gap-1 text-xs"
                        >
                          <Hand className="h-3 w-3" /> Claim
                        </Button>
                      )}
                    {item.invoice_record_id && (
                      <Link href={`/invoices/${item.invoice_record_id}`}>
                        <Button
                          size="sm"
                          variant="default"
                          className="h-7 gap-1 text-xs"
                        >
                          <Eye className="h-3 w-3" /> Review
                        </Button>
                      </Link>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Desktop Table View */}
          <div className="hidden overflow-hidden rounded-lg border bg-card lg:block">
            <Table>
              <TableHeader className="bg-muted/40">
                <TableRow>
                  <TableHead>Document</TableHead>
                  <TableHead>Invoice #</TableHead>
                  <TableHead>Open Issues</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Assigned To</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item) => (
                  <TableRow
                    key={item.id}
                    className="transition-colors hover:bg-muted/30"
                  >
                    <TableCell
                      className="max-w-[200px] truncate font-medium"
                      title={item.document_filename}
                    >
                      {item.document_filename}
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {item.invoice?.invoice_number || "—"}
                    </TableCell>
                    <TableCell>
                      <span className="text-xs font-semibold text-amber-600 dark:text-amber-400">
                        {item.open_issue_count} issue
                        {item.open_issue_count === 1 ? "" : "s"}
                      </span>
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={item.status} />
                    </TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {item.assigned_to ? (
                        item.assigned_to === user?.id ? (
                          <span className="font-medium text-primary">You</span>
                        ) : (
                          item.assigned_to
                        )
                      ) : (
                        <span className="text-zinc-400 italic">Unassigned</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <DateTime value={item.created_at} />
                    </TableCell>
                    <TableCell className="space-x-1 text-right">
                      {!item.assigned_to &&
                        hasPermission(user?.role, "REVIEW_CLAIM") && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() =>
                              handleClaim(item.id, item.invoice_record_id)
                            }
                            disabled={isClaiming}
                            className="h-8 gap-1 text-xs"
                          >
                            <Hand className="h-3.5 w-3.5" /> Claim
                          </Button>
                        )}
                      {item.invoice_record_id && (
                        <Link href={`/invoices/${item.invoice_record_id}`}>
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-8 gap-1 text-xs"
                          >
                            <Eye className="h-3.5 w-3.5" /> Review
                          </Button>
                        </Link>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
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

export default function ReviewsPage() {
  return (
    <Suspense
      fallback={<div className="h-96 animate-pulse rounded-lg bg-card" />}
    >
      <ReviewsContent />
    </Suspense>
  )
}
