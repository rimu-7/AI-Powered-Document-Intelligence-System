import { apiClient } from "@/lib/api/client"
import type { components } from "@/lib/api/schema"

export type InvoiceDetail = components["schemas"]["InvoiceDetail"]
export type LineItemOut = components["schemas"]["LineItemOut"]
export type ValidationIssueOut = components["schemas"]["ValidationIssueOut"]
export type CorrectionRequest = components["schemas"]["CorrectionRequest"]
export type CorrectionResponse = components["schemas"]["CorrectionResponse"]
export type ApprovalRequest = components["schemas"]["ApprovalRequest"]
export type RejectionRequest = components["schemas"]["RejectionRequest"]
export type AuditEventOut = components["schemas"]["AuditEventOut"]

export const invoicesApi = {
  async get(id: string): Promise<InvoiceDetail> {
    const res = await apiClient.get<InvoiceDetail>(`/invoices/${id}`)
    return res.data
  },

  async lineItems(id: string): Promise<LineItemOut[]> {
    const res = await apiClient.get<LineItemOut[]>(`/invoices/${id}/line-items`)
    return res.data
  },

  async history(id: string): Promise<AuditEventOut[]> {
    const res = await apiClient.get<AuditEventOut[]>(`/invoices/${id}/history`)
    return res.data
  },

  async validations(id: string, params?: { severity?: string }): Promise<ValidationIssueOut[]> {
    const res = await apiClient.get<any>(`/invoices/${id}/validations`, { params })
    return Array.isArray(res.data) ? res.data : (res.data?.items ?? [])
  },

  async correct(id: string, payload: CorrectionRequest): Promise<CorrectionResponse> {
    const res = await apiClient.patch<CorrectionResponse>(`/invoices/${id}/corrections`, payload)
    return res.data
  },

  async approve(id: string, payload: ApprovalRequest): Promise<InvoiceDetail> {
    const res = await apiClient.post<InvoiceDetail>(`/invoices/${id}/approve`, payload)
    return res.data
  },

  async reject(id: string, payload: RejectionRequest): Promise<InvoiceDetail> {
    const res = await apiClient.post<InvoiceDetail>(`/invoices/${id}/reject`, payload)
    return res.data
  },

  async revalidate(id: string): Promise<{ job_id: string; status_url: string }> {
    const res = await apiClient.post<{ job_id: string; status_url: string }>(`/invoices/${id}/revalidate`)
    return res.data
  },
}

