import { useQuery } from "@tanstack/react-query"
import { searchApi, SearchFilters } from "./api"
import { qk } from "@/lib/api/keys"

export function useSearch(
  mode: "keyword" | "semantic" | "hybrid",
  query: string,
  filters?: SearchFilters,
  limit = 50,
  offset = 0
) {
  const isEnabled = Boolean(query && query.trim().length > 0)

  return useQuery({
    queryKey:
      mode === "keyword"
        ? qk.search.keyword({ query, filters, limit, offset })
        : mode === "semantic"
        ? qk.search.semantic({ query, filters, limit, offset })
        : qk.search.hybrid({ query, filters, limit, offset }),
    queryFn: () => {
      if (mode === "keyword") {
        return searchApi.keyword(query, filters, limit, offset)
      } else if (mode === "semantic") {
        return searchApi.semantic({
          query,
          limit,
          offset,
          filters: filters as any,
        })
      } else {
        return searchApi.hybrid({
          query,
          limit,
          offset,
          filters: filters as any,
        })
      }
    },
    enabled: isEnabled,
    staleTime: 60_000,
    placeholderData: (prev) => prev,
  })
}

