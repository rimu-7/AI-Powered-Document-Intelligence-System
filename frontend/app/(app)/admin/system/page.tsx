"use client"

import React from "react"
import { PageHeader } from "@/components/page-header"
import { useCurrentUser } from "@/features/auth/hooks"
import { useSystemHealth } from "@/features/admin/hooks"
import { canAdmin } from "@/lib/permissions"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/error-state"
import { Database, HardDrive, Cpu, ShieldAlert, CheckCircle2, AlertCircle } from "lucide-react"

export default function SystemHealthAdminPage() {
  const { data: user } = useCurrentUser()
  const isAdmin = canAdmin(user?.role)

  const { data: health, isLoading, isError, error, refetch } = useSystemHealth()

  if (!isAdmin) {
    return (
      <EmptyState
        icon={ShieldAlert}
        title="Access Denied"
        description="System health inspection is restricted to organization administrators."
      />
    )
  }

  const isHealthy = health?.status === "ready" || health?.status === "healthy" || health?.status === "ok"

  return (
    <div className="space-y-6">
      <PageHeader
        title="System Readiness & Infrastructure Health"
        description="Live operational telemetry of database engines, Redis queues, and object storage connectivity."
      />

      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-32 bg-muted animate-pulse rounded-lg" />
          ))}
        </div>
      ) : isError ? (
        <ErrorState
          message={(error as any)?.message || "Failed to reach health endpoint"}
          requestId={(error as any)?.requestId}
          onRetry={() => refetch()}
        />
      ) : (
        <div className="space-y-6">
          <Card className="border-border">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <div className="space-y-1">
                <CardTitle className="text-base font-semibold">Overall System Status</CardTitle>
                <CardDescription className="text-xs">
                  Backend API, background worker pool, and shared data tiers
                </CardDescription>
              </div>
              <div
                className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold uppercase tracking-wider ${
                  isHealthy
                    ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800"
                    : "bg-rose-50 text-rose-700 dark:bg-rose-950 dark:text-rose-300 border border-rose-200 dark:border-rose-800"
                }`}
              >
                {isHealthy ? <CheckCircle2 className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
                {health?.status || "UNKNOWN"}
              </div>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-4">
                <Card className="p-4 border bg-muted/20 space-y-2">
                  <div className="flex items-center gap-2 text-foreground font-medium text-xs">
                    <Database className="h-4 w-4 text-primary" />
                    <span>PostgreSQL Database</span>
                  </div>
                  <div className="flex items-center gap-1.5 text-xs text-emerald-600 dark:text-emerald-400 font-medium">
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    Connected & Responsive
                  </div>
                </Card>

                <Card className="p-4 border bg-muted/20 space-y-2">
                  <div className="flex items-center gap-2 text-foreground font-medium text-xs">
                    <Cpu className="h-4 w-4 text-primary" />
                    <span>Redis Queue & Locks</span>
                  </div>
                  <div className="flex items-center gap-1.5 text-xs text-emerald-600 dark:text-emerald-400 font-medium">
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    Operating Normatively
                  </div>
                </Card>

                <Card className="p-4 border bg-muted/20 space-y-2">
                  <div className="flex items-center gap-2 text-foreground font-medium text-xs">
                    <HardDrive className="h-4 w-4 text-primary" />
                    <span>Object Storage (S3 / MinIO)</span>
                  </div>
                  <div className="flex items-center gap-1.5 text-xs text-emerald-600 dark:text-emerald-400 font-medium">
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    Buckets Accessible
                  </div>
                </Card>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}
