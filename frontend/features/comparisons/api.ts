import { apiClient } from "@/lib/api/client"
import type { Res } from "@/lib/api/typed"
import type { components } from "@/lib/api/schema"

export type ComparisonOut = components["schemas"]["ComparisonOut"]
export type Page_ComparisonOut_ = components["schemas"]["Page_ComparisonOut_"]
export type ComparisonCreate = components["schemas"]["ComparisonCreate"]
export type ReconciliationCreate = components["schemas"]["ReconciliationCreate"]
export type ComparisonAccepted = components["schemas"]["ComparisonAccepted"]
export type FindingOut = components["schemas"]["FindingOut"]
export type Page_FindingOut_ = components["schemas"]["Page_FindingOut_"]
export type ComparedDocument = components["schemas"]["ComparedDocument"]
export type FindingStatus = FindingOut["status"]

export interface FindingParams {
  limit?: number
  offset?: number
  finding_status?: FindingStatus
  records_only?: boolean
  /** Only the field findings of the record at this position. */
  record_position?: number
}

export const comparisonsApi = {
  async list(params?: {
    limit?: number
    offset?: number
  }): Promise<Page_ComparisonOut_> {
    const res = await apiClient.get<Res<"GET /comparisons">>("/comparisons", {
      params,
    })
    return res.data
  },

  async getComparison(id: string): Promise<ComparisonOut> {
    const res = await apiClient.get<Res<"GET /comparisons/{comparison_id}">>(
      `/comparisons/${id}`
    )
    return res.data
  },

  /** Works for both PDF↔PDF comparisons and reconciliations. */
  async comparisonFindings(
    id: string,
    params?: FindingParams
  ): Promise<Page_FindingOut_> {
    const res = await apiClient.get<
      Res<"GET /comparisons/{comparison_id}/findings">
    >(`/comparisons/${id}/findings`, { params })
    return res.data
  },

  async createComparison(
    payload: ComparisonCreate,
    idempotencyKey?: string
  ): Promise<ComparisonAccepted> {
    const res = await apiClient.post<Res<"POST /comparisons">>(
      "/comparisons",
      payload,
      {
        headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {},
      }
    )
    return res.data
  },

  async getReconciliation(id: string): Promise<ComparisonOut> {
    const res = await apiClient.get<
      Res<"GET /reconciliations/{reconciliation_id}">
    >(`/reconciliations/${id}`)
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
    const res = await apiClient.get<
      Res<"GET /reconciliations/{reconciliation_id}/findings">
    >(`/reconciliations/${id}/findings`, { params })
    return res.data
  },

  async createReconciliation(
    payload: ReconciliationCreate,
    idempotencyKey?: string
  ): Promise<ComparisonAccepted> {
    const res = await apiClient.post<Res<"POST /reconciliations">>(
      "/reconciliations",
      payload,
      {
        headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {},
      }
    )
    return res.data
  },

  /** Same documents and settings, on the current data; the old run is kept. */
  async rerun(id: string): Promise<ComparisonAccepted> {
    const res = await apiClient.post<
      Res<"POST /comparisons/{comparison_id}/rerun">
    >(`/comparisons/${id}/rerun`)
    return res.data
  },

  getExportCsvUrl(id: string): string {
    return `/bff/api/v1/comparisons/${id}/export.csv`
  },
}
