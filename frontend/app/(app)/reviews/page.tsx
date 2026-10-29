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
import { Eye, Hand, ChevronLeft, ChevronRight, CheckCircle2 } from "lucide-react"
import Link from "next/link"
import { useRouter } from "next/navigation"

function ReviewsContent() {
  const router = useRouter()
  const { data: user } = useCurrentUser()
  const { mutate: claimTask, isPending: isClaiming } = useClaimReview()

  const [filterType, setFilterType] = useQueryState("filter", parseAsString.withDefault("all"))
  const [page, setPage] = useQueryState("page", parseAsInteger.withDefault(1))

  const limit = 20
  const offset = (page - 1) * limit

  const queryParams = {
    limit,
    offset,
    assigned_to_me: filterType === "mine" ? true : undefined,
    unassigned: filterType === "unassigned" ? true : undefined,
  }

  const { data, isLoading, isError, error, refetch } = useReviewQueue(queryParams)
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
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <Select
            value={filterType}
            onValueChange={(val) => {
              setFilterType(val)
              setPage(1)
            }}
          >
            <SelectTrigger className="w-[180px] h-9 text-xs">
              <SelectValue placeholder="Queue Filter" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Open Tasks</SelectItem>
              <SelectItem value="mine">Assigned to Me</SelectItem>
              <SelectItem value="unassigned">Unassigned Tasks</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="text-xs text-muted-foreground font-mono">
          Showing {total === 0 ? 0 : offset + 1}–{Math.min(offset + limit, total)} of {total}
        </div>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="space-y-2 border rounded-lg p-4">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="h-10 bg-muted animate-pulse rounded" />
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
        <div className="border rounded-lg overflow-hidden bg-card">
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
                <TableRow key={item.id} className="hover:bg-muted/30 transition-colors">
                  <TableCell className="font-medium truncate max-w-[200px]" title={item.document_filename}>
                    {item.document_filename}
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {item.invoice?.invoice_number || "—"}
                  </TableCell>
                  <TableCell>
                    <span className="font-semibold text-xs text-amber-600 dark:text-amber-400">
                      {item.open_issue_count} issue{item.open_issue_count === 1 ? "" : "s"}
                    </span>
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={item.status} />
                  </TableCell>
                  <TableCell className="text-xs font-mono text-muted-foreground">
                    {item.assigned_to ? (
                      item.assigned_to === user?.id ? (
                        <span className="text-primary font-medium">You</span>
                      ) : (
                        item.assigned_to
                      )
                    ) : (
                      <span className="italic text-zinc-400">Unassigned</span>
                    )}
                  </TableCell>
                  <TableCell>
                    <DateTime value={item.created_at} />
                  </TableCell>
                  <TableCell className="text-right space-x-1">
                    {!item.assigned_to && hasPermission(user?.role, "REVIEW_CLAIM") && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleClaim(item.id, item.invoice_record_id)}
                        disabled={isClaiming}
                        className="h-8 gap-1 text-xs"
                      >
                        <Hand className="h-3.5 w-3.5" /> Claim
                      </Button>
                    )}
                    {item.invoice_record_id && (
                      <Link href={`/invoices/${item.invoice_record_id}`}>
                        <Button size="sm" variant="outline" className="h-8 gap-1 text-xs">
                          <Eye className="h-3.5 w-3.5" /> Review
                        </Button>
                      </Link>
                    )}
                  </TableCell>
                </TableRow>
              ))}
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

export default function ReviewsPage() {
  return (
    <Suspense fallback={<div className="h-96 rounded-lg bg-card animate-pulse" />}>
      <ReviewsContent />
    </Suspense>
  )
}
