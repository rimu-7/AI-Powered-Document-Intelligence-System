import { apiClient } from "@/lib/api/client"
import type { Res } from "@/lib/api/typed"
import type { components } from "@/lib/api/schema"

export type JobOut = components["schemas"]["JobOut"]
export type JobDetail = components["schemas"]["JobDetail"]
export type Page_JobOut_ = components["schemas"]["Page_JobOut_"]
export type TaskOut = components["schemas"]["TaskOut"]
export type ActiveJob = components["schemas"]["ActiveJobOut"]

export interface JobListParams {
  limit?: number
  offset?: number
  state?: string
  job_type?: string
  document_id?: string
}

export const jobsApi = {
  async list(params?: JobListParams): Promise<Page_JobOut_> {
    const res = await apiClient.get<Res<"GET /jobs">>("/jobs", { params })
    return res.data
  },

  async active(): Promise<ActiveJob[]> {
    const res = await apiClient.get<Res<"GET /jobs/active">>("/jobs/active")
    return res.data
  },

  async get(id: string): Promise<JobDetail> {
    const res = await apiClient.get<Res<"GET /jobs/{job_id}">>(`/jobs/${id}`)
    return res.data
  },

  async retry(id: string): Promise<{ job_id: string; status_url: string }> {
    const res = await apiClient.post<Res<"POST /jobs/{job_id}/retry">>(
      `/jobs/${id}/retry`
    )
    return res.data
  },

  async cancel(id: string): Promise<void> {
    await apiClient.post<Res<"POST /jobs/{job_id}/cancel">>(
      `/jobs/${id}/cancel`
    )
  },
}
