import { apiClient } from "@/lib/api/client"
import type { components } from "@/lib/api/schema"

export type ReviewQueueItem = components["schemas"]["ReviewQueueItem"]
export type Page_ReviewQueueItem_ =
  components["schemas"]["Page_ReviewQueueItem_"]
export type ReviewTaskOut = components["schemas"]["ReviewTaskOut"]
export type ReviewTaskStatus = components["schemas"]["ReviewTaskStatus"]

export interface ReviewQueueParams {
  status?: ReviewTaskStatus | null
  assigned_to_me?: boolean
  unassigned?: boolean
  limit?: number
  offset?: number
}

export const reviewsApi = {
  async queue(params?: ReviewQueueParams): Promise<Page_ReviewQueueItem_> {
    const res = await apiClient.get<Page_ReviewQueueItem_>("/reviews/queue", {
      params,
    })
    return res.data
  },

  async get(id: string): Promise<ReviewTaskOut> {
    const res = await apiClient.get<ReviewTaskOut>(`/reviews/${id}`)
    return res.data
  },

  async claim(id: string, force = false): Promise<ReviewTaskOut> {
    const res = await apiClient.post<ReviewTaskOut>(
      `/reviews/${id}/claim${force ? "?force=true" : ""}`
    )
    return res.data
  },
}
