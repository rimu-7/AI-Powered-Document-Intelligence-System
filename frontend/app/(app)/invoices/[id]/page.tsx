"use client"

import React, { use, useState, useEffect } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import {
  useInvoice,
  useInvoiceLineItems,
  useInvoiceHistory,
  useInvoiceValidations,
  useCorrectInvoice,
  useApproveInvoice,
  useRejectInvoice,
  useRevalidateInvoice,
} from "@/features/invoices/hooks"
import type {
  LineItemOut,
  ValidationIssueOut,
  AuditEventOut,
} from "@/features/invoices/api"
import { useCurrentUser } from "@/features/auth/hooks"
import { hasPermission } from "@/lib/permissions"
import {
  InvoiceViewer,
  EvidenceBox,
} from "@/features/invoices/components/invoice-viewer"
import { StatusBadge } from "@/components/status-badge"
import { Money } from "@/components/money"
import { CurrencySelect } from "@/components/currency-select"
import type { CurrencyCode } from "@/lib/api/types"
import { DateTime } from "@/components/date-time"
import { ErrorState } from "@/components/error-state"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Check,
  X,
  Edit2,
  Save,
  RotateCw,
  AlertTriangle,
  History,
  FileSpreadsheet,
  FileText,
} from "lucide-react"
import { toast } from "sonner"

