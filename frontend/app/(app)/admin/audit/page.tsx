"use client"

import React, { useState } from "react"
import { PageHeader } from "@/components/page-header"
import { useCurrentUser } from "@/features/auth/hooks"
import { useAuditEvents } from "@/features/admin/hooks"
import { canAdmin } from "@/lib/permissions"
import { DateTime } from "@/components/date-time"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/error-state"
import { Input } from "@/components/ui/input"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { History, ShieldAlert, Search } from "lucide-react"

export default function AuditAdminPage() {
  const { data: user } = useCurrentUser()
  const isAdmin = canAdmin(user?.role)

  const [resourceType, setResourceType] = useState("")
  const [action, setAction] = useState("")

  const { data, isLoading, isError, error, refetch } = useAuditEvents({
    resource_type: resourceType || null,
    action: action || null,
    limit: 100,
  })

  const events = data?.items ?? []

  if (!isAdmin) {
    return (
      <EmptyState
        icon={ShieldAlert}
        title="Access Denied"
        description="Audit logging is restricted to organization administrators."
      />
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Audit Log"
        description="Tamper-evident append-only record of security events, document edits, and operational activities."
      />

      {/* Filter toolbar */}
      <div className="flex items-center gap-3">
        <div className="relative max-w-xs flex-1">
          <Search className="absolute top-2.5 left-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Filter by action..."
            value={action}
            onChange={(e) => setAction(e.target.value)}
            className="h-9 pl-9 text-xs"
          />
        </div>
        <div className="relative max-w-xs flex-1">
          <Search className="absolute top-2.5 left-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Filter by resource type..."
            value={resourceType}
            onChange={(e) => setResourceType(e.target.value)}
            className="h-9 pl-9 text-xs"
          />
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-2 rounded-lg border p-4">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="h-10 animate-pulse rounded bg-muted" />
          ))}
        </div>
      ) : isError ? (
        <ErrorState
          message={(error as any)?.message || "Failed to load audit events"}
          requestId={(error as any)?.requestId}
          onRetry={() => refetch()}
        />
      ) : events.length === 0 ? (
        <EmptyState
          icon={History}
          title="No audit events found"
          description="No security or mutation logs matched your filter."
        />
      ) : (
        <div className="space-y-4">
          {/* Mobile / Tablet Container Cards */}
          <div className="grid grid-cols-1 gap-3 font-mono text-xs sm:grid-cols-2 lg:hidden">
            {events.map((evt) => (
              <div
                key={evt.id}
                className="space-y-2 rounded-lg border bg-card p-3.5 transition-colors hover:border-primary/40"
              >
                <div className="flex items-start justify-between gap-2">
                  <span className="font-semibold text-foreground uppercase">
                    {evt.action}
                  </span>
                  <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground uppercase">
                    {evt.resource_type}
                  </span>
                </div>

                <div className="space-y-1 text-[11px] text-muted-foreground">
                  <div>
                    <span className="text-muted-foreground/70">Actor: </span>
                    <span className="text-foreground">
                      {evt.actor_id
                        ? evt.actor_id.slice(0, 12) + "..."
                        : "SYSTEM"}
                    </span>
                  </div>
                  <div>
                    <span className="text-muted-foreground/70">Resource: </span>
                    <span className="text-foreground">
                      {evt.resource_id
                        ? evt.resource_id.slice(0, 12) + "..."
                        : "—"}
                    </span>
                  </div>
                </div>

                <div className="border-t pt-1.5 text-[11px] text-muted-foreground">
                  <DateTime value={evt.created_at} />
                </div>
              </div>
            ))}
          </div>

          {/* Desktop Table View */}
          <div className="hidden overflow-hidden rounded-lg border bg-card lg:block">
            <Table>
              <TableHeader className="bg-muted/40">
                <TableRow>
                  <TableHead>Timestamp</TableHead>
                  <TableHead>Actor ID</TableHead>
                  <TableHead>Action</TableHead>
                  <TableHead>Resource Type</TableHead>
                  <TableHead>Resource ID</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {events.map((evt) => (
                  <TableRow key={evt.id} className="font-mono text-xs">
                    <TableCell>
                      <DateTime value={evt.created_at} />
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {evt.actor_id
                        ? evt.actor_id.slice(0, 10) + "..."
                        : "SYSTEM"}
                    </TableCell>
                    <TableCell className="font-semibold text-foreground uppercase">
                      {evt.action}
                    </TableCell>
                    <TableCell className="text-muted-foreground uppercase">
                      {evt.resource_type}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {evt.resource_id
                        ? evt.resource_id.slice(0, 10) + "..."
                        : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      )}
    </div>
  )
}
