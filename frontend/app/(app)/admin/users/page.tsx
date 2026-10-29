"use client"

import React, { useState } from "react"
import { PageHeader } from "@/components/page-header"
import { useCurrentUser } from "@/features/auth/hooks"
import {
  useUsersList,
  useCreateUser,
  useUpdateUser,
  useRevokeUserSessions,
} from "@/features/admin/hooks"
import { canAdmin } from "@/lib/permissions"
import { DateTime } from "@/components/date-time"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/error-state"
import { ConfirmDialog } from "@/components/confirm-dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { UserPlus, ShieldAlert, KeyRound } from "lucide-react"

export default function UsersAdminPage() {
  const { data: currentUser } = useCurrentUser()
  const isAdmin = canAdmin(currentUser?.role)

  const { data, isLoading, isError, error, refetch } = useUsersList({ limit: 50 })
  const users = data?.items ?? []

  const { mutate: createUser, isPending: isCreating } = useCreateUser()
  const { mutate: updateUser } = useUpdateUser()
  const { mutate: revokeSessions, isPending: isRevoking } = useRevokeUserSessions()

  const [createOpen, setCreateOpen] = useState(false)
  const [newUser, setNewUser] = useState({
    email: "",
    full_name: "",
    password: "",
    role: "VIEWER" as "VIEWER" | "ANALYST" | "REVIEWER" | "ADMIN",
  })

  const [revokeTargetId, setRevokeTargetId] = useState<string | null>(null)

  if (!isAdmin) {
    return (
      <EmptyState
        icon={ShieldAlert}
        title="Access Denied"
        description="User management is restricted to organization administrators."
      />
    )
  }

  const handleCreate = () => {
    createUser(newUser, {
      onSuccess: () => {
        setCreateOpen(false)
        setNewUser({
          email: "",
          full_name: "",
          password: "",
          role: "VIEWER",
        })
      },
    })
  }

  const handleToggleActive = (userId: string, currentActive: boolean) => {
    updateUser({
      userId,
      payload: { is_active: !currentActive },
    })
  }

  const handleRoleChange = (userId: string, newRole: any) => {
    updateUser({
      userId,
      payload: { role: newRole },
    })
  }

  const handleRevoke = () => {
    if (revokeTargetId) {
      revokeSessions(revokeTargetId, {
        onSuccess: () => setRevokeTargetId(null),
      })
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="User Management"
        description="Invite users, configure roles, and govern active authentication sessions."
      >
        <Button onClick={() => setCreateOpen(true)} className="gap-2">
          <UserPlus className="h-4 w-4" />
          <span>Invite / Add User</span>
        </Button>
      </PageHeader>

      {isLoading ? (
        <div className="space-y-2 border rounded-lg p-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-10 bg-muted animate-pulse rounded" />
          ))}
        </div>
      ) : isError ? (
        <ErrorState
          message={(error as any)?.message || "Failed to load users"}
          requestId={(error as any)?.requestId}
          onRetry={() => refetch()}
        />
      ) : (
        <div className="border rounded-lg overflow-hidden bg-card">
          <Table>
            <TableHeader className="bg-muted/40">
              <TableRow>
                <TableHead>User</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Created</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.map((u) => (
                <TableRow key={u.id} className="text-xs">
                  <TableCell>
                    <div className="flex flex-col">
                      <span className="font-medium text-foreground">{u.full_name || "—"}</span>
                      <span className="text-muted-foreground font-mono text-[11px]">{u.email}</span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Select
                      value={u.role}
                      onValueChange={(val) => handleRoleChange(u.id, val)}
                      disabled={u.id === currentUser?.id}
                    >
                      <SelectTrigger className="w-[120px] h-7 text-xs font-mono uppercase">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="VIEWER">VIEWER</SelectItem>
                        <SelectItem value="ANALYST">ANALYST</SelectItem>
                        <SelectItem value="REVIEWER">REVIEWER</SelectItem>
                        <SelectItem value="ADMIN">ADMIN</SelectItem>
                      </SelectContent>
                    </Select>
                  </TableCell>
                  <TableCell>
                    <span
                      onClick={() => u.id !== currentUser?.id && handleToggleActive(u.id, u.is_active)}
                      className={`cursor-pointer inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold tracking-wide ${
                        u.is_active
                          ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
                          : "bg-zinc-200 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400"
                      }`}
                    >
                      {u.is_active ? "Active" : "Deactivated"}
                    </span>
                  </TableCell>
                  <TableCell>
                    <DateTime value={u.created_at} />
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setRevokeTargetId(u.id)}
                      className="h-7 text-xs text-rose-600 hover:text-rose-700 gap-1"
                    >
                      <KeyRound className="h-3 w-3" /> Revoke Sessions
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Create User Dialog */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Invite / Add User</DialogTitle>
            <DialogDescription>
              Create a new user account within your organization.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3 py-2 text-xs">
            <div className="space-y-1">
              <Label className="text-xs">Full Name</Label>
              <Input
                placeholder="Jane Analyst"
                value={newUser.full_name}
                onChange={(e) => setNewUser((p) => ({ ...p, full_name: e.target.value }))}
                className="h-8 text-xs"
              />
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Email Address</Label>
              <Input
                type="email"
                placeholder="jane@company.com"
                value={newUser.email}
                onChange={(e) => setNewUser((p) => ({ ...p, email: e.target.value }))}
                className="h-8 text-xs"
              />
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Initial Password (min 12 characters)</Label>
              <Input
                type="password"
                placeholder="••••••••••••"
                value={newUser.password}
                onChange={(e) => setNewUser((p) => ({ ...p, password: e.target.value }))}
                className="h-8 text-xs font-mono"
              />
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Role</Label>
              <Select
                value={newUser.role}
                onValueChange={(val: any) => setNewUser((p) => ({ ...p, role: val }))}
              >
                <SelectTrigger className="h-8 text-xs font-mono">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="VIEWER">VIEWER - Read only</SelectItem>
                  <SelectItem value="ANALYST">ANALYST - Upload & Compare</SelectItem>
                  <SelectItem value="REVIEWER">REVIEWER - Approve & Correct</SelectItem>
                  <SelectItem value="ADMIN">ADMIN - Full privileges</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <DialogFooter>
            <Button variant="ghost" size="sm" onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={handleCreate}
              disabled={isCreating || !newUser.email || newUser.password.length < 12}
            >
              {isCreating ? "Creating..." : "Create User"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Revoke Sessions Confirmation */}
      <ConfirmDialog
        open={!!revokeTargetId}
        onOpenChange={(open) => !open && setRevokeTargetId(null)}
        title="Revoke All Sessions"
        description="Are you sure you want to invalidate all active refresh tokens and sessions for this user? They will be logged out immediately across all devices."
        confirmText="Revoke Sessions"
        isDestructive
        isLoading={isRevoking}
        onConfirm={handleRevoke}
      />
    </div>
  )
}
