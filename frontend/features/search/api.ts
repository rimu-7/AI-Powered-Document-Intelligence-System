import { apiClient } from "@/lib/api/client"
import type { Res } from "@/lib/api/typed"
import type { components } from "@/lib/api/schema"
import type { CurrencyCode } from "@/lib/api/types"

export type SearchResponse = components["schemas"]["SearchResponse"]
export type SearchHit = components["schemas"]["SearchHit"]
export type SearchRequest = components["schemas"]["SearchRequest"]

export interface SearchFilters {
  supplier?: string
  currency?: CurrencyCode
  date_from?: string
  date_to?: string
  amount_min?: string
  amount_max?: string
  file_kind?: any[]
  document_type?: any[]
  status?: any[]
  validation_outcome?: any[]
}

export const searchApi = {
  async keyword(
    query: string,
    filters?: SearchFilters,
    limit = 50,
    offset = 0
  ): Promise<SearchResponse> {
    const res = await apiClient.get<Res<"GET /search/keyword">>(
      "/search/keyword",
      {
        params: {
          q: query,
          limit,
          offset,
          ...filters,
        },
      }
    )
    return res.data
  },

  async semantic(payload: SearchRequest): Promise<SearchResponse> {
    const res = await apiClient.post<Res<"POST /search/semantic">>(
      "/search/semantic",
      payload
    )
    return res.data
  },

  async hybrid(payload: SearchRequest): Promise<SearchResponse> {
    const res = await apiClient.post<Res<"POST /search/hybrid">>(
      "/search/hybrid",
      payload
    )
    return res.data
  },
}
