import type { ComparisonOut, FindingStatus } from "./api"

export type Kind = ComparisonOut["comparison_type"]

/** What each side is called on screen. */
export function sideNames(
  comp: Pick<ComparisonOut, "comparison_type" | "documents">
) {
  if (comp.comparison_type === "PDF_SPREADSHEET")
    return { left: "PDFs", right: "Spreadsheet" }
  const left = comp.documents?.find((d) => d.side === "left")?.filename
  const right = comp.documents?.find((d) => d.side === "right")?.filename
  return { left: left ?? "Left", right: right ?? "Right" }
}

export function kindLabel(kind: Kind): string {
  return kind === "PDF_SPREADSHEET" ? "Reconciliation" : "PDF comparison"
}

export interface StatusMeta {
  label: string
  /** Tailwind classes for the badge. */
  tone: string
  /** One-line explanation, shown as a tooltip and in the legend. */
  help: string
}

export function statusMeta(status: FindingStatus, kind: Kind): StatusMeta {
  const rec = kind === "PDF_SPREADSHEET"
  switch (status) {
    case "MATCH":
      return {
        label: "Match",
        tone: "bg-emerald-500/10 text-emerald-700 border-emerald-500/30 dark:text-emerald-400",
        help: "Both sides agree.",
      }
    case "MISMATCH":
      return {
        label: "Different",
        tone: "bg-rose-500/10 text-rose-700 border-rose-500/30 dark:text-rose-400",
        help: "Found on both sides, but values differ.",
      }
    case "MISSING_RIGHT":
      return {
        label: rec ? "Not in spreadsheet" : "Only on left",
        tone: "bg-amber-500/10 text-amber-700 border-amber-500/30 dark:text-amber-400",
        help: rec
          ? "This invoice has no row in the spreadsheet."
          : "This invoice is not in the right-hand document.",
      }
    case "MISSING_LEFT":
      return {
        label: rec ? "Not in PDFs" : "Only on right",
        tone: "bg-amber-500/10 text-amber-700 border-amber-500/30 dark:text-amber-400",
        help: rec
          ? "This spreadsheet row has no matching invoice in the PDFs."
          : "This invoice is not in the left-hand document.",
      }
    case "AMBIGUOUS":
      return {
        label: "Needs confirmation",
        tone: "bg-violet-500/10 text-violet-700 border-violet-500/30 dark:text-violet-400",
        help: "A likely match that a person should confirm, or several possible matches.",
      }
    case "DUPLICATE":
      return {
        label: "Duplicate",
        tone: "bg-zinc-500/10 text-zinc-700 border-zinc-500/30 dark:text-zinc-300",
        help: "The same invoice appears more than once.",
      }
    default:
      return {
        label: "Can't compare",
        tone: "bg-muted text-muted-foreground border-border",
        help: "A value is missing on one side, or the currencies differ.",
      }
  }
}

const FIELDS: Record<string, string> = {
  invoice_number: "Invoice number",
  supplier_name: "Supplier",
  customer_name: "Customer",
  invoice_date: "Invoice date",
  currency: "Currency",
  subtotal: "Subtotal",
  tax_amount: "Tax",
  total_amount: "Total",
}

/** "total_amount" -> "Total", "line_items[3]" -> "Line 3", "line_items[r2]" -> "Line 2 (right only)" */
export function fieldName(field: string): string {
  if (FIELDS[field]) return FIELDS[field]
  const line = /^line_items\[(r?)(\d+)\]$/.exec(field)
  if (line) return `Line ${line[2]}${line[1] ? " (right only)" : ""}`
  return field.replace(/_/g, " ")
}

/** "2141.9100" -> "2141.91"; other text is left alone. */
export function trimAmount(text: string): string {
  const m = /^(-?\d+)\.(\d{2})(\d*)$/.exec(text)
  if (!m || /[1-9]/.test(m[3])) return text
  return `${m[1]}.${m[2]}`
}

/** Display text for a finding value (strings, numbers, lists, line items). */
export function showValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—"
  if (typeof value === "string") return trimAmount(value)
  if (Array.isArray(value)) return value.map(showValue).join(" · ")
  if (typeof value === "object") {
    const v = value as Record<string, unknown>
    if ("description" in v || "line_total" in v)
      return [v.description, v.line_total]
        .filter((x) => x != null)
        .map((x) => showValue(x))
        .join(" — ")
    return Object.entries(v)
      .map(([k, x]) => `${k}: ${showValue(x)}`)
      .join(", ")
  }
  return String(value)
}

