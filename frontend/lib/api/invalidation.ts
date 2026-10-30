import { QueryClient } from "@tanstack/react-query"
import { qk } from "./keys"

export type MutationType =
  | "upload_documents"
  | "reprocess_document"
  | "delete_document"
  | "retry_job"
  | "cancel_job"
  | "correct_invoice"
  | "approve_invoice"
  | "reject_invoice"
  | "revalidate_invoice"
  | "claim_review"
  | "create_comparison"
  | "create_reconciliation"
  | "create_user"
  | "update_user"
  | "revoke_user_sessions"
  | "update_currency_settings"

export async function invalidateForMutation(
  queryClient: QueryClient,
  type: MutationType,
  context?: {
    documentId?: string
    invoiceId?: string
    jobId?: string
    reviewId?: string
    userId?: string
    comparisonId?: string
    reconciliationId?: string
  }
) {
  switch (type) {
    case "upload_documents":
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: qk.documents.all() }),
        queryClient.invalidateQueries({ queryKey: qk.jobs.all() }),
        queryClient.invalidateQueries({ queryKey: qk.admin.stats() }),
      ])
      break

    case "reprocess_document":
      if (context?.documentId) {
        await Promise.all([
          queryClient.invalidateQueries({
            queryKey: qk.documents.detail(context.documentId),
          }),
          queryClient.invalidateQueries({
            queryKey: qk.documents.jobs(context.documentId),
          }),
          queryClient.invalidateQueries({
            queryKey: qk.documents.invoices(context.documentId),
          }),
          queryClient.invalidateQueries({
            queryKey: qk.documents.validations(context.documentId),
          }),
          queryClient.invalidateQueries({ queryKey: qk.documents.all() }),
          queryClient.invalidateQueries({ queryKey: qk.jobs.all() }),
        ])
      }
      break

    case "delete_document":
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: qk.documents.all() }),
        queryClient.invalidateQueries({ queryKey: qk.reviews.all() }),
        queryClient.invalidateQueries({ queryKey: qk.admin.stats() }),
      ])
      break

    case "retry_job":
    case "cancel_job":
      if (context?.jobId) {
        await queryClient.invalidateQueries({
          queryKey: qk.jobs.detail(context.jobId),
        })
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: qk.jobs.all() }),
        queryClient.invalidateQueries({ queryKey: qk.admin.deadLetter() }),
        queryClient.invalidateQueries({ queryKey: qk.admin.stats() }),
      ])
      break

    case "correct_invoice":
    case "revalidate_invoice":
      if (context?.invoiceId) {
        await Promise.all([
          queryClient.invalidateQueries({
            queryKey: qk.invoices.detail(context.invoiceId),
          }),
          queryClient.invalidateQueries({
            queryKey: qk.invoices.validations(context.invoiceId),
          }),
          queryClient.invalidateQueries({
            queryKey: qk.invoices.history(context.invoiceId),
          }),
          queryClient.invalidateQueries({
            queryKey: qk.invoices.lineItems(context.invoiceId),
          }),
        ])
      }
      if (context?.documentId) {
        await Promise.all([
          queryClient.invalidateQueries({
            queryKey: qk.documents.detail(context.documentId),
          }),
          queryClient.invalidateQueries({
            queryKey: qk.documents.invoices(context.documentId),
          }),
          queryClient.invalidateQueries({
            queryKey: qk.documents.validations(context.documentId),
          }),
        ])
      }
      await queryClient.invalidateQueries({ queryKey: qk.reviews.all() })
      break

    case "approve_invoice":
    case "reject_invoice":
      if (context?.invoiceId) {
        await Promise.all([
          queryClient.invalidateQueries({
            queryKey: qk.invoices.detail(context.invoiceId),
          }),
          queryClient.invalidateQueries({
            queryKey: qk.invoices.history(context.invoiceId),
          }),
        ])
      }
      if (context?.documentId) {
        await queryClient.invalidateQueries({
          queryKey: qk.documents.detail(context.documentId),
        })
        await queryClient.invalidateQueries({
          queryKey: qk.documents.invoices(context.documentId),
        })
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: qk.reviews.all() }),
        queryClient.invalidateQueries({ queryKey: qk.admin.stats() }),
      ])
      break

    case "claim_review":
      await queryClient.invalidateQueries({ queryKey: qk.reviews.all() })
      if (context?.reviewId) {
        await queryClient.invalidateQueries({
          queryKey: qk.reviews.detail(context.reviewId),
        })
      }
      break

    case "create_comparison":
    case "create_reconciliation":
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: qk.comparisons.all() }),
        queryClient.invalidateQueries({ queryKey: qk.jobs.all() }),
      ])
      break

    case "update_currency_settings":
      // A policy change can resolve many waiting invoices at once.
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: qk.organization.currencySettings(),
        }),
        queryClient.invalidateQueries({ queryKey: qk.invoices.all() }),
        queryClient.invalidateQueries({ queryKey: qk.documents.all() }),
        queryClient.invalidateQueries({ queryKey: qk.reviews.all() }),
        queryClient.invalidateQueries({ queryKey: qk.admin.stats() }),
      ])
      break

    case "create_user":
    case "update_user":
    case "revoke_user_sessions":
      await queryClient.invalidateQueries({ queryKey: qk.admin.users() })
      break
  }
}
