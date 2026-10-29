"use client"

import React, { use } from "react"
import { useJob, useRetryJob, useCancelJob, isTerminal } from "@/features/jobs/hooks"
import { useCurrentUser } from "@/features/auth/hooks"
import { hasPermission } from "@/lib/permissions"
import { StatusBadge } from "@/components/status-badge"
import { DateTime } from "@/components/date-time"
import { ErrorState } from "@/components/error-state"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  RotateCw,
  XCircle,
  AlertCircle,
  FileText,
} from "lucide-react"
import Link from "next/link"

export default function JobDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  const { data: user } = useCurrentUser()
  const { data: job, isLoading, isError, error, refetch } = useJob(id)

  const { mutate: retryJob, isPending: isRetrying } = useRetryJob()
  const { mutate: cancelJob, isPending: isCancelling } = useCancelJob()

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="h-24 bg-muted animate-pulse rounded-lg" />
        <div className="h-64 bg-muted animate-pulse rounded-lg" />
      </div>
    )
  }

  if (isError || !job) {
    return (
      <ErrorState
        message={(error as any)?.message || "Job not found"}
        requestId={(error as any)?.requestId}
        onRetry={() => refetch()}
      />
    )
  }

  const isJobRunning = !isTerminal(job.state)
  const progressPct = parseFloat(job.progress_percent) || 0
  const stageHistory = Array.isArray(job.stage_history_json) ? job.stage_history_json : []
  const tasksByState = job.tasks_by_state || {}
  const failedTasks = job.failed_tasks || []

  return (
    <div className="space-y-6">
      {/* Top Header Card */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-6 rounded-xl border bg-card shadow-sm">
        <div className="space-y-1.5">
          <div className="flex items-center gap-2.5 flex-wrap">
            <h1 className="text-xl font-bold tracking-tight font-mono">Job {job.id.slice(0, 13)}</h1>
            <StatusBadge status={job.state} />
            <span className="text-xs font-mono bg-muted px-2 py-0.5 rounded text-muted-foreground">
              Attempt #{job.attempt_number}
            </span>
          </div>
          <div className="flex items-center gap-3 text-xs text-muted-foreground font-mono flex-wrap">
            <span>Type: {job.job_type}</span>
            <span>•</span>
            <span>Started: <DateTime value={job.started_at || job.created_at} /></span>
            {job.completed_at && (
              <>
                <span>•</span>
                <span>Finished: <DateTime value={job.completed_at} /></span>
              </>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {job.document_id && (
            <Link href={`/documents/${job.document_id}`}>
              <Button variant="outline" size="sm" className="gap-1.5 text-xs">
                <FileText className="h-3.5 w-3.5" />
                View Document
              </Button>
            </Link>
          )}

          {isJobRunning && hasPermission(user?.role, "JOB_MANAGE") && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => cancelJob(id)}
              disabled={isCancelling}
              className="gap-1.5 text-xs text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/20"
            >
              <XCircle className="h-3.5 w-3.5" />
              Cancel Job
            </Button>
          )}

          {!isJobRunning && hasPermission(user?.role, "JOB_MANAGE") && (
            <Button
              size="sm"
              onClick={() => retryJob(id)}
              disabled={isRetrying}
              className="gap-1.5 text-xs"
            >
              <RotateCw className={`h-3.5 w-3.5 ${isRetrying ? "animate-spin" : ""}`} />
              Retry Job
            </Button>
          )}
        </div>
      </div>

      {/* Progress Card */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-semibold">Progress & Pages</CardTitle>
            <span className="font-mono text-xs font-bold">{progressPct}%</span>
          </div>
          <CardDescription className="text-xs">
            {job.pages_completed} of {job.pages_total} pages processed ({job.pages_failed} failed)
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Progress value={progressPct} className="h-2" />
        </CardContent>
      </Card>

      {/* Grid: Stage Timeline & Task Status Breakdown */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Stage Timeline */}
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-semibold">Stage History</CardTitle>
            <CardDescription className="text-xs">Pipeline progression milestones</CardDescription>
          </CardHeader>
          <CardContent>
            {stageHistory.length === 0 ? (
              <div className="text-xs text-muted-foreground py-4 text-center">
                No stage history transitions recorded.
              </div>
            ) : (
              <div className="relative border-l-2 border-muted pl-4 ml-2 space-y-4 text-xs">
                {stageHistory.map((st: any, idx: number) => (
                  <div key={idx} className="relative">
                    <div className="absolute -left-[21px] top-0.5 h-2.5 w-2.5 rounded-full bg-primary" />
                    <div className="flex items-center justify-between font-mono font-medium">
                      <span>{st.stage || st.name || `Stage ${idx + 1}`}</span>
                      <DateTime value={st.timestamp || st.time} />
                    </div>
                    {st.message && <p className="text-muted-foreground mt-0.5">{st.message}</p>}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Task Counts by State */}
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-semibold">Tasks by Execution State</CardTitle>
            <CardDescription className="text-xs">Granular task worker distribution</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-3">
              {Object.entries(tasksByState).map(([k, v]) => (
                <div key={k} className="p-3 border rounded-lg bg-card text-xs flex items-center justify-between">
                  <span className="font-mono uppercase text-muted-foreground">{k}</span>
                  <span className="font-bold text-sm font-mono">{v}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Failed Tasks Section */}
      {failedTasks.length > 0 && (
        <Card className="border-rose-200 dark:border-rose-900/50">
          <CardHeader className="bg-rose-50/50 dark:bg-rose-950/20 border-b">
            <CardTitle className="text-sm font-semibold text-rose-700 dark:text-rose-400 flex items-center gap-2">
              <AlertCircle className="h-4 w-4" /> Failed Tasks ({failedTasks.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader className="bg-muted/40">
                <TableRow>
                  <TableHead>Task Name</TableHead>
                  <TableHead>Attempt</TableHead>
                  <TableHead>Error Code</TableHead>
                  <TableHead>Message</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {failedTasks.map((t) => (
                  <TableRow key={t.id} className="text-xs">
                    <TableCell className="font-mono font-medium">{t.task_type}</TableCell>
                    <TableCell className="font-mono">#{t.attempt_count}</TableCell>
                    <TableCell className="font-mono text-rose-600 dark:text-rose-400">
                      {t.last_error_code || "UNKNOWN"}
                    </TableCell>
                    <TableCell className="text-muted-foreground font-mono">
                      {t.last_error_message || "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
