"use client"

import React, { useState } from "react"
import { PageHeader } from "@/components/page-header"
import { useCurrentUser } from "@/features/auth/hooks"
import { useDeadLetter } from "@/features/admin/hooks"
import { useRetryJob } from "@/features/jobs/hooks"
import { canAdmin } from "@/lib/permissions"
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
import { RotateCw, ShieldAlert, AlertTriangle } from "lucide-react"
import Link from "next/link"

export default function DeadLetterAdminPage() {
  const { data: user } = useCurrentUser()
  const isAdmin = canAdmin(user?.role)

  const { data, isLoading, isError, error, refetch } = useDeadLetter({ limit: 50 })
  const deadLetters = data?.items ?? []
  const { mutate: retryJob, isPending: isRetrying } = useRetryJob()
  const [retryingId, setRetryingId] = useState<string | null>(null)

  if (!isAdmin) {
    return (
      <EmptyState
        icon={ShieldAlert}
        title="Access Denied"
        description="Dead-letter queue inspection is restricted to organization administrators."
      />
    )
  }

  const handleReplay = (jobId: string) => {
    setRetryingId(jobId)
    retryJob(jobId, {
      onSettled: () => setRetryingId(null),
    })
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Failed Jobs & Dead-Letter Queue"
        description="Inspect exhausted asynchronous pipeline errors, view error traces, and replay failed runs."
      />

      {isLoading ? (
        <div className="space-y-2 border rounded-lg p-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-10 bg-muted animate-pulse rounded" />
          ))}
        </div>
      ) : isError ? (
        <ErrorState
          message={(error as any)?.message || "Failed to load dead-letter items"}
          requestId={(error as any)?.requestId}
          onRetry={() => refetch()}
        />
      ) : deadLetters.length === 0 ? (
        <EmptyState
          icon={AlertTriangle}
          title="Dead-letter queue clean"
          description="There are currently no exhausted or permanently failed jobs in the dead-letter queue."
        />
      ) : (
        <div className="border rounded-lg overflow-hidden bg-card">
          <Table>
            <TableHeader className="bg-muted/40">
              <TableRow>
                <TableHead>Job ID</TableHead>
                <TableHead>Document</TableHead>
                <TableHead>Error Code</TableHead>
                <TableHead>Message</TableHead>
                <TableHead>Failed At</TableHead>
                <TableHead className="text-right">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {deadLetters.map((dl) => (
                <TableRow key={dl.job.id} className="text-xs">
                  <TableCell className="font-mono font-medium">
                    <Link href={`/jobs/${dl.job.id}`} className="hover:text-primary transition-colors">
                      {dl.job.id.slice(0, 8)}...
                    </Link>
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {dl.job.document_id ? (
                      <Link href={`/documents/${dl.job.document_id}`} className="hover:text-primary underline">
                        {dl.job.document_id.slice(0, 8)}...
                      </Link>
                    ) : (
                      "—"
                    )}
                  </TableCell>
                  <TableCell className="font-mono text-rose-600 dark:text-rose-400 font-medium">
                    {dl.job.error_code || dl.failed_tasks[0]?.last_error_code || "UNKNOWN"}
                  </TableCell>
                  <TableCell
                    className="text-muted-foreground font-mono truncate max-w-xs"
                    title={dl.failed_tasks[0]?.last_error_message || dl.job.sanitized_error_message || ""}
                  >
                    {dl.failed_tasks[0]?.last_error_message || dl.job.sanitized_error_message || "—"}
                  </TableCell>
                  <TableCell>
                    <DateTime value={dl.job.completed_at || dl.job.created_at} />
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleReplay(dl.job.id)}
                      disabled={isRetrying && retryingId === dl.job.id}
                      className="h-7 text-xs gap-1"
                    >
                      <RotateCw
                        className={`h-3 w-3 ${isRetrying && retryingId === dl.job.id ? "animate-spin" : ""}`}
                      />
                      Replay Job
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
