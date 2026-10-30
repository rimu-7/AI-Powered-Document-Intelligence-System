import { apiClient } from "@/lib/api/client"
import type { components } from "@/lib/api/schema"

export type JobOut = components["schemas"]["JobOut"]
export type JobDetail = components["schemas"]["JobDetail"]
export type Page_JobOut_ = components["schemas"]["Page_JobOut_"]
export type TaskOut = components["schemas"]["TaskOut"]

export interface JobListParams {
  limit?: number
  offset?: number
  state?: string
  job_type?: string
  document_id?: string
}

export const jobsApi = {
  async list(params?: JobListParams): Promise<Page_JobOut_> {
    const res = await apiClient.get<Page_JobOut_>("/jobs", { params })
    return res.data
  },

  async get(id: string): Promise<JobDetail> {
    const res = await apiClient.get<JobDetail>(`/jobs/${id}`)
    return res.data
  },

  async retry(id: string): Promise<{ job_id: string; status_url: string }> {
    const res = await apiClient.post<{ job_id: string; status_url: string }>(
      `/jobs/${id}/retry`
    )
    return res.data
  },

  async cancel(id: string): Promise<void> {
    await apiClient.post(`/jobs/${id}/cancel`)
  },
}
