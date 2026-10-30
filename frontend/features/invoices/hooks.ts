import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  invoicesApi,
  CorrectionRequest,
  ApprovalRequest,
  RejectionRequest,
} from "./api"
import { qk } from "@/lib/api/keys"
import { invalidateForMutation } from "@/lib/api/invalidation"
import { toast } from "sonner"

export function useInvoice(id: string) {
  return useQuery({
    queryKey: qk.invoices.detail(id),
    queryFn: () => invoicesApi.get(id),
    enabled: !!id,
    staleTime: 30_000,
  })
}

export function useInvoiceLineItems(id: string) {
  return useQuery({
    queryKey: qk.invoices.lineItems(id),
    queryFn: () => invoicesApi.lineItems(id),
    enabled: !!id,
    staleTime: 30_000,
  })
}

export function useInvoiceHistory(id: string) {
  return useQuery({
    queryKey: qk.invoices.history(id),
    queryFn: () => invoicesApi.history(id),
    enabled: !!id,
    staleTime: 30_000,
  })
}

export function useInvoiceValidations(
  id: string,
  params?: { severity?: string }
) {
  return useQuery({
    queryKey: qk.invoices.validations(id, params),
    queryFn: () => invoicesApi.validations(id, params),
    enabled: !!id,
    staleTime: 30_000,
  })
}

export function useCorrectInvoice() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: CorrectionRequest }) =>
      invoicesApi.correct(id, payload),
    onSuccess: async (data, { id }) => {
      await invalidateForMutation(queryClient, "correct_invoice", {
        invoiceId: id,
        documentId: data.invoice.document_id,
      })
      toast.success("Invoice corrections saved. Revalidating...")
    },
    onError: (err: any) => {
      if (err.status === 409 && err.code === "VERSION_CONFLICT") {
        toast.error(
          "Version conflict: The invoice was modified by another user."
        )
      } else {
        toast.error(err.message || "Failed to save corrections")
      }
    },
  })
}

export function useApproveInvoice() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: ApprovalRequest }) =>
      invoicesApi.approve(id, payload),
    onSuccess: async (data, { id }) => {
      await invalidateForMutation(queryClient, "approve_invoice", {
        invoiceId: id,
        documentId: data.document_id,
      })
      toast.success("Invoice approved successfully")
    },
    onError: async (err: any, { id }) => {
      // The approve dialog shows these inline; refresh what the server based them on.
      if (err.status === 409) {
        await queryClient.invalidateQueries({ queryKey: ["invoices", id] })
        return
      }
      toast.error(err.message || "Failed to approve invoice")
    },
  })
}

export function useRejectInvoice() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: RejectionRequest }) =>
      invoicesApi.reject(id, payload),
    onSuccess: async (data, { id }) => {
      await invalidateForMutation(queryClient, "reject_invoice", {
        invoiceId: id,
        documentId: data.document_id,
      })
      toast.success("Invoice rejected")
    },
    onError: (err: any) => {
      toast.error(err.message || "Failed to reject invoice")
    },
  })
}

export function useRevalidateInvoice() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => invoicesApi.revalidate(id),
    onSuccess: async (_, id) => {
      await invalidateForMutation(queryClient, "revalidate_invoice", {
        invoiceId: id,
      })
      toast.success("Revalidation started")
    },
    onError: (err: any) => {
      toast.error(err.message || "Failed to trigger revalidation")
    },
  })
}
