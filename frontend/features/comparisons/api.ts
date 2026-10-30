import { apiClient } from "@/lib/api/client"
import type { components } from "@/lib/api/schema"

export type ComparisonOut = components["schemas"]["ComparisonOut"]
export type Page_ComparisonOut_ = components["schemas"]["Page_ComparisonOut_"]
export type ComparisonCreate = components["schemas"]["ComparisonCreate"]
export type ReconciliationCreate = components["schemas"]["ReconciliationCreate"]
export type ComparisonAccepted = components["schemas"]["ComparisonAccepted"]
export type FindingOut = components["schemas"]["FindingOut"]
export type Page_FindingOut_ = components["schemas"]["Page_FindingOut_"]

export const comparisonsApi = {
  async list(params?: {
    limit?: number
    offset?: number
  }): Promise<Page_ComparisonOut_> {
    const res = await apiClient.get<Page_ComparisonOut_>("/comparisons", {
      params,
    })
    return res.data
  },

  async getComparison(id: string): Promise<ComparisonOut> {
    const res = await apiClient.get<ComparisonOut>(`/comparisons/${id}`)
    return res.data
  },

  async comparisonFindings(
    id: string,
    params?: { limit?: number; offset?: number; status?: string }
  ): Promise<Page_FindingOut_> {
    const res = await apiClient.get<Page_FindingOut_>(
      `/comparisons/${id}/findings`,
      { params }
    )
    return res.data
  },

  async createComparison(
    payload: ComparisonCreate,
    idempotencyKey?: string
  ): Promise<ComparisonAccepted> {
    const res = await apiClient.post<ComparisonAccepted>(
      "/comparisons",
      payload,
      {
        headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {},
      }
    )
    return res.data
  },

  async getReconciliation(id: string): Promise<ComparisonOut> {
    const res = await apiClient.get<ComparisonOut>(`/reconciliations/${id}`)
    return res.data
  },

  async reconciliationFindings(
    id: string,
    params?: {
      records_only?: boolean
      finding_status?: string
      limit?: number
      offset?: number
    }
  ): Promise<Page_FindingOut_> {
    const res = await apiClient.get<Page_FindingOut_>(
      `/reconciliations/${id}/findings`,
      { params }
    )
    return res.data
  },

  async createReconciliation(
    payload: ReconciliationCreate,
    idempotencyKey?: string
  ): Promise<ComparisonAccepted> {
    const res = await apiClient.post<ComparisonAccepted>(
      "/reconciliations",
      payload,
      {
        headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {},
      }
    )
    return res.data
  },

  getExportCsvUrl(reconciliationId: string): string {
    return `/bff/api/v1/reconciliations/${reconciliationId}/export.csv`
  },
}
