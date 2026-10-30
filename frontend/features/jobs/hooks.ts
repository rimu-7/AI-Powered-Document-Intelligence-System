import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { jobsApi, JobListParams } from "./api"
import { qk } from "@/lib/api/keys"
import { invalidateForMutation } from "@/lib/api/invalidation"
import { toast } from "sonner"
import { useRef, useEffect } from "react"

const TERMINAL_STATES = ["COMPLETED", "FAILED", "CANCELLED"]

export function isTerminal(state?: string): boolean {
  if (!state) return false
  return TERMINAL_STATES.includes(state.toUpperCase())
}

export function useJobList(params?: JobListParams) {
  return useQuery({
    queryKey: qk.jobs.list(params as Record<string, unknown>),
    queryFn: () => jobsApi.list(params),
    placeholderData: (previousData) => previousData,
    staleTime: 10_000,
    refetchInterval: (query) => {
      const items = query.state.data?.items
      if (!items || items.length === 0) return false
      const hasRunning = items.some((j) => !isTerminal(j.state))
      return hasRunning ? 3000 : false
    },
  })
}

export function useJob(id: string) {
  const queryClient = useQueryClient()
  const pollCountRef = useRef(0)
  const prevTerminalRef = useRef(false)

  const query = useQuery({
    queryKey: qk.jobs.detail(id),
    queryFn: () => jobsApi.get(id),
    enabled: !!id,
    refetchInterval: (q) => {
      const job = q.state.data
      if (!job || isTerminal(job.state)) {
        return false
      }
      pollCountRef.current += 1
      if (pollCountRef.current < 3) return 1000
      if (pollCountRef.current < 6) return 2000
      return 5000
    },
  })

  // Invalidate dependent queries once the job finishes
  useEffect(() => {
    const job = query.data
    if (!job) return

    const terminal = isTerminal(job.state)
    if (terminal && !prevTerminalRef.current) {
      prevTerminalRef.current = true
      if (job.document_id) {
        queryClient.invalidateQueries({
          queryKey: qk.documents.detail(job.document_id),
        })
        queryClient.invalidateQueries({
          queryKey: qk.documents.invoices(job.document_id),
        })
        queryClient.invalidateQueries({
          queryKey: qk.documents.validations(job.document_id),
        })
        queryClient.invalidateQueries({ queryKey: qk.reviews.queue() })
      }
      queryClient.invalidateQueries({ queryKey: qk.admin.stats() })
    } else if (!terminal) {
      prevTerminalRef.current = false
    }
  }, [query.data, queryClient])

  return query
}

export function useRetryJob() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => jobsApi.retry(id),
    onSuccess: async (_, id) => {
      await invalidateForMutation(queryClient, "retry_job", { jobId: id })
      toast.success("Job retry initiated")
    },
    onError: (err: any) => {
      toast.error(err.message || "Failed to retry job")
    },
  })
}

export function useCancelJob() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => jobsApi.cancel(id),
    onSuccess: async (_, id) => {
      await invalidateForMutation(queryClient, "cancel_job", { jobId: id })
      toast.success("Job cancelled")
    },
    onError: (err: any) => {
      toast.error(err.message || "Failed to cancel job")
    },
  })
}
