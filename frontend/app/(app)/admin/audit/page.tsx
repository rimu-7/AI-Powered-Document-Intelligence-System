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
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Filter by action..."
            value={action}
            onChange={(e) => setAction(e.target.value)}
            className="pl-9 h-9 text-xs"
          />
        </div>
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Filter by resource type..."
            value={resourceType}
            onChange={(e) => setResourceType(e.target.value)}
            className="pl-9 h-9 text-xs"
          />
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-2 border rounded-lg p-4">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="h-10 bg-muted animate-pulse rounded" />
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
        <div className="border rounded-lg overflow-hidden bg-card">
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
                <TableRow key={evt.id} className="text-xs font-mono">
                  <TableCell>
                    <DateTime value={evt.created_at} />
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {evt.actor_id ? evt.actor_id.slice(0, 10) + "..." : "SYSTEM"}
                  </TableCell>
                  <TableCell className="font-semibold text-foreground uppercase">
                    {evt.action}
                  </TableCell>
                  <TableCell className="uppercase text-muted-foreground">
                    {evt.resource_type}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {evt.resource_id ? evt.resource_id.slice(0, 10) + "..." : "—"}
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

