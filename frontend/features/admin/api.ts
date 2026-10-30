import { apiClient } from "@/lib/api/client"
import type { Res } from "@/lib/api/typed"
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
    const res = await apiClient.get<Res<"GET /admin/stats">>("/admin/stats")
    return res.data
  },

  async getDeadLetter(params?: {
    limit?: number
    offset?: number
  }): Promise<Page_DeadLetter_> {
    const res = await apiClient.get<Res<"GET /admin/dead-letter">>(
      "/admin/dead-letter",
      {
        params,
      }
    )
    return res.data
  },

  async getAuditEvents(params?: {
    resource_type?: string | null
    resource_id?: string | null
    action?: string | null
    limit?: number
    offset?: number
  }): Promise<Page_AuditEventOut_> {
    const res = await apiClient.get<Res<"GET /admin/audit-events">>(
      "/admin/audit-events",
      { params }
    )
    return res.data
  },

  async listUsers(params?: {
    limit?: number
    offset?: number
  }): Promise<Page_UserOut_> {
    const res = await apiClient.get<Res<"GET /users">>("/users", { params })
    return res.data
  },

  async createUser(payload: CreateUserRequest): Promise<UserOut> {
    const res = await apiClient.post<Res<"POST /users">>("/users", payload)
    return res.data
  },

  async updateUser(
    userId: string,
    payload: UpdateUserRequest
  ): Promise<UserOut> {
    const res = await apiClient.patch<Res<"PATCH /users/{user_id}">>(
      `/users/${userId}`,
      payload
    )
    return res.data
  },

  async revokeUserSessions(userId: string): Promise<void> {
    await apiClient.post<Res<"POST /users/{user_id}/revoke-sessions">>(
      `/users/${userId}/revoke-sessions`
    )
  },

  async getHealthReady(): Promise<SystemHealth> {
    const res = await apiClient.get<SystemHealth>("/health/ready", {
      baseURL: "/bff/api",
    })
    return res.data
  },
}
