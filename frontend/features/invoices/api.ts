import { apiClient } from "@/lib/api/client"
import type { Res } from "@/lib/api/typed"
import type { components } from "@/lib/api/schema"
import { fetchAllPages } from "@/lib/api/pages"

export type InvoiceDetail = components["schemas"]["InvoiceDetail"]
export type LineItemOut = components["schemas"]["LineItemOut"]
export type ValidationIssueOut = components["schemas"]["ValidationIssueOut"]
export type CorrectionRequest = components["schemas"]["CorrectionRequest"]
export type CorrectionResponse = components["schemas"]["CorrectionResponse"]
export type ApprovalRequest = components["schemas"]["ApprovalRequest"]
export type RejectionRequest = components["schemas"]["RejectionRequest"]
export type AuditEventOut = components["schemas"]["AuditEventOut"]
export type ReviewActionOut = components["schemas"]["ReviewActionOut"]
export type InvoiceOut = components["schemas"]["InvoiceOut"]

export const invoicesApi = {
  async get(id: string): Promise<InvoiceDetail> {
    const res = await apiClient.get<Res<"GET /invoices/{invoice_id}">>(
      `/invoices/${id}`
    )
    return res.data
  },

  async lineItems(id: string): Promise<LineItemOut[]> {
    const res = await apiClient.get<
      Res<"GET /invoices/{invoice_id}/line-items">
    >(`/invoices/${id}/line-items`)
    return res.data
  },

  /** Corrections, approvals and rejections, oldest first. */
  async history(id: string): Promise<ReviewActionOut[]> {
    const res = await apiClient.get<Res<"GET /invoices/{invoice_id}/history">>(
      `/invoices/${id}/history`
    )
    return res.data
  },

  async validations(
    id: string,
    params?: { severity?: string }
  ): Promise<ValidationIssueOut[]> {
    return fetchAllPages(async (offset, limit) => {
      const res = await apiClient.get<
        Res<"GET /invoices/{invoice_id}/validations">
      >(`/invoices/${id}/validations`, { params: { ...params, offset, limit } })
      return res.data
    })
  },

  async correct(
    id: string,
    payload: CorrectionRequest
  ): Promise<CorrectionResponse> {
    const res = await apiClient.patch<
      Res<"PATCH /invoices/{invoice_id}/corrections">
    >(`/invoices/${id}/corrections`, payload)
    return res.data
  },

  async approve(id: string, payload: ApprovalRequest): Promise<InvoiceOut> {
    const res = await apiClient.post<
      Res<"POST /invoices/{invoice_id}/approve">
    >(`/invoices/${id}/approve`, payload)
    return res.data
  },

  async reject(id: string, payload: RejectionRequest): Promise<InvoiceOut> {
    const res = await apiClient.post<Res<"POST /invoices/{invoice_id}/reject">>(
      `/invoices/${id}/reject`,
      payload
    )
    return res.data
  },

  async revalidate(
    id: string
  ): Promise<{ job_id: string; status_url: string }> {
    const res = await apiClient.post<
      Res<"POST /invoices/{invoice_id}/revalidate">
    >(`/invoices/${id}/revalidate`)
    return res.data
  },
}
