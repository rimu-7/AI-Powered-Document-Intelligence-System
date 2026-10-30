import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query"
import {
  comparisonsApi,
  ComparisonCreate,
  FindingParams,
  ReconciliationCreate,
} from "./api"
import { qk } from "@/lib/api/keys"
import { invalidateForMutation } from "@/lib/api/invalidation"
import { toast } from "sonner"

export function useComparisonsList(params?: {
  limit?: number
  offset?: number
}) {
  return useQuery({
    queryKey: qk.comparisons.list(params),
    queryFn: () => comparisonsApi.list(params),
    placeholderData: (prev) => prev,
    staleTime: 15_000,
  })
}

export function useComparison(id: string) {
  return useQuery({
    queryKey: qk.comparisons.detail(id),
    queryFn: () => comparisonsApi.getComparison(id),
    enabled: !!id,
    refetchInterval: (query) => {
      const comp = query.state.data
      if (!comp) return false
      if (comp.status === "QUEUED" || comp.status === "RUNNING") {
        return 1500
      }
      return false
    },
  })
}

/** Results exist only once the run has finished; `ready` gates the fetch. */
export function useComparisonFindings(
  id: string,
  params: FindingParams,
  { ready = true }: { ready?: boolean } = {}
) {
  return useQuery({
    queryKey: qk.comparisons.findings(id, { ...params }),
    queryFn: () => comparisonsApi.comparisonFindings(id, params),
    enabled: !!id && ready,
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  })
}

export function useRerunComparison() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => comparisonsApi.rerun(id),
    onSuccess: async () => {
      await invalidateForMutation(queryClient, "create_comparison")
      toast.success("Running again on the current data")
    },
    onError: (err: any) => {
      toast.error(err.message || "Could not run the comparison again")
    },
  })
}

export function useReconciliation(id: string) {
  return useQuery({
    queryKey: qk.reconciliations.detail(id),
    queryFn: () => comparisonsApi.getReconciliation(id),
    enabled: !!id,
    refetchInterval: (query) => {
      const rec = query.state.data
      if (!rec) return false
      if (rec.status === "QUEUED" || rec.status === "RUNNING") {
        return 3000
      }
      return false
    },
  })
}

export function useReconciliationFindings(
  id: string,
  params?: {
    records_only?: boolean
    finding_status?: string
    limit?: number
    offset?: number
  }
) {
  return useQuery({
    queryKey: qk.reconciliations.findings(id, params),
    queryFn: () => comparisonsApi.reconciliationFindings(id, params),
    enabled: !!id,
  })
}

export function useCreateComparison() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: ComparisonCreate) =>
      comparisonsApi.createComparison(
        payload,
        typeof crypto !== "undefined" ? crypto.randomUUID() : undefined
      ),
    onSuccess: async () => {
      await invalidateForMutation(queryClient, "create_comparison")
      toast.success("Comparison started")
    },
    onError: (err: any) => {
      toast.error(err.message || "Failed to start comparison")
    },
  })
}

export function useCreateReconciliation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: ReconciliationCreate) =>
      comparisonsApi.createReconciliation(
        payload,
        typeof crypto !== "undefined" ? crypto.randomUUID() : undefined
      ),
    onSuccess: async () => {
      await invalidateForMutation(queryClient, "create_reconciliation")
      toast.success("Reconciliation started")
    },
    onError: (err: any) => {
      toast.error(err.message || "Failed to start reconciliation")
    },
  })
}
