import { apiClient } from "@/lib/api/client"
import type { Res } from "@/lib/api/typed"
import type { components } from "@/lib/api/schema"
import { fetchAllPages } from "@/lib/api/pages"

export type DocumentOut = components["schemas"]["DocumentOut"]
export type Page_DocumentOut_ = components["schemas"]["Page_DocumentOut_"]
export type PageOut = components["schemas"]["PageOut"]
export type Page_PageOut_ = components["schemas"]["Page_PageOut_"]
export type PageText = components["schemas"]["PageText"]
export type TableOut = components["schemas"]["TableOut"]
export type Page_TableOut_ = components["schemas"]["Page_TableOut_"]
export type RowOut = components["schemas"]["RowOut"]
export type Page_RowOut_ = components["schemas"]["Page_RowOut_"]
export type ValidationIssueOut = components["schemas"]["ValidationIssueOut"]
export type Page_ValidationIssueOut_ =
  components["schemas"]["Page_ValidationIssueOut_"]
export type MappingSuggestions = components["schemas"]["MappingSuggestions"]
export type JobOut = components["schemas"]["JobOut"]
export type InvoiceOut = components["schemas"]["InvoiceOut"]

export interface DocumentListParams {
  limit?: number
  offset?: number
  status?: string
  document_type?: string
  file_kind?: string
  filename?: string
  created_from?: string
  created_to?: string
}

export const documentsApi = {
  async list(params?: DocumentListParams): Promise<Page_DocumentOut_> {
    const res = await apiClient.get<Res<"GET /documents">>("/documents", {
      params,
    })
    return res.data
  },

  async get(id: string): Promise<DocumentOut> {
    const res = await apiClient.get<Res<"GET /documents/{document_id}">>(
      `/documents/${id}`
    )
    return res.data
  },

  async download(
    id: string,
    mode?: "direct" | "presigned"
  ): Promise<Blob | { url: string }> {
    if (mode === "presigned") {
      // Not described in the schema: the endpoint also streams the raw file.
      const res = await apiClient.get<{ url: string; expires_in: number }>(
        `/documents/${id}/download`,
        { params: { mode: "presigned" } }
      )
      return res.data
    }
    const res = await apiClient.get(`/documents/${id}/download`, {
      responseType: "blob",
    })
    return res.data
  },

  async pages(
    id: string,
    params?: { limit?: number; offset?: number }
  ): Promise<Page_PageOut_> {
    const res = await apiClient.get<Res<"GET /documents/{document_id}/pages">>(
      `/documents/${id}/pages`,
      {
        params,
      }
    )
    return res.data
  },

  getPageImageUrl(id: string, pageNumber: number, width?: number): string {
    const params = new URLSearchParams()
    if (width) params.set("width", String(width))
    const query = params.toString()
    return `/bff/api/v1/documents/${id}/pages/${pageNumber}/image${query ? `?${query}` : ""}`
  },

  async text(id: string, page_from = 1, page_to?: number): Promise<PageText[]> {
    const res = await apiClient.get<Res<"GET /documents/{document_id}/text">>(
      `/documents/${id}/text`,
      {
        params: { page_from, ...(page_to ? { page_to } : {}) },
      }
    )
    return res.data
  },

  async tables(
    id: string,
    params?: { limit?: number; offset?: number }
  ): Promise<Page_TableOut_> {
    const res = await apiClient.get<Res<"GET /documents/{document_id}/tables">>(
      `/documents/${id}/tables`,
      {
        params,
      }
    )
    return res.data
  },

  async tableRows(
    docId: string,
    tableId: string,
    params?: { limit?: number; offset?: number }
  ): Promise<Page_RowOut_> {
    const res = await apiClient.get<
      Res<"GET /documents/{document_id}/tables/{table_id}/rows">
    >(`/documents/${docId}/tables/${tableId}/rows`, { params })
    return res.data
  },

  async mappingSuggestions(id: string): Promise<MappingSuggestions[]> {
    const res = await apiClient.get<
      Res<"GET /documents/{document_id}/spreadsheet/mapping-suggestions">
    >(`/documents/${id}/spreadsheet/mapping-suggestions`)
    return res.data
  },

  /** Every processing run of this document, newest first. */
  async jobs(id: string): Promise<JobOut[]> {
    const jobs = await fetchAllPages(async (offset, limit) => {
      const res = await apiClient.get<Res<"GET /documents/{document_id}/jobs">>(
        `/documents/${id}/jobs`,
        { params: { offset, limit } }
      )
      return res.data
    })
    return jobs.sort((a, b) => b.created_at.localeCompare(a.created_at))
  },

  async invoices(
    id: string,
    include_superseded = false
  ): Promise<InvoiceOut[]> {
    const res = await apiClient.get<
      Res<"GET /documents/{document_id}/invoices">
    >(`/documents/${id}/invoices`, {
      params: { include_superseded },
    })
    return res.data
  },

  async validations(
    id: string,
    params?: { severity?: string; limit?: number; offset?: number }
  ): Promise<Page_ValidationIssueOut_> {
    const res = await apiClient.get<
      Res<"GET /documents/{document_id}/validations">
    >(`/documents/${id}/validations`, { params })
    return res.data
  },

  async reprocess(id: string): Promise<{ job_id: string; status_url: string }> {
    const res = await apiClient.post<
      Res<"POST /documents/{document_id}/reprocess">
    >(`/documents/${id}/reprocess`)
    return res.data
  },

  async delete(id: string): Promise<void> {
    await apiClient.delete<Res<"DELETE /documents/{document_id}">>(
      `/documents/${id}`
    )
  },
}
