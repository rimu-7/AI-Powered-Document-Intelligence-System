import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { adminApi, CreateUserRequest, UpdateUserRequest } from "./api"
import { qk } from "@/lib/api/keys"
import { invalidateForMutation } from "@/lib/api/invalidation"
import { toast } from "sonner"

export function useOrgStats() {
  return useQuery({
    queryKey: qk.admin.stats(),
    queryFn: adminApi.getStats,
    staleTime: 30_000,
    refetchInterval: 30_000,
  })
}

export function useDeadLetter(params?: { limit?: number; offset?: number }) {
  return useQuery({
    queryKey: qk.admin.deadLetter(params),
    queryFn: () => adminApi.getDeadLetter(params),
    placeholderData: (prev) => prev,
    staleTime: 15_000,
  })
}

export function useAuditEvents(params?: {
  resource_type?: string | null
  resource_id?: string | null
  action?: string | null
  limit?: number
  offset?: number
}) {
  return useQuery({
    queryKey: qk.admin.auditEvents(params),
    queryFn: () => adminApi.getAuditEvents(params),
    placeholderData: (prev) => prev,
    staleTime: 15_000,
  })
}

export function useUsersList(params?: { limit?: number; offset?: number }) {
  return useQuery({
    queryKey: qk.admin.users(params),
    queryFn: () => adminApi.listUsers(params),
    placeholderData: (prev) => prev,
    staleTime: 30_000,
  })
}

export function useCreateUser() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: CreateUserRequest) => adminApi.createUser(payload),
    onSuccess: async () => {
      await invalidateForMutation(queryClient, "create_user")
      toast.success("User invited/created successfully")
    },
    onError: (err: any) => {
      toast.error(err.message || "Failed to create user")
    },
  })
}

export function useUpdateUser() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      userId,
      payload,
    }: {
      userId: string
      payload: UpdateUserRequest
    }) => adminApi.updateUser(userId, payload),
    onSuccess: async () => {
      await invalidateForMutation(queryClient, "update_user")
      toast.success("User updated")
    },
    onError: (err: any) => {
      toast.error(err.message || "Failed to update user")
    },
  })
}

export function useRevokeUserSessions() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (userId: string) => adminApi.revokeUserSessions(userId),
    onSuccess: async () => {
      await invalidateForMutation(queryClient, "revoke_user_sessions")
      toast.success("All sessions revoked for user")
    },
    onError: (err: any) => {
      toast.error(err.message || "Failed to revoke sessions")
    },
  })
}

export function useSystemHealth() {
  return useQuery({
    queryKey: qk.admin.health(),
    queryFn: adminApi.getHealthReady,
    refetchInterval: 10_000,
  })
}
