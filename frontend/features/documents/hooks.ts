import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { documentsApi, DocumentListParams } from "./api"
import { qk } from "@/lib/api/keys"
import { invalidateForMutation } from "@/lib/api/invalidation"
import { toast } from "sonner"

export function useDocumentsList(params?: DocumentListParams) {
  return useQuery({
    queryKey: qk.documents.list(params as Record<string, unknown>),
    queryFn: () => documentsApi.list(params),
    placeholderData: (previousData) => previousData,
    staleTime: 30_000,
  })
}

export function useDocument(id: string) {
  const queryClient = useQueryClient()
  return useQuery({
    queryKey: qk.documents.detail(id),
    queryFn: () => documentsApi.get(id),
    initialData: () => {
      // Seed detail from list cache if available (§3.3)
      const listData = queryClient.getQueriesData<{ items?: { id: string }[] }>({
        queryKey: qk.documents.all(),
      })
      for (const [, cache] of listData) {
        const found = cache?.items?.find((item) => item.id === id)
        if (found) return found as any
      }
      return undefined
    },
    staleTime: 30_000,
    enabled: !!id,
  })
}

export function useDocumentPages(id: string, params?: { limit?: number; offset?: number }) {
  return useQuery({
    queryKey: qk.documents.pages(id, params),
    queryFn: () => documentsApi.pages(id, params),
    enabled: !!id,
  })
}

export function useDocumentText(id: string, page_from = 1, page_to?: number) {
  return useQuery({
    queryKey: qk.documents.text(id, { page_from, page_to }),
    queryFn: () => documentsApi.text(id, page_from, page_to),
    enabled: !!id,
  })
}

export function useDocumentTables(id: string, params?: { limit?: number; offset?: number }) {
  return useQuery({
    queryKey: qk.documents.tables(id, params),
    queryFn: () => documentsApi.tables(id, params),
    enabled: !!id,
  })
}

export function useDocumentTableRows(docId: string, tableId: string, params?: { limit?: number; offset?: number }) {
  return useQuery({
    queryKey: qk.documents.tableRows(docId, tableId, params),
    queryFn: () => documentsApi.tableRows(docId, tableId, params),
    enabled: !!docId && !!tableId,
  })
}

export function useDocumentMappingSuggestions(id: string) {
  return useQuery({
    queryKey: qk.documents.mappingSuggestions(id),
    queryFn: () => documentsApi.mappingSuggestions(id),
    enabled: !!id,
  })
}

export function useDocumentJobs(id: string) {
  return useQuery({
    queryKey: qk.documents.jobs(id),
    queryFn: () => documentsApi.jobs(id),
    enabled: !!id,
    refetchInterval: (query) => {
      // Poll if any job is still running
      const jobs = query.state.data
      if (!jobs || jobs.length === 0) return false
      const hasRunning = jobs.some((j) => !["COMPLETED", "FAILED", "CANCELLED"].includes(j.state))
      return hasRunning ? 3000 : false
    },
  })
}

export function useDocumentInvoices(id: string, include_superseded = false) {
  return useQuery({
    queryKey: qk.documents.invoices(id),
    queryFn: () => documentsApi.invoices(id, include_superseded),
    enabled: !!id,
  })
}

export function useDocumentValidations(id: string, params?: { severity?: string; limit?: number; offset?: number }) {
  return useQuery({
    queryKey: qk.documents.validations(id, params),
    queryFn: () => documentsApi.validations(id, params),
    enabled: !!id,
  })
}

export function useReprocessDocument() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => documentsApi.reprocess(id),
    onSuccess: async (_, id) => {
      await invalidateForMutation(queryClient, "reprocess_document", { documentId: id })
      toast.success("Document re-processing started")
    },
    onError: (err: any) => {
      toast.error(err.message || "Failed to trigger re-processing")
    },
  })
}

export function useDeleteDocument() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => documentsApi.delete(id),
    onSuccess: async () => {
      await invalidateForMutation(queryClient, "delete_document")
      toast.success("Document deleted")
    },
    onError: (err: any) => {
      toast.error(err.message || "Failed to delete document")
    },
  })
}

