import type { components } from "@/lib/api/schema"

type JobType = components["schemas"]["JobOut"]["job_type"]

const JOB_TYPES: Record<JobType, string> = {
  DOCUMENT_PROCESSING: "Document processing",
  REVALIDATION: "Revalidation",
  REINDEX: "Search reindex",
  COMPARISON: "Comparison",
  RECONCILIATION: "Reconciliation",
}

/** "DOCUMENT_PROCESSING" -> "Document processing" */
export function jobTypeLabel(type: string): string {
  return (
    JOB_TYPES[type as JobType] ??
    type.charAt(0) + type.slice(1).toLowerCase().replace(/_/g, " ")
  )
}
