"use client"

import React, { use, useState, useEffect } from "react"
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
import type { LineItemOut, ValidationIssueOut, AuditEventOut } from "@/features/invoices/api"
import { useCurrentUser } from "@/features/auth/hooks"
import { hasPermission } from "@/lib/permissions"
import { InvoiceViewer, EvidenceBox } from "@/features/invoices/components/invoice-viewer"
import { StatusBadge } from "@/components/status-badge"
import { Money } from "@/components/money"
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
    params instanceof Promise || (params && typeof (params as any).then === "function")
      ? use(params as Promise<{ id: string }>)
      : (params as { id: string })
  const id = resolvedParams.id
  const router = useRouter()
  const { data: user } = useCurrentUser()

  const { data: invoice, isLoading, isError, error, refetch } = useInvoice(id)
  const { data: rawLineItems = [] } = useInvoiceLineItems(id)
  const { data: rawHistory = [] } = useInvoiceHistory(id)
  const { data: issues = [] } = useInvoiceValidations(id)

  const lineItems = (Array.isArray(rawLineItems) ? rawLineItems : (rawLineItems as any)?.items ?? []) as LineItemOut[]
  const history = (Array.isArray(rawHistory) ? rawHistory : (rawHistory as any)?.items ?? []) as AuditEventOut[]

  const { mutate: correctInvoice, isPending: isSavingCorrection } = useCorrectInvoice()
  const { mutate: approveInvoice, isPending: isApproving } = useApproveInvoice()
  const { mutate: rejectInvoice, isPending: isRejecting } = useRejectInvoice()
  const { mutate: revalidateInvoice, isPending: isRevalidating } = useRevalidateInvoice()

  const [activeEvidence, setActiveEvidence] = useState<EvidenceBox | null>(null)
  const [isEditing, setIsEditing] = useState(false)
  const [editedFields, setEditedFields] = useState<Record<string, string>>({})
  const [correctionReason, setCorrectionReason] = useState("")

  // Dialog States
  const [approveOpen, setApproveOpen] = useState(false)
  const [acknowledgeIssues, setAcknowledgeIssues] = useState(false)
  const [approveReason, setApproveReason] = useState("")

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
        setApproveOpen(true)
      } else if (e.key === "]") {
        e.preventDefault()
        router.push("/reviews")
      }
    }

    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [router])

  const handleFieldClick = (fieldName: string) => {
    const evidence = (invoice?.source_evidence_json as any)?.[fieldName] as EvidenceBox | undefined
    if (evidence) {
      setActiveEvidence(evidence)
    }
  }

  const handleStartEdit = () => {
    if (!invoice) return
    setEditedFields({
      invoice_number: invoice.invoice_number || "",
      invoice_date: invoice.invoice_date || "",
      payment_due_date: invoice.payment_due_date || "",
      supplier_name: invoice.supplier_name || "",
      supplier_tax_id: invoice.supplier_tax_id || "",
      currency: invoice.currency || "EUR",
      subtotal: invoice.subtotal || "",
      tax_amount: invoice.tax_amount || "",
      total_amount: invoice.total_amount || "",
    })
    setCorrectionReason("")
    setIsEditing(true)
  }

  const handleSaveCorrection = () => {
    if (!invoice) return
    if (!correctionReason.trim()) {
      toast.error("A reason for the correction is required.")
      return
    }

    const changes = Object.entries(editedFields)
      .filter(([key, val]) => {
        const original = (invoice as any)[key] || ""
        return String(val) !== String(original)
      })
      .map(([field_path, value]) => ({ field_path, value }))

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
        },
        onError: (err: any) => {
          if (err.status === 409 && err.code === "VERSION_CONFLICT") {
            setConflictOpen(true)
          }
        },
      }
    )
  }

  const handleApprove = () => {
    if (!invoice) return
    approveInvoice(
      {
        id,
        payload: {
          expected_version: invoice.version,
          reason: approveReason || null,
          acknowledge_issues: acknowledgeIssues,
        },
      },
      {
        onSuccess: () => {
          setApproveOpen(false)
        },
        onError: (err: any) => {
          if (err.status === 409 && err.code === "BLOCKING_ISSUES") {
            // Handled inside dialog
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
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 h-[calc(100vh-8rem)]">
        <div className="h-full bg-muted animate-pulse rounded-lg" />
        <div className="h-full bg-muted animate-pulse rounded-lg" />
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

  const issueList = (Array.isArray(issues) ? issues : (issues as any)?.items ?? []) as ValidationIssueOut[]

  const blockingIssues = issueList.filter(
    (i) => (i.severity === "ERROR" || i.severity === "CRITICAL") && i.resolution_status === "OPEN"
  )

  const sourceEvidence = (invoice.source_evidence_json || {}) as Record<string, any>
  const correctedFields = Array.isArray(invoice.corrected_fields_json) ? invoice.corrected_fields_json : []

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)] gap-4">
      {/* Action Header */}
      <div className="flex items-center justify-between gap-4 p-4 border rounded-lg bg-card shrink-0">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-bold tracking-tight">
            Invoice: {invoice.invoice_number || "Draft"}
          </h2>
          <StatusBadge status={invoice.review_status} />
          <StatusBadge status={invoice.validation_outcome} />
          <span className="text-xs font-mono bg-muted px-2 py-0.5 rounded text-muted-foreground">
            Version {invoice.version}
          </span>
        </div>

        <div className="flex items-center gap-2">
          {hasPermission(user?.role, "INVOICE_CORRECT") && (
            <Button
              variant={isEditing ? "default" : "outline"}
              size="sm"
              onClick={isEditing ? handleSaveCorrection : handleStartEdit}
              disabled={isSavingCorrection}
              className="gap-1.5 text-xs"
            >
              {isEditing ? <Save className="h-3.5 w-3.5" /> : <Edit2 className="h-3.5 w-3.5" />}
              {isEditing ? (isSavingCorrection ? "Saving..." : "Save Changes") : "Edit (e)"}
            </Button>
          )}

          {isEditing && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsEditing(false)}
              className="text-xs"
            >
              Cancel
            </Button>
          )}

          <Button
            variant="outline"
            size="sm"
            onClick={() => revalidateInvoice(id)}
            disabled={isRevalidating}
            className="gap-1.5 text-xs"
          >
            <RotateCw className={`h-3.5 w-3.5 ${isRevalidating ? "animate-spin" : ""}`} />
            Revalidate
          </Button>

          {hasPermission(user?.role, "INVOICE_REJECT") && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setRejectOpen(true)}
              className="gap-1.5 text-xs text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/20"
            >
              <X className="h-3.5 w-3.5" />
              Reject
            </Button>
          )}

          {hasPermission(user?.role, "INVOICE_APPROVE") && (
            <Button
              size="sm"
              onClick={() => setApproveOpen(true)}
              className="gap-1.5 text-xs bg-emerald-600 hover:bg-emerald-700 text-white"
            >
              <Check className="h-3.5 w-3.5" />
              Approve (a)
            </Button>
          )}
        </div>
      </div>

      {/* Main Split Screen */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 flex-1 min-h-0">
        {/* Left: Document Page Viewer with Evidence Overlay */}
        <div className="h-full min-h-[400px]">
          <InvoiceViewer
            documentId={invoice.document_id}
            pageStart={invoice.page_start}
            activeEvidence={activeEvidence}
          />
        </div>

        {/* Right: Fields, Line Items, Issues, History */}
        <div className="h-full flex flex-col border rounded-lg overflow-hidden bg-card">
          <Tabs defaultValue="fields" className="flex-1 flex flex-col min-h-0">
            <div className="px-4 pt-3 border-b bg-muted/30">
              <TabsList className="bg-muted">
                <TabsTrigger value="fields" className="text-xs gap-1.5">
                  <FileText className="h-3.5 w-3.5" /> Fields
                </TabsTrigger>
                <TabsTrigger value="line_items" className="text-xs gap-1.5">
                  <FileSpreadsheet className="h-3.5 w-3.5" /> Line Items ({lineItems.length})
                </TabsTrigger>
                <TabsTrigger value="issues" className="text-xs gap-1.5">
                  <AlertTriangle className="h-3.5 w-3.5" /> Issues ({issueList.length})
                </TabsTrigger>
                <TabsTrigger value="history" className="text-xs gap-1.5">
                  <History className="h-3.5 w-3.5" /> Audit History
                </TabsTrigger>
              </TabsList>
            </div>

            <TabsContent value="fields" className="flex-1 overflow-y-auto p-4 space-y-4 m-0">
              {isEditing ? (
                <div className="space-y-4">
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label className="text-xs">Invoice Number</Label>
                      <Input
                        value={editedFields.invoice_number || ""}
                        onChange={(e) =>
                          setEditedFields((p) => ({ ...p, invoice_number: e.target.value }))
                        }
                        className="h-8 text-xs font-mono mt-1"
                      />
                    </div>
                    <div>
                      <Label className="text-xs">Supplier Name</Label>
                      <Input
                        value={editedFields.supplier_name || ""}
                        onChange={(e) =>
                          setEditedFields((p) => ({ ...p, supplier_name: e.target.value }))
                        }
                        className="h-8 text-xs mt-1"
                      />
                    </div>
                    <div>
                      <Label className="text-xs">Invoice Date</Label>
                      <Input
                        type="date"
                        value={editedFields.invoice_date || ""}
                        onChange={(e) =>
                          setEditedFields((p) => ({ ...p, invoice_date: e.target.value }))
                        }
                        className="h-8 text-xs font-mono mt-1"
                      />
                    </div>
                    <div>
                      <Label className="text-xs">Due Date</Label>
                      <Input
                        type="date"
                        value={editedFields.payment_due_date || ""}
                        onChange={(e) =>
                          setEditedFields((p) => ({ ...p, payment_due_date: e.target.value }))
                        }
                        className="h-8 text-xs font-mono mt-1"
                      />
                    </div>
                    <div>
                      <Label className="text-xs">Currency</Label>
                      <Input
                        value={editedFields.currency || ""}
                        onChange={(e) =>
                          setEditedFields((p) => ({ ...p, currency: e.target.value }))
                        }
                        className="h-8 text-xs font-mono uppercase mt-1"
                      />
                    </div>
                    <div>
                      <Label className="text-xs">Total Amount</Label>
                      <Input
                        value={editedFields.total_amount || ""}
                        onChange={(e) =>
                          setEditedFields((p) => ({ ...p, total_amount: e.target.value }))
                        }
                        className="h-8 text-xs font-mono mt-1"
                      />
                    </div>
                    <div>
                      <Label className="text-xs">Subtotal (Net)</Label>
                      <Input
                        value={editedFields.subtotal || ""}
                        onChange={(e) =>
                          setEditedFields((p) => ({ ...p, subtotal: e.target.value }))
                        }
                        className="h-8 text-xs font-mono mt-1"
                      />
                    </div>
                    <div>
                      <Label className="text-xs">Tax Amount</Label>
                      <Input
                        value={editedFields.tax_amount || ""}
                        onChange={(e) =>
                          setEditedFields((p) => ({ ...p, tax_amount: e.target.value }))
                        }
                        className="h-8 text-xs font-mono mt-1"
                      />
                    </div>
                  </div>

                  <div className="pt-2">
                    <Label className="text-xs font-medium">Correction Reason (required)</Label>
                    <Textarea
                      placeholder="Explain why fields were corrected..."
                      value={correctionReason}
                      onChange={(e) => setCorrectionReason(e.target.value)}
                      className="text-xs mt-1"
                      rows={2}
                    />
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
                    value={invoice.currency}
                    evidence={sourceEvidence.currency as EvidenceBox}
                    onClick={() => handleFieldClick("currency")}
                  />
                  <FieldRow
                    label="Subtotal (Net)"
                    value={invoice.subtotal ? `${invoice.currency || "EUR"} ${invoice.subtotal}` : "—"}
                    evidence={sourceEvidence.subtotal as EvidenceBox}
                    onClick={() => handleFieldClick("subtotal")}
                  />
                  <FieldRow
                    label="Tax Amount"
                    value={invoice.tax_amount ? `${invoice.currency || "EUR"} ${invoice.tax_amount}` : "—"}
                    evidence={sourceEvidence.tax_amount as EvidenceBox}
                    onClick={() => handleFieldClick("tax_amount")}
                  />
                  <FieldRow
                    label="Total Amount"
                    value={invoice.total_amount ? `${invoice.currency || "EUR"} ${invoice.total_amount}` : "—"}
                    isCorrected={correctedFields.includes("total_amount")}
                    evidence={sourceEvidence.total_amount as EvidenceBox}
                    onClick={() => handleFieldClick("total_amount")}
                  />
                </div>
              )}
            </TabsContent>

            <TabsContent value="line_items" className="flex-1 overflow-y-auto p-0 m-0">
              <Table>
                <TableHeader className="bg-muted/40">
                  <TableRow>
                    <TableHead className="w-12">#</TableHead>
                    <TableHead>Description</TableHead>
                    <TableHead className="text-right">Qty</TableHead>
                    <TableHead className="text-right">Unit Price</TableHead>
                    <TableHead className="text-right">Total</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {lineItems.map((item, idx) => (
                    <TableRow key={item.id} className="text-xs">
                      <TableCell className="font-mono text-muted-foreground">{idx + 1}</TableCell>
                      <TableCell className="font-medium">{item.description}</TableCell>
                      <TableCell className="text-right font-mono">{item.quantity || "1"}</TableCell>
                      <TableCell className="text-right font-mono">
                        {item.unit_price ? <Money value={item.unit_price} currency={invoice.currency} /> : "—"}
                      </TableCell>
                      <TableCell className="text-right font-mono font-medium">
                        <Money value={item.line_total} currency={invoice.currency} />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TabsContent>

            <TabsContent value="issues" className="flex-1 overflow-y-auto p-4 space-y-3 m-0">
              {issueList.length === 0 ? (
                <div className="py-8 text-center text-xs text-muted-foreground">
                  No issues reported for this invoice.
                </div>
              ) : (
                issueList.map((iss) => (
                  <div key={iss.id} className="p-3 rounded-lg border bg-card space-y-1.5 text-xs">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <StatusBadge status={iss.severity} />
                        <span className="font-mono font-medium">{iss.rule_code}</span>
                      </div>
                      <StatusBadge status={iss.resolution_status} />
                    </div>
                    <p className="text-foreground/90">{iss.message}</p>
                    {iss.field_path && (
                      <p className="text-[11px] font-mono text-muted-foreground">
                        Field: {iss.field_path}
                      </p>
                    )}
                  </div>
                ))
              )}
            </TabsContent>

            <TabsContent value="history" className="flex-1 overflow-y-auto p-4 space-y-3 m-0">
              {history.length === 0 ? (
                <div className="py-8 text-center text-xs text-muted-foreground">
                  No modification history.
                </div>
              ) : (
                history.map((evt) => (
                  <div key={evt.id} className="p-3 rounded-lg border bg-card space-y-1 text-xs">
                    <div className="flex items-center justify-between">
                      <span className="font-mono font-semibold uppercase">{evt.action}</span>
                      <DateTime value={evt.created_at} />
                    </div>
                    {evt.actor_id && (
                      <p className="text-muted-foreground font-mono text-[11px]">Actor: {evt.actor_id}</p>
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
              Confirm approval of invoice #{invoice.invoice_number || invoice.id}.
            </DialogDescription>
          </DialogHeader>

          {blockingIssues.length > 0 && (
            <div className="p-3 rounded-md bg-amber-500/15 border border-amber-500/30 text-amber-800 dark:text-amber-300 text-xs space-y-2">
              <div className="font-semibold flex items-center gap-1.5">
                <AlertTriangle className="h-4 w-4" /> Open Blocking Issues ({blockingIssues.length})
              </div>
              <ul className="list-disc pl-4 space-y-1">
                {blockingIssues.map((bi) => (
                  <li key={bi.id}>
                    <strong>{bi.rule_code}:</strong> {bi.message}
                  </li>
                ))}
              </ul>
              <div className="pt-2 flex items-center gap-2">
                <Checkbox
                  id="ack-issues"
                  checked={acknowledgeIssues}
                  onCheckedChange={(c) => setAcknowledgeIssues(!!c)}
                />
                <Label htmlFor="ack-issues" className="text-xs cursor-pointer font-medium">
                  I acknowledge these issues and wish to approve anyway
                </Label>
              </div>
            </div>
          )}

          <div className="space-y-2 pt-2">
            <Label className="text-xs">Approval notes (optional)</Label>
            <Textarea
              placeholder="e.g. Verified with purchasing director"
              value={approveReason}
              onChange={(e) => setApproveReason(e.target.value)}
              className="text-xs"
              rows={2}
            />
          </div>

          <DialogFooter>
            <Button variant="ghost" size="sm" onClick={() => setApproveOpen(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={handleApprove}
              disabled={isApproving || (blockingIssues.length > 0 && !acknowledgeIssues)}
              className="bg-emerald-600 hover:bg-emerald-700 text-white"
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
              State the reason for rejecting invoice #{invoice.invoice_number || invoice.id}.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-2">
            <Label className="text-xs">Rejection Reason (min 3 characters)</Label>
            <Textarea
              placeholder="e.g. Total does not match line item sum, incorrect VAT calculation"
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              className="text-xs"
              rows={3}
            />
          </div>

          <DialogFooter>
            <Button variant="ghost" size="sm" onClick={() => setRejectOpen(false)}>
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
              This invoice was updated by another user or background task while you were viewing it.
              Please reload to view the latest changes before reapplying your edits.
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
  value: string | null | undefined
  isCorrected?: boolean
  evidence?: EvidenceBox
  onClick: () => void
}) {
  return (
    <div
      onClick={onClick}
      className="py-2.5 px-3 flex items-center justify-between hover:bg-muted/40 cursor-pointer rounded transition-colors group"
    >
      <div className="flex flex-col">
        <span className="text-muted-foreground font-medium text-[11px]">{label}</span>
        <div className="flex items-center gap-1.5 mt-0.5">
          <span className="font-medium text-foreground text-xs">{value || "—"}</span>
          {isCorrected && (
            <span className="text-[10px] text-amber-600 bg-amber-500/10 px-1 rounded font-mono font-medium">
              corrected
            </span>
          )}
        </div>
      </div>

      <div className="flex items-center gap-2">
        {evidence && (
          <span className="text-[10px] text-primary/70 group-hover:text-primary font-mono flex items-center gap-0.5">
            P.{evidence.page_number || 1}
          </span>
        )}
      </div>
    </div>
  )
}
