"use client"

import React from "react"
import { PageHeader } from "@/components/page-header"
import { useCurrentUser } from "@/features/auth/hooks"
import { useOrgStats } from "@/features/admin/hooks"
import { useDocumentsList } from "@/features/documents/hooks"
import { useJobList } from "@/features/jobs/hooks"
import { useReviewQueue } from "@/features/reviews/hooks"
import { useUpload } from "@/features/upload/upload-context"
import { canUpload, canAdmin } from "@/lib/permissions"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { StatusBadge } from "@/components/status-badge"
import { DateTime } from "@/components/date-time"
import { Bytes } from "@/components/bytes"
import {
  FileText,
  FileCheck,
  AlertTriangle,
  Briefcase,
  Upload,
  ArrowRight,
} from "lucide-react"
import Link from "next/link"

export default function DashboardPage() {
  const { data: user } = useCurrentUser()
  const { setIsOpen: setUploadOpen } = useUpload()
  const isAdmin = canAdmin(user?.role)

  const { data: stats } = useOrgStats()
  const { data: docsData, isLoading: docsLoading } = useDocumentsList({
    limit: 8,
  })
  const { data: jobsData, isLoading: jobsLoading } = useJobList({ limit: 5 })
  const { data: reviewQueue } = useReviewQueue({ limit: 5 })

  const recentDocs = docsData?.items ?? []
  const recentJobs = jobsData?.items ?? []
  const totalDocs = docsData?.total ?? 0
  const openReviewsCount = stats?.open_reviews ?? reviewQueue?.total ?? 0
  const failedTasksCount = stats?.failed_tasks ?? 0

  return (
    <div className="space-y-8">
      <PageHeader
        title={`Welcome back, ${user?.full_name?.split(" ")[0] || "Analyst"}`}
        description="Here is an overview of your organization's document processing and review workload."
      >
        {canUpload(user?.role) && (
          <Button onClick={() => setUploadOpen(true)} className="gap-2">
            <Upload className="h-4 w-4" />
            <span>Upload Documents</span>
          </Button>
        )}
      </PageHeader>

      {/* Metrics Row */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              Total Documents
            </CardTitle>
            <FileText className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold tracking-tight">{totalDocs}</div>
            <p className="mt-1 text-xs text-muted-foreground">
              Invoices, scans, and sheets
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Open Reviews</CardTitle>
            <FileCheck className="h-4 w-4 text-purple-600 dark:text-purple-400" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold tracking-tight text-purple-600 dark:text-purple-400">
              {openReviewsCount}
            </div>
            <Link
              href="/reviews"
              className="mt-1 flex items-center gap-1 text-xs font-medium text-primary hover:underline"
            >
              Go to review queue <ArrowRight className="h-3 w-3" />
            </Link>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Failed Tasks</CardTitle>
            <AlertTriangle className="h-4 w-4 text-rose-600 dark:text-rose-400" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold tracking-tight text-rose-600 dark:text-rose-400">
              {failedTasksCount}
            </div>
            {isAdmin ? (
              <Link
                href="/admin/failed-jobs"
                className="mt-1 flex items-center gap-1 text-xs font-medium text-primary hover:underline"
              >
                Inspect dead-letter queue <ArrowRight className="h-3 w-3" />
              </Link>
            ) : (
              <p className="mt-1 text-xs text-muted-foreground">
                Requiring supervisor attention
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Active Jobs</CardTitle>
            <Briefcase className="h-4 w-4 text-blue-600 dark:text-blue-400" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold tracking-tight text-blue-600 dark:text-blue-400">
              {
                recentJobs.filter(
                  (j) => !["COMPLETED", "FAILED", "CANCELLED"].includes(j.state)
                ).length
              }
            </div>
            <Link
              href="/jobs"
              className="mt-1 flex items-center gap-1 text-xs font-medium text-primary hover:underline"
            >
              View processing timeline <ArrowRight className="h-3 w-3" />
            </Link>
          </CardContent>
        </Card>
      </div>

      {/* Two columns: Recent Documents and Running Jobs */}
      <div className="grid gap-6 md:grid-cols-2">
        {/* Recent Documents */}
        <Card className="col-span-1">
          <CardHeader className="flex flex-row items-center justify-between pb-3">
            <div>
              <CardTitle className="text-base font-semibold">
                Recent Documents
              </CardTitle>
              <CardDescription className="text-xs">
                Latest uploaded files and status
              </CardDescription>
            </div>
            <Link href="/documents">
              <Button variant="ghost" size="sm" className="gap-1 text-xs">
                View all <ArrowRight className="h-3.5 w-3.5" />
              </Button>
            </Link>
          </CardHeader>
          <CardContent>
            {docsLoading ? (
              <div className="space-y-3">
                {[1, 2, 3].map((i) => (
                  <div
                    key={i}
                    className="h-12 animate-pulse rounded bg-muted"
                  />
                ))}
              </div>
            ) : recentDocs.length === 0 ? (
              <div className="py-8 text-center text-sm text-muted-foreground">
                No documents uploaded yet.
              </div>
            ) : (
              <div className="divide-y divide-border">
                {recentDocs.map((doc) => (
                  <div
                    key={doc.id}
                    className="flex items-center justify-between gap-3 py-2.5 text-xs"
                  >
                    <div className="flex min-w-0 flex-1 flex-col">
                      <Link
                        href={`/documents/${doc.id}`}
                        className="truncate text-sm font-medium transition-colors hover:text-primary"
                      >
                        {doc.original_filename}
                      </Link>
                      <div className="mt-0.5 flex items-center gap-2 text-muted-foreground">
                        <span className="font-mono text-[10px] uppercase">
                          {doc.file_kind}
                        </span>
                        <span>•</span>
                        <Bytes bytes={doc.file_size_bytes} />
                        <span>•</span>
                        <DateTime value={doc.created_at} />
                      </div>
                    </div>
                    <StatusBadge status={doc.status} />
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Processing Jobs */}
        <Card className="col-span-1">
          <CardHeader className="flex flex-row items-center justify-between pb-3">
            <div>
              <CardTitle className="text-base font-semibold">
                Processing Pipeline
              </CardTitle>
              <CardDescription className="text-xs">
                Recent worker execution status
              </CardDescription>
            </div>
            <Link href="/jobs">
              <Button variant="ghost" size="sm" className="gap-1 text-xs">
                View all <ArrowRight className="h-3.5 w-3.5" />
              </Button>
            </Link>
          </CardHeader>
          <CardContent>
            {jobsLoading ? (
              <div className="space-y-3">
                {[1, 2, 3].map((i) => (
                  <div
                    key={i}
                    className="h-12 animate-pulse rounded bg-muted"
                  />
                ))}
              </div>
            ) : recentJobs.length === 0 ? (
              <div className="py-8 text-center text-sm text-muted-foreground">
                No processing jobs recorded.
              </div>
            ) : (
              <div className="divide-y divide-border">
                {recentJobs.map((job) => (
                  <div
                    key={job.id}
                    className="flex items-center justify-between gap-3 py-2.5 text-xs"
                  >
                    <div className="flex min-w-0 flex-1 flex-col">
                      <Link
                        href={`/jobs/${job.id}`}
                        className="flex items-center gap-1.5 truncate text-sm font-medium transition-colors hover:text-primary"
                      >
                        <span className="font-mono text-xs">
                          {job.job_type}
                        </span>
                        <span className="font-mono text-[10px] text-muted-foreground">
                          (attempt #{job.attempt_number})
                        </span>
                      </Link>
                      <div className="mt-0.5 flex items-center gap-2 text-muted-foreground">
                        <span>
                          Pages: {job.pages_completed}/{job.pages_total}
                        </span>
                        <span>•</span>
                        <span>Progress: {job.progress_percent}%</span>
                        <span>•</span>
                        <DateTime value={job.created_at} />
                      </div>
                    </div>
                    <StatusBadge status={job.state} />
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
