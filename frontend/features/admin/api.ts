import { apiClient } from "@/lib/api/client"
import type { components } from "@/lib/api/schema"

export type OrgStats = components["schemas"]["OrgStats"]
export type DeadLetter = components["schemas"]["DeadLetter"]
export type Page_DeadLetter_ = components["schemas"]["Page_DeadLetter_"]
export type AuditEventOut = components["schemas"]["AuditEventOut"]
export type Page_AuditEventOut_ = components["schemas"]["Page_AuditEventOut_"]
export type UserOut = components["schemas"]["UserOut"]
export type Page_UserOut_ = components["schemas"]["Page_UserOut_"]
export type CreateUserRequest = components["schemas"]["CreateUserRequest"]
export type UpdateUserRequest = components["schemas"]["UpdateUserRequest"]

export interface SystemHealth {
  status: string
  details?: Record<string, unknown>
}

export const adminApi = {
  async getStats(): Promise<OrgStats> {
    const res = await apiClient.get<OrgStats>("/admin/stats")
    return res.data
  },

  async getDeadLetter(params?: {
    limit?: number
    offset?: number
  }): Promise<Page_DeadLetter_> {
    const res = await apiClient.get<Page_DeadLetter_>("/admin/dead-letter", {
      params,
    })
    return res.data
  },

  async getAuditEvents(params?: {
    resource_type?: string | null
    resource_id?: string | null
    action?: string | null
    limit?: number
    offset?: number
  }): Promise<Page_AuditEventOut_> {
    const res = await apiClient.get<Page_AuditEventOut_>(
      "/admin/audit-events",
      { params }
    )
    return res.data
  },

  async listUsers(params?: {
    limit?: number
    offset?: number
  }): Promise<Page_UserOut_> {
    const res = await apiClient.get<Page_UserOut_>("/users", { params })
    return res.data
  },

  async createUser(payload: CreateUserRequest): Promise<UserOut> {
    const res = await apiClient.post<UserOut>("/users", payload)
    return res.data
  },

  async updateUser(
    userId: string,
    payload: UpdateUserRequest
  ): Promise<UserOut> {
    const res = await apiClient.patch<UserOut>(`/users/${userId}`, payload)
    return res.data
  },

  async revokeUserSessions(userId: string): Promise<void> {
    await apiClient.post(`/users/${userId}/revoke-sessions`)
  },

  async getHealthReady(): Promise<SystemHealth> {
    const res = await apiClient.get<SystemHealth>("/health/ready", {
      baseURL: "/bff/api",
    })
    return res.data
  },
}