/** Plain-English text for `difference_json` of a field finding. */
export function showDifference(diff: unknown): string | null {
  if (diff === null || diff === undefined) return null
  if (typeof diff !== "object") return String(diff)
  const d = diff as Record<string, unknown>
  if (typeof d.difference === "string") {
    const text = trimAmount(d.difference)
    return Number(text) > 0 ? `+${text}` : text
  }
  if (typeof d.days === "number")
    return `${Math.abs(d.days)} ${Math.abs(d.days) === 1 ? "day" : "days"} ${d.days > 0 ? "later" : "earlier"}`
  if (typeof d.similarity === "string") {
    const score = /:(\d+)/.exec(d.similarity)?.[1]
    return score ? `${score}% similar` : d.similarity
  }
  if (typeof d.reason === "string") return d.reason
  return null
}

/** Why a record got its status, from the record finding's `difference_json`. */
export function recordReason(
  status: FindingStatus,
  diff: unknown,
  kind: Kind
): string | null {
  const d = (diff ?? {}) as Record<string, unknown>
  const list = (key: string) =>
    Array.isArray(d[key]) ? (d[key] as string[]).map(fieldName) : []
  if (typeof d.reason === "string") {
    if (d.reason === "multiple candidate matches")
      return "Several records could be this invoice. Pick the right one by hand."
    if (d.reason.startsWith("fuzzy invoice-number"))
      return "The invoice numbers are nearly identical (a likely scanning error). Check that it is the same invoice."
    if (d.reason.startsWith("same invoice number belongs"))
      return "The same invoice number exists on the other side, but from a different supplier, so it is not treated as a match."
    if (d.reason.startsWith("no invoice number"))
      return "No invoice number, and several records share the same supplier, date and total."
    return d.reason
  }
  if (d.duplicate_of)
    return "This row repeats an earlier row for the same invoice."
  const parts: string[] = []
  if (d.match_quality === "no_invoice_number")
    parts.push(
      "Paired on supplier, date and total because one side has no invoice number."
    )
  else if (
    typeof d.match_quality === "string" &&
    d.match_quality.startsWith("fuzzy")
  )
    parts.push("Supplier names are similar but not identical.")
  const different = list("mismatched_fields")
  if (different.length) parts.push(`Different: ${different.join(", ")}.`)
  const uncertain = list("uncertain_fields")
  if (uncertain.length) parts.push(`Check: ${uncertain.join(", ")}.`)
  const lines = list("missing_lines")
  if (lines.length)
    parts.push(
      `${lines.length} line ${lines.length === 1 ? "item" : "items"} only on one side.`
    )
  if (!parts.length && status === "MATCH") return "Every compared value agrees."
  if (!parts.length && status === "MISSING_RIGHT")
    return statusMeta(status, kind).help
  if (!parts.length && status === "MISSING_LEFT")
    return statusMeta(status, kind).help
  return parts.join(" ") || null
}

export interface Ref {
  document_id?: string
  filename?: string
  invoice_record_id?: string
  page_start?: number | null
  sheet_name?: string | null
  row_number?: number | null
  field?: { page_number?: number; cell?: string; supporting_text?: string }
}

/** "page 2" / "Sheet1, row 14" / "cell C14" */
export function whereText(ref: Ref | undefined): string | null {
  if (!ref) return null
  if (ref.field?.cell) return `cell ${ref.field.cell}`
  if (ref.field?.page_number) return `page ${ref.field.page_number}`
  if (ref.row_number != null)
    return `${ref.sheet_name ? `${ref.sheet_name}, ` : ""}row ${ref.row_number}`
  if (ref.page_start) return `page ${ref.page_start}`
  return null
}

/** Link to open the invoice (or the spreadsheet) this side refers to. */
export function refHref(ref: Ref | undefined): string | null {
  if (!ref) return null
  if (ref.invoice_record_id) {
    const page = ref.field?.page_number ?? ref.page_start
    return `/invoices/${ref.invoice_record_id}${page ? `?page=${page}` : ""}`
  }
  if (ref.document_id) return `/documents/${ref.document_id}`
  return null
}