export default function InvoiceReviewPage({
  params,
}: {
  params: Promise<{ id: string }> | { id: string }
}) {
  const resolvedParams =
    params instanceof Promise ||
    (params && typeof (params as any).then === "function")
      ? use(params as Promise<{ id: string }>)
      : (params as { id: string })
  const id = resolvedParams.id
  const router = useRouter()
  const { data: user } = useCurrentUser()

  const { data: invoice, isLoading, isError, error, refetch } = useInvoice(id)
  const { data: rawLineItems = [] } = useInvoiceLineItems(id)
  const { data: rawHistory = [] } = useInvoiceHistory(id)
  const { data: issues = [] } = useInvoiceValidations(id)

  const lineItems = (
    Array.isArray(rawLineItems)
      ? rawLineItems
      : ((rawLineItems as any)?.items ?? [])
  ) as LineItemOut[]
  const history = (
    Array.isArray(rawHistory) ? rawHistory : ((rawHistory as any)?.items ?? [])
  ) as AuditEventOut[]
  const issueList = React.useMemo(
    () =>
      (Array.isArray(issues)
        ? issues
        : ((issues as any)?.items ?? [])) as ValidationIssueOut[],
    [issues]
  )

  const currencyCandidates: CurrencyCode[] = React.useMemo(() => {
    // 1. From alternatives_json.alternatives.currency
    const alts = (invoice?.alternatives_json as any)?.alternatives?.currency
    if (Array.isArray(alts) && alts.length > 0) return alts as CurrencyCode[]

    // 2. From INVALID_CURRENCY issue details_json.candidates
    const invalidCurrencyIssue = issueList.find(
      (i) => i.rule_code === "INVALID_CURRENCY"
    )
    const issueCandidates = (invalidCurrencyIssue?.details_json as any)
      ?.candidates
    if (Array.isArray(issueCandidates) && issueCandidates.length > 0) {
      return issueCandidates as CurrencyCode[]
    }

    return []
  }, [invoice?.alternatives_json, issueList])

  const { mutate: correctInvoice, isPending: isSavingCorrection } =
    useCorrectInvoice()
  const { mutate: approveInvoice, isPending: isApproving } = useApproveInvoice()
  const { mutate: rejectInvoice, isPending: isRejecting } = useRejectInvoice()
  const { mutate: revalidateInvoice, isPending: isRevalidating } =
    useRevalidateInvoice()

  const [activeEvidence, setActiveEvidence] = useState<EvidenceBox | null>(null)
  const [mobileView, setMobileView] = useState<"viewer" | "data">("data")
  const [activeTab, setActiveTab] = useState<string>("fields")
  const [isEditing, setIsEditing] = useState(false)
  const [editedFields, setEditedFields] = useState<Record<string, string>>({})
  const [editedCurrency, setEditedCurrency] = useState<CurrencyCode | null>(
    null
  )
  const [correctionErrors, setCorrectionErrors] = useState<
    Record<string, string>
  >({})
  const [correctionReason, setCorrectionReason] = useState("")

  // Dialog States
  const [approveOpen, setApproveOpenState] = useState(false)
  const [acknowledgeIssues, setAcknowledgeIssues] = useState(false)
  const [approveReason, setApproveReason] = useState("")
  const [approveError, setApproveError] = useState<string | null>(null)

  const setApproveOpen = (open: boolean) => {
    if (open) {
      setAcknowledgeIssues(false)
      setApproveReason("")
      setApproveError(null)
    }
    setApproveOpenState(open)
  }

  const [rejectOpen, setRejectOpen] = useState(false)
  const [rejectReason, setRejectReason] = useState("")

  const [conflictOpen, setConflictOpen] = useState(false)

  // Keyboard navigation (§6.3)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (["INPUT", "TEXTAREA"].includes((e.target as HTMLElement)?.tagName)) {
        return
      }

      if (e.key === "e") {
        e.preventDefault()
        setIsEditing((v) => !v)
      } else if (e.key === "a") {
        e.preventDefault()
        if (invoice?.review_status !== "APPROVED") setApproveOpen(true)
      } else if (e.key === "]") {
        e.preventDefault()
        router.push("/reviews")
      }
    }

    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [router, invoice?.review_status])

  const handleFieldClick = (fieldName: string) => {
    const evidence = (invoice?.source_evidence_json as any)?.[fieldName] as
      EvidenceBox | undefined
    if (evidence) {
      setActiveEvidence(evidence)
      setMobileView("viewer")
    }
  }

  const handleStartEdit = (preselectedCurrency?: CurrencyCode | null) => {
    if (!invoice) return
    setEditedFields({
      invoice_number: invoice.invoice_number || "",
      invoice_date: invoice.invoice_date || "",
      payment_due_date: invoice.payment_due_date || "",
      supplier_name: invoice.supplier_name || "",
      supplier_tax_id: invoice.supplier_tax_id || "",
      subtotal: invoice.subtotal || "",
      tax_amount: invoice.tax_amount || "",
      total_amount: invoice.total_amount || "",
    })
    setEditedCurrency(
      preselectedCurrency !== undefined
        ? preselectedCurrency
        : (invoice.currency ?? null)
    )
    setCorrectionReason("")
    setCorrectionErrors({})
    setIsEditing(true)
  }

  const handleSaveCorrection = () => {
    if (!invoice) return
    setCorrectionErrors({})
    if (!correctionReason.trim()) {
      toast.error("A reason for the correction is required.")
      return
    }

    const changes: { field_path: string; value: any }[] = Object.entries(
      editedFields
    )
      .filter(([key, val]) => {
        const original = (invoice as any)[key] || ""
        return String(val) !== String(original)
      })
      .map(([field_path, value]) => ({
        field_path,
        value: value.trim() === "" ? null : value.trim(),
      }))

    // Only send the currency change if it differs from invoice.currency
    if (editedCurrency !== invoice.currency) {
      changes.push({
        field_path: "currency",
        value: editedCurrency,
      })
    }

    if (changes.length === 0) {
      setIsEditing(false)
      return
    }

    correctInvoice(
      {
        id,
        payload: {
          expected_version: invoice.version,
          reason: correctionReason,
          changes,
        },
      },
      {
        onSuccess: () => {
          setIsEditing(false)
          setCorrectionErrors({})
        },
        onError: (err: any) => {
          if (err.status === 409 && err.code === "VERSION_CONFLICT") {
            setConflictOpen(true)
          } else if (
            err.status === 422 ||
            err.code === "INVALID_CORRECTION_VALUE"
          ) {
            const msg = err.message || "Invalid correction value"
            if (msg.toLowerCase().includes("currency")) {
              setCorrectionErrors((prev) => ({ ...prev, currency: msg }))
            } else {
              setCorrectionErrors((prev) => ({ ...prev, general: msg }))
            }
          }
        },
      }
    )
  }

  const handleApprove = () => {
    if (!invoice) return
    setApproveError(null)
    approveInvoice(
      {
        id,
        payload: {
          expected_version: invoice.version,
          reason: approveReason.trim() || null,
          acknowledge_issues: acknowledgeIssues,
        },
      },
      {
        onSuccess: () => {
          setApproveOpen(false)
        },
        onError: (err: any) => {
          switch (err.code) {
            case "BLOCKING_ISSUES":
              setApproveError(
                "This invoice has open errors. Tick the acknowledgement and give a reason, or correct the invoice first."
              )
              break
            case "REVALIDATION_PENDING":
              setApproveError(
                "Revalidation is still running. Wait a few seconds, then approve again."
              )
              break
            case "VERSION_CONFLICT":
              setApproveOpen(false)
              setConflictOpen(true)
              break
            case "ALREADY_APPROVED":
              setApproveOpen(false)
              toast.info("This invoice is already approved.")
              break
            case "INVOICE_SUPERSEDED":
              setApproveOpen(false)
              toast.error(
                "This invoice was replaced by a newer extraction. Open the document to review the current one."
              )
              break
            default:
              if (err.status === 409) setApproveError(err.message)
          }
        },
      }
    )
  }

  const handleReject = () => {
    if (!invoice) return
    if (!rejectReason || rejectReason.trim().length < 3) {
      toast.error("Rejection reason must be at least 3 characters.")
      return
    }

    rejectInvoice(
      {
        id,
        payload: {
          expected_version: invoice.version,
          reason: rejectReason,
        },
      },
      {
        onSuccess: () => {
          setRejectOpen(false)
        },
      }
    )
  }

  if (isLoading) {
    return (
      <div className="grid h-[calc(100vh-8rem)] grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="h-full animate-pulse rounded-lg bg-muted" />
        <div className="h-full animate-pulse rounded-lg bg-muted" />
      </div>
    )
  }

  if (isError || !invoice) {
    return (
      <ErrorState
        message={(error as any)?.message || "Invoice not found"}
        requestId={(error as any)?.requestId}
        onRetry={() => refetch()}
      />
    )
  }

  const blockingIssues = issueList.filter(
    (i) =>
      (i.severity === "ERROR" || i.severity === "CRITICAL") &&
      i.resolution_status === "OPEN"
  )
  const severityRank: Record<string, number> = {
    CRITICAL: 0,
    ERROR: 1,
    WARNING: 2,
    INFO: 3,
  }
  const sortedIssues = [...issueList].sort(
    (a, b) => (severityRank[a.severity] ?? 9) - (severityRank[b.severity] ?? 9)
  )
  const reasonRequired = blockingIssues.length > 0
  const canConfirmApproval =
    !isApproving &&
    (!reasonRequired || (acknowledgeIssues && approveReason.trim().length >= 3))
  const isApproved = invoice.review_status === "APPROVED"

  const sourceEvidence = (invoice.source_evidence_json || {}) as Record<
    string,
    any
  >
  const correctedFields = Array.isArray(invoice.corrected_fields_json)
    ? invoice.corrected_fields_json
    : []

  return (
    <div className="flex min-h-0 flex-col gap-3 lg:h-[calc(100vh-8rem)]">
      {/* Action Header */}
      <div className="flex shrink-0 flex-col gap-3 rounded-lg border bg-card p-3 sm:flex-row sm:items-center sm:justify-between sm:p-4">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <h2 className="truncate text-sm font-bold tracking-tight sm:text-base md:text-lg">
            Invoice: {invoice.invoice_number || "Draft"}
          </h2>
          <StatusBadge status={invoice.review_status} />
          <StatusBadge status={invoice.validation_outcome} />
          <span className="rounded bg-muted px-2 py-0.5 font-mono text-[11px] text-muted-foreground sm:text-xs">
            v{invoice.version}
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
          {hasPermission(user?.role, "INVOICE_CORRECT") && (
            <Button
              variant={isEditing ? "default" : "outline"}
              size="sm"
              onClick={
                isEditing ? handleSaveCorrection : () => handleStartEdit()
              }
              disabled={isSavingCorrection}
              className="h-8 gap-1.5 text-xs"
            >
              {isEditing ? (
                <Save className="h-3.5 w-3.5" />
              ) : (
                <Edit2 className="h-3.5 w-3.5" />
              )}
              {isEditing
                ? isSavingCorrection
                  ? "Saving..."
                  : "Save Changes"
                : "Edit"}
            </Button>
          )}

          {isEditing && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsEditing(false)}
              className="h-8 text-xs"
            >
              Cancel
            </Button>
          )}

          <Button
            variant="outline"
            size="sm"
            onClick={() => revalidateInvoice(id)}
            disabled={isRevalidating}
            className="h-8 gap-1.5 text-xs"
          >
            <RotateCw
              className={`h-3.5 w-3.5 ${isRevalidating ? "animate-spin" : ""}`}
            />
            <span className="hidden sm:inline">Revalidate</span>
          </Button>

          {hasPermission(user?.role, "INVOICE_REJECT") && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setRejectOpen(true)}
              className="h-8 gap-1.5 text-xs text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/20"
            >
              <X className="h-3.5 w-3.5" />
              <span>Reject</span>
            </Button>
          )}

          {hasPermission(user?.role, "INVOICE_APPROVE") && (
            <Button
              size="sm"
              onClick={() => setApproveOpen(true)}
              disabled={isApproved}
              className="h-8 gap-1.5 bg-emerald-600 text-xs text-white hover:bg-emerald-700"
            >
              <Check className="h-3.5 w-3.5" />
              <span>{isApproved ? "Approved" : "Approve"}</span>
            </Button>
          )}
        </div>
      </div>

      {/* Mobile Mode Switcher (< lg) */}
      <div className="flex shrink-0 items-center gap-1 rounded-lg border bg-muted/60 p-1 text-xs lg:hidden">
        <button
          type="button"
          onClick={() => setMobileView("viewer")}
          className={`flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-1.5 font-medium transition-all ${
            mobileView === "viewer"
              ? "bg-background text-foreground shadow-xs"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          <FileText className="h-3.5 w-3.5" />
          <span>Document Preview</span>
        </button>
        <button
          type="button"
          onClick={() => setMobileView("data")}
          className={`flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-1.5 font-medium transition-all ${
            mobileView === "data"
              ? "bg-background text-foreground shadow-xs"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          <FileSpreadsheet className="h-3.5 w-3.5" />
          <span>Invoice Details</span>
          {blockingIssues.length > 0 && (
            <span className="flex h-1.5 w-1.5 animate-pulse rounded-full bg-rose-500" />
          )}
        </button>
      </div>

      {/* Main Split Screen */}
      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Left: Document Page Viewer with Evidence Overlay */}
        <div
          className={`min-h-0 lg:h-full ${
            mobileView === "viewer"
              ? "block h-[calc(100vh-14rem)] min-h-[460px]"
              : "hidden lg:block"
          }`}
        >
          <InvoiceViewer
            documentId={invoice.document_id}
            pageStart={invoice.page_start}
            activeEvidence={activeEvidence}
          />
        </div>

        {/* Right: Fields, Line Items, Issues, History */}
        <div
          className={`flex h-full min-h-0 flex-col overflow-hidden rounded-lg border bg-card ${
            mobileView === "data"
              ? "flex h-[calc(100vh-14rem)] min-h-[460px]"
              : "hidden lg:flex"
          }`}
        >
          <Tabs
            value={activeTab}
            onValueChange={setActiveTab}
            className="flex min-h-0 flex-1 flex-col"
          >
            <div className="shrink-0 overflow-x-auto border-b bg-muted/30 px-3 pt-2 sm:px-4 sm:pt-3">
              <TabsList className="grid h-auto w-full grid-cols-4 gap-0.5 bg-muted p-1 sm:flex sm:w-auto">
                <TabsTrigger
                  value="fields"
                  className="gap-1 px-1.5 py-1.5 text-xs sm:gap-1.5 sm:px-3"
                >
                  <FileText className="h-3.5 w-3.5" />
                  <span className="truncate">Fields</span>
                </TabsTrigger>
                <TabsTrigger
                  value="line_items"
                  className="gap-1 px-1.5 py-1.5 text-xs sm:gap-1.5 sm:px-3"
                >
                  <FileSpreadsheet className="h-3.5 w-3.5" />
                  <span className="truncate">
                    Line Items ({lineItems.length})
                  </span>
                </TabsTrigger>
                <TabsTrigger
                  value="issues"
                  className="gap-1 px-1.5 py-1.5 text-xs sm:gap-1.5 sm:px-3"
                >
                  <AlertTriangle className="h-3.5 w-3.5" />
                  <span className="truncate">Issues ({issueList.length})</span>
                </TabsTrigger>
                <TabsTrigger
                  value="history"
                  className="gap-1 px-1.5 py-1.5 text-xs sm:gap-1.5 sm:px-3"
                >
                  <History className="h-3.5 w-3.5" />
                  <span className="truncate">History</span>
                </TabsTrigger>
              </TabsList>
            </div>

            <TabsContent
              value="fields"
              className="m-0 flex-1 space-y-4 overflow-y-auto p-4"
            >
              {isEditing ? (
                <div className="space-y-4">
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <div>
                      <Label className="text-xs">Invoice Number</Label>
                      <Input
                        value={editedFields.invoice_number || ""}
                        onChange={(e) =>
                          setEditedFields((p) => ({
                            ...p,
                            invoice_number: e.target.value,
                          }))
                        }
                        className="mt-1 h-8 font-mono text-xs"
                      />
                    </div>
                    <div>
                      <Label className="text-xs">Supplier Name</Label>
                      <Input
                        value={editedFields.supplier_name || ""}
                        onChange={(e) =>
                          setEditedFields((p) => ({
                            ...p,
                            supplier_name: e.target.value,
                          }))
                        }
                        className="mt-1 h-8 text-xs"
                      />
                    </div>
                    <div>
                      <Label className="text-xs">Invoice Date</Label>
                      <Input
                        type="date"
                        value={editedFields.invoice_date || ""}
                        onChange={(e) =>
                          setEditedFields((p) => ({
                            ...p,
                            invoice_date: e.target.value,
                          }))
                        }
                        className="mt-1 h-8 font-mono text-xs"
                      />
                    </div>
                    <div>
                      <Label className="text-xs">Due Date</Label>
                      <Input
                        type="date"
                        value={editedFields.payment_due_date || ""}
                        onChange={(e) =>
                          setEditedFields((p) => ({
                            ...p,
                            payment_due_date: e.target.value,
                          }))
                        }
                        className="mt-1 h-8 font-mono text-xs"
                      />
                    </div>
                    <div>
                      <Label className="text-xs">Currency</Label>
                      <div className="mt-1">
                        <CurrencySelect
                          value={editedCurrency}
                          onChange={(c) => {
                            setEditedCurrency(c)
                            if (correctionErrors.currency) {
                              setCorrectionErrors((prev) => {
                                const next = { ...prev }
                                delete next.currency
                                return next
                              })
                            }
                          }}
                          candidates={currencyCandidates}
                        />
                      </div>
                      {correctionErrors.currency && (
                        <p className="mt-1 text-[11px] font-medium text-destructive">
                          {correctionErrors.currency}
                        </p>
                      )}
                    </div>
                    <div>
                      <Label className="text-xs">Total Amount</Label>
                      <Input
                        value={editedFields.total_amount || ""}
                        onChange={(e) =>
                          setEditedFields((p) => ({
                            ...p,
                            total_amount: e.target.value,
                          }))
                        }
                        className="mt-1 h-8 font-mono text-xs"
                      />
                    </div>
                    <div>
                      <Label className="text-xs">Subtotal (Net)</Label>
                      <Input
                        value={editedFields.subtotal || ""}
                        onChange={(e) =>
                          setEditedFields((p) => ({
                            ...p,
                            subtotal: e.target.value,
                          }))
                        }
                        className="mt-1 h-8 font-mono text-xs"
                      />
                    </div>
                    <div>
                      <Label className="text-xs">Tax Amount</Label>
                      <Input
                        value={editedFields.tax_amount || ""}
                        onChange={(e) =>
                          setEditedFields((p) => ({
                            ...p,
                            tax_amount: e.target.value,
                          }))
                        }
                        className="mt-1 h-8 font-mono text-xs"
                      />
                    </div>
                  </div>

                  <div className="pt-2">
                    <Label className="text-xs font-medium">
                      Correction Reason (required)
                    </Label>
                    <Textarea
                      placeholder="Explain why fields were corrected..."
                      value={correctionReason}
                      onChange={(e) => setCorrectionReason(e.target.value)}
                      className="mt-1 text-xs"
                      rows={2}
                    />
                    {correctionErrors.general && (
                      <p className="mt-1 text-xs text-destructive">
                        {correctionErrors.general}
                      </p>
                    )}
                  </div>
                </div>
              ) : (
                <div className="divide-y divide-border text-xs">
                  <FieldRow
                    label="Invoice Number"
                    value={invoice.invoice_number}
                    isCorrected={correctedFields.includes("invoice_number")}
                    evidence={sourceEvidence.invoice_number as EvidenceBox}
                    onClick={() => handleFieldClick("invoice_number")}
                  />
                  <FieldRow
                    label="Supplier"
                    value={invoice.supplier_name}
                    isCorrected={correctedFields.includes("supplier_name")}
                    evidence={sourceEvidence.supplier_name as EvidenceBox}
                    onClick={() => handleFieldClick("supplier_name")}
                  />
                  <FieldRow
                    label="Supplier Tax ID"
                    value={invoice.supplier_tax_id}
                    evidence={sourceEvidence.supplier_tax_id as EvidenceBox}
                    onClick={() => handleFieldClick("supplier_tax_id")}
                  />
                  <FieldRow
                    label="Invoice Date"
                    value={invoice.invoice_date}
                    evidence={sourceEvidence.invoice_date as EvidenceBox}
                    onClick={() => handleFieldClick("invoice_date")}
                  />
                  <FieldRow
                    label="Payment Due Date"
                    value={invoice.payment_due_date}
                    evidence={sourceEvidence.payment_due_date as EvidenceBox}
                    onClick={() => handleFieldClick("payment_due_date")}
                  />
                  <FieldRow
                    label="Currency"
                    value={
                      invoice.currency ? (
                        <span className="font-mono font-semibold">
                          {invoice.currency}
                        </span>
                      ) : (
                        <div className="flex items-center gap-2">
                          <span className="text-muted-foreground">
                            {invoice.currency_raw
                              ? `${invoice.currency_raw} – not confirmed`
                              : "—"}
                          </span>
                          {hasPermission(user?.role, "INVOICE_CORRECT") && (
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              className="h-6 px-2 text-[10px]"
                              onClick={(e) => {
                                e.stopPropagation()
                                handleStartEdit()
                                setActiveTab("fields")
                              }}
                            >
                              Set currency
                            </Button>
                          )}
                        </div>
                      )
                    }
                    isCorrected={correctedFields.includes("currency")}
                    evidence={sourceEvidence.currency as EvidenceBox}
                    onClick={() => handleFieldClick("currency")}
                  />
                  <FieldRow
                    label="Subtotal (Net)"
                    value={
                      invoice.subtotal ? (
                        <Money
                          value={invoice.subtotal}
                          currency={invoice.currency}
                          raw={invoice.currency_raw}
                        />
                      ) : (
                        "—"
                      )
                    }
                    evidence={sourceEvidence.subtotal as EvidenceBox}
                    onClick={() => handleFieldClick("subtotal")}
                  />
                  <FieldRow
                    label="Tax Amount"
                    value={
                      invoice.tax_amount ? (
                        <Money
                          value={invoice.tax_amount}
                          currency={invoice.currency}
                          raw={invoice.currency_raw}
                        />
                      ) : (
                        "—"
                      )
                    }
                    evidence={sourceEvidence.tax_amount as EvidenceBox}
                    onClick={() => handleFieldClick("tax_amount")}
                  />
                  <FieldRow
                    label="Total Amount"
                    value={
                      invoice.total_amount ? (
                        <Money
                          value={invoice.total_amount}
                          currency={invoice.currency}
                          raw={invoice.currency_raw}
                        />
                      ) : (
                        "—"
                      )
                    }
                    isCorrected={correctedFields.includes("total_amount")}
                    evidence={sourceEvidence.total_amount as EvidenceBox}
                    onClick={() => handleFieldClick("total_amount")}
                  />
                </div>
              )}
            </TabsContent>

            <TabsContent
              value="line_items"
              className="m-0 flex-1 overflow-y-auto p-4"
            >
              {lineItems.length === 0 ? (
                <div className="py-8 text-center text-xs text-muted-foreground">
                  No line items extracted.
                </div>
              ) : (
                <div className="space-y-3">
                  {/* Mobile / Tablet Container Cards */}
                  <div className="space-y-2 lg:hidden">
                    {lineItems.map((item, idx) => (
                      <div
                        key={item.id}
                        className="space-y-1.5 rounded-lg border bg-card p-3 text-xs"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex min-w-0 items-center gap-1.5">
                            <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
                              #{idx + 1}
                            </span>
                            <span className="truncate font-medium text-foreground">
                              {item.description || "Line Item"}
                            </span>
                          </div>
                          <span className="shrink-0 font-mono font-semibold text-foreground">
                            <Money
                              value={item.line_total}
                              currency={invoice.currency}
                              raw={invoice.currency_raw}
                            />
                          </span>
                        </div>
                        <div className="flex items-center justify-between border-t border-border/40 pt-1 font-mono text-[11px] text-muted-foreground">
                          <span>Qty: {item.quantity || "1"}</span>
                          <span>
                            Unit:{" "}
                            {item.unit_price ? (
                              <Money
                                value={item.unit_price}
                                currency={invoice.currency}
                                raw={invoice.currency_raw}
                              />
                            ) : (
                              "—"
                            )}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* Desktop Table View */}
                  <div className="hidden overflow-hidden rounded-lg border lg:block">
                    <Table>
                      <TableHeader className="bg-muted/40">
                        <TableRow>
                          <TableHead className="w-12">#</TableHead>
                          <TableHead>Description</TableHead>
                          <TableHead className="text-right">Qty</TableHead>
                          <TableHead className="text-right">
                            Unit Price
                          </TableHead>
                          <TableHead className="text-right">Total</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {lineItems.map((item, idx) => (
                          <TableRow key={item.id} className="text-xs">
                            <TableCell className="font-mono text-muted-foreground">
                              {idx + 1}
                            </TableCell>
                            <TableCell className="font-medium">
                              {item.description}
                            </TableCell>
                            <TableCell className="text-right font-mono">
                              {item.quantity || "1"}
                            </TableCell>
                            <TableCell className="text-right font-mono">
                              {item.unit_price ? (
                                <Money
                                  value={item.unit_price}
                                  currency={invoice.currency}
                                  raw={invoice.currency_raw}
                                />
                              ) : (
                                "—"
                              )}
                            </TableCell>
                            <TableCell className="text-right font-mono font-medium">
                              <Money
                                value={item.line_total}
                                currency={invoice.currency}
                                raw={invoice.currency_raw}
                              />
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                </div>
              )}
            </TabsContent>

            <TabsContent
              value="issues"
              className="m-0 flex-1 space-y-3 overflow-y-auto p-4"
            >
              {issueList.length === 0 ? (
                <div className="py-8 text-center text-xs text-muted-foreground">
                  No issues reported for this invoice.
                </div>
              ) : (
                sortedIssues.map((iss) => {
                  const details = (iss.details_json ?? {}) as Record<
                    string,
                    any
                  >
                  const isNote = iss.severity === "INFO"
                  return (
                    <div
                      key={iss.id}
                      className={`space-y-1.5 rounded-lg border p-3 text-xs ${isNote ? "bg-muted/40" : "bg-card"}`}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <StatusBadge status={iss.severity} />
                          <span className="font-mono font-medium">
                            {iss.rule_code}
                          </span>
                        </div>
                        {/* INFO entries are notes about how a value was obtained; they need no action. */}
                        {!isNote && (
                          <StatusBadge status={iss.resolution_status} />
                        )}
                      </div>
                      <p className="text-foreground/90">{iss.message}</p>
                      {iss.field_path && (
                        <p className="font-mono text-[11px] text-muted-foreground">
                          Field: {iss.field_path}
                        </p>
                      )}
                      {iss.rule_code === "INVALID_CURRENCY" &&
                        Array.isArray(details.candidates) &&
                        details.candidates.length > 0 && (
                          <div className="mt-2 space-y-1.5 rounded-md border border-border/60 bg-muted/30 p-2.5">
                            <p className="text-[11px] font-medium text-muted-foreground">
                              Suggested currencies:
                            </p>
                            <div className="flex flex-wrap gap-1.5">
                              {details.candidates.map((code: CurrencyCode) => (
                                <Button
                                  key={code}
                                  type="button"
                                  variant="outline"
                                  size="sm"
                                  className="h-6 px-2 font-mono text-xs font-semibold hover:bg-primary hover:text-primary-foreground"
                                  onClick={() => {
                                    handleStartEdit(code)
                                    setCorrectionReason(
                                      `Resolve INVALID_CURRENCY: set to ${code}`
                                    )
                                    setActiveTab("fields")
                                  }}
                                >
                                  {code}
                                </Button>
                              ))}
                            </div>
                          </div>
                        )}
                      {iss.rule_code === "DUPLICATE_INVOICE" &&
                        details.other_document_id && (
                          <Link
                            href={`/documents/${details.other_document_id}`}
                            className="inline-block text-[11px] font-medium text-primary underline-offset-4 hover:underline"
                          >
                            Open{" "}
                            {details.other_filename
                              ? `"${details.other_filename}"`
                              : "the other document"}
                            {details.other_review_status
                              ? ` (${String(details.other_review_status).toLowerCase()})`
                              : ""}
                          </Link>
                        )}
                    </div>
                  )
                })
              )}
            </TabsContent>

            <TabsContent
              value="history"
              className="m-0 flex-1 space-y-3 overflow-y-auto p-4"
            >
              {history.length === 0 ? (
                <div className="py-8 text-center text-xs text-muted-foreground">
                  No modification history.
                </div>
              ) : (
                history.map((evt) => (
                  <div
                    key={evt.id}
                    className="space-y-1 rounded-lg border bg-card p-3 text-xs"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-mono font-semibold uppercase">
                        {evt.action}
                      </span>
                      <DateTime value={evt.created_at} />
                    </div>
                    {evt.actor_id && (
                      <p className="font-mono text-[11px] text-muted-foreground">
                        Actor: {evt.actor_id}
                      </p>
                    )}
                  </div>
                ))
              )}
            </TabsContent>
          </Tabs>
        </div>
      </div>

      {/* Approve Dialog */}
      <Dialog open={approveOpen} onOpenChange={setApproveOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Approve Invoice</DialogTitle>
            <DialogDescription>
              Confirm approval of invoice #
              {invoice.invoice_number || invoice.id}.
            </DialogDescription>
          </DialogHeader>

          {blockingIssues.length > 0 && (
            <div className="space-y-2 rounded-md border border-amber-500/30 bg-amber-500/15 p-3 text-xs text-amber-800 dark:text-amber-300">
              <div className="flex items-center gap-1.5 font-semibold">
                <AlertTriangle className="h-4 w-4" /> Open Blocking Issues (
                {blockingIssues.length})
              </div>
              <ul className="list-disc space-y-1 pl-4">
                {blockingIssues.map((bi) => (
                  <li key={bi.id}>
                    <strong>{bi.rule_code}:</strong> {bi.message}
                  </li>
                ))}
              </ul>
              <div className="flex items-center gap-2 pt-2">
                <Checkbox
                  id="ack-issues"
                  checked={acknowledgeIssues}
                  onCheckedChange={(c) => setAcknowledgeIssues(!!c)}
                />
                <Label
                  htmlFor="ack-issues"
                  className="cursor-pointer text-xs font-medium"
                >
                  I acknowledge these issues and wish to approve anyway
                </Label>
              </div>
            </div>
          )}

          <div className="space-y-2 pt-2">
            <Label htmlFor="approve-reason" className="text-xs">
              {reasonRequired
                ? "Reason (required to approve with open errors)"
                : "Approval notes (optional)"}
            </Label>
            <Textarea
              id="approve-reason"
              placeholder={
                reasonRequired
                  ? "e.g. Same invoice as the PDF copy; approving this one and rejecting the other"
                  : "e.g. Verified with purchasing director"
              }
              value={approveReason}
              onChange={(e) => setApproveReason(e.target.value)}
              className="text-xs"
              rows={2}
              maxLength={1000}
            />
          </div>

          {approveError && (
            <p role="alert" className="text-xs font-medium text-destructive">
              {approveError}
            </p>
          )}

          <DialogFooter>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setApproveOpen(false)}
            >
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={handleApprove}
              disabled={!canConfirmApproval}
              className="bg-emerald-600 text-white hover:bg-emerald-700"
            >
              {isApproving ? "Approving..." : "Confirm Approval"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Reject Dialog */}
      <Dialog open={rejectOpen} onOpenChange={setRejectOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reject Invoice</DialogTitle>
            <DialogDescription>
              State the reason for rejecting invoice #
              {invoice.invoice_number || invoice.id}.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-2">
            <Label className="text-xs">
              Rejection Reason (min 3 characters)
            </Label>
            <Textarea
              placeholder="e.g. Total does not match line item sum, incorrect VAT calculation"
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              className="text-xs"
              rows={3}
            />
          </div>

          <DialogFooter>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setRejectOpen(false)}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={handleReject}
              disabled={isRejecting || rejectReason.trim().length < 3}
            >
              {isRejecting ? "Rejecting..." : "Confirm Rejection"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Version Conflict Dialog */}
      <Dialog open={conflictOpen} onOpenChange={setConflictOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Version Conflict</DialogTitle>
            <DialogDescription>
              This invoice was updated by another user or background task while
              you were viewing it. Please reload to view the latest changes
              before reapplying your edits.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              size="sm"
              onClick={() => {
                setConflictOpen(false)
                refetch()
              }}
            >
              Reload Latest Version
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

function FieldRow({
  label,
  value,
  isCorrected,
  evidence,
  onClick,
}: {
  label: string
  value: React.ReactNode
  isCorrected?: boolean
  evidence?: EvidenceBox
  onClick: () => void
}) {
  return (
    <div
      onClick={onClick}
      className="group flex cursor-pointer items-center justify-between rounded px-3 py-2.5 transition-colors hover:bg-muted/40"
    >
      <div className="flex min-w-0 flex-col">
        <span className="text-[11px] font-medium text-muted-foreground">
          {label}
        </span>
        <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
          <span className="text-xs font-medium text-foreground">
            {value || "—"}
          </span>
          {isCorrected && (
            <span className="rounded bg-amber-500/10 px-1 font-mono text-[10px] font-medium text-amber-600">
              corrected
            </span>
          )}
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-2">
        {evidence && (
          <span className="flex items-center gap-0.5 font-mono text-[10px] text-primary/70 group-hover:text-primary">
            P.{evidence.page_number || 1}
          </span>
        )}
      </div>
    </div>
  )
}
