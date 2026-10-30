"use client"

import React, { useState } from "react"
import { useRouter } from "next/navigation"
import { PageHeader } from "@/components/page-header"
import {
  useDocumentsList,
  useDocumentMappingSuggestions,
} from "@/features/documents/hooks"
import {
  useCreateComparison,
  useCreateReconciliation,
} from "@/features/comparisons/hooks"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  CardFooter,
} from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { CurrencySelect } from "@/components/currency-select"
import type { CurrencyCode } from "@/lib/api/types"
import { GitCompare, FileSpreadsheet, ArrowRight, Loader2 } from "lucide-react"
import { toast } from "sonner"

export default function NewComparisonPage() {
  const router = useRouter()
  const [mode, setMode] = useState<"pdf" | "reconciliation">("pdf")

  // Documents list
  const { data: docsData } = useDocumentsList({ limit: 100 })
  const documents = docsData?.items ?? []

  // PDF ↔ PDF State
  const [leftDocId, setLeftDocId] = useState("")
  const [rightDocId, setRightDocId] = useState("")
  const [amountTolerance, setAmountTolerance] = useState("0.01")
  const [supplierFuzzyThreshold, setSupplierFuzzyThreshold] = useState("90")
  const [fuzzyInvoiceNumbers, setFuzzyInvoiceNumbers] = useState(true)
  const [defaultCurrency, setDefaultCurrency] = useState<CurrencyCode | null>(
    null
  )

  // Reconciliation State
  const [reconcilePdfIds, setReconcilePdfIds] = useState<string[]>([])
  const [spreadsheetId, setSpreadsheetId] = useState("")
  const [columnMapping, setColumnMapping] = useState<Record<string, string>>({
    invoice_number: "Invoice No",
    total_amount: "Total Amount",
    supplier_name: "Supplier",
    invoice_date: "Date",
    currency: "Currency",
    tax_amount: "Tax",
  })

  const { data: suggestions } = useDocumentMappingSuggestions(spreadsheetId)
  const suggestedMapping = suggestions?.[0]?.suggested_mapping || {}
  const effectiveMapping = { ...columnMapping, ...suggestedMapping }

  const { mutate: createComp, isPending: isCreatingComp } =
    useCreateComparison()
  const { mutate: createRec, isPending: isCreatingRec } =
    useCreateReconciliation()

  const readyStatuses = [
    "COMPLETED",
    "COMPLETED_WITH_WARNINGS",
    "REQUIRES_REVIEW",
  ]
  const pdfDocs = documents.filter(
    (d) => d.file_kind === "PDF" && readyStatuses.includes(d.status)
  )
  const spreadsheetDocs = documents.filter(
    (d) =>
      ["XLSX", "XLS", "CSV"].includes(d.file_kind) &&
      readyStatuses.includes(d.status)
  )

  const handleStartPdfComparison = () => {
    if (!leftDocId || !rightDocId) {
      toast.error("Please select both documents for comparison.")
      return
    }

    if (leftDocId === rightDocId) {
      toast.error("Left and right documents must differ.")
      return
    }

    const numTolerance = parseFloat(amountTolerance)
    if (isNaN(numTolerance) || numTolerance < 0 || numTolerance > 100) {
      toast.error("Amount tolerance must be a number between 0 and 100.")
      return
    }

    const numThreshold = parseInt(supplierFuzzyThreshold, 10)
    if (isNaN(numThreshold) || numThreshold < 70 || numThreshold > 100) {
      toast.error(
        "Supplier match threshold must be an integer between 70 and 100."
      )
      return
    }

    createComp(
      {
        comparison_type: "PDF_PDF",
        left_document_id: leftDocId,
        right_document_id: rightDocId,
        options: {
          amount_tolerance: amountTolerance.trim() || "0.01",
          supplier_fuzzy_threshold: numThreshold,
          fuzzy_invoice_numbers: fuzzyInvoiceNumbers,
          default_currency: defaultCurrency || undefined,
        },
      },
      {
        onSuccess: (data: any) => {
          const compId = data?.comparison_id || data?.id
          if (compId) {
            router.push(`/compare/${compId}`)
          } else {
            router.push("/compare")
          }
        },
      }
    )
  }

  const handleStartReconciliation = () => {
    if (reconcilePdfIds.length === 0 || !spreadsheetId) {
      toast.error(
        "Please select at least one PDF and one spreadsheet document."
      )
      return
    }

    createRec(
      {
        pdf_document_ids: reconcilePdfIds,
        spreadsheet_document_id: spreadsheetId,
        column_mapping: effectiveMapping,
      },
      {
        onSuccess: (data: any) => {
          const compId = data?.comparison_id || data?.id
          if (compId) {
            router.push(`/compare/${compId}`)
          } else {
            router.push("/compare")
          }
        },
      }
    )
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader
        title="New Comparison / Reconciliation"
        description="Configure automated matching between documents or against a ledger register."
      />

      <Tabs value={mode} onValueChange={(v) => setMode(v as any)}>
        <TabsList className="grid h-auto w-full grid-cols-1 gap-1 p-1 sm:grid-cols-2">
          <TabsTrigger value="pdf" className="gap-2 py-2 text-xs">
            <GitCompare className="h-4 w-4" />
            PDF ↔ PDF Comparison
          </TabsTrigger>
          <TabsTrigger value="reconciliation" className="gap-2 py-2 text-xs">
            <FileSpreadsheet className="h-4 w-4" />
            PDF ↔ Spreadsheet Reconciliation
          </TabsTrigger>
        </TabsList>

        {/* PDF ↔ PDF Wizard */}
        <TabsContent value="pdf" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base font-semibold">
                Compare Two Documents
              </CardTitle>
              <CardDescription className="text-xs">
                Select an original invoice and a revised version to find
                differences in amounts, dates, and supplier information.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label className="text-xs">Left Document (Baseline)</Label>
                  <Select
                    value={leftDocId}
                    onValueChange={(val) => setLeftDocId(val || "")}
                  >
                    <SelectTrigger className="text-xs">
                      <SelectValue placeholder="Select PDF document..." />
                    </SelectTrigger>
                    <SelectContent>
                      {pdfDocs.length === 0 ? (
                        <div className="p-2 text-center text-xs text-muted-foreground">
                          No processed PDF documents available
                        </div>
                      ) : (
                        pdfDocs.map((d) => (
                          <SelectItem
                            key={d.id}
                            value={d.id}
                            disabled={d.id === rightDocId}
                            className="text-xs"
                          >
                            {d.original_filename}
                            {d.id === rightDocId ? " (Selected on right)" : ""}
                          </SelectItem>
                        ))
                      )}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label className="text-xs">Right Document (Comparison)</Label>
                  <Select
                    value={rightDocId}
                    onValueChange={(val) => setRightDocId(val || "")}
                  >
                    <SelectTrigger className="text-xs">
                      <SelectValue placeholder="Select PDF document..." />
                    </SelectTrigger>
                    <SelectContent>
                      {pdfDocs.length === 0 ? (
                        <div className="p-2 text-center text-xs text-muted-foreground">
                          No processed PDF documents available
                        </div>
                      ) : (
                        pdfDocs.map((d) => (
                          <SelectItem
                            key={d.id}
                            value={d.id}
                            disabled={d.id === leftDocId}
                            className="text-xs"
                          >
                            {d.original_filename}
                            {d.id === leftDocId ? " (Selected on left)" : ""}
                          </SelectItem>
                        ))
                      )}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="space-y-3 border-t pt-4">
                <h4 className="text-xs font-semibold text-muted-foreground uppercase">
                  Matching Parameters
                </h4>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <div className="space-y-1">
                    <Label className="text-xs">
                      Amount Tolerance (Currency, 0–100)
                    </Label>
                    <Input
                      value={amountTolerance}
                      onChange={(e) => setAmountTolerance(e.target.value)}
                      placeholder="0.01"
                      className="h-8 font-mono text-xs"
                    />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">
                      Supplier Match Threshold (70–100)
                    </Label>
                    <Input
                      type="number"
                      min={70}
                      max={100}
                      value={supplierFuzzyThreshold}
                      onChange={(e) =>
                        setSupplierFuzzyThreshold(e.target.value)
                      }
                      className="h-8 font-mono text-xs"
                    />
                  </div>
                </div>

                <div className="space-y-1">
                  <Label className="text-xs">
                    Assume this currency when a record states none (optional)
                  </Label>
                  <CurrencySelect
                    value={defaultCurrency}
                    onChange={setDefaultCurrency}
                    placeholder="None (do not assume)"
                    allowNull
                  />
                </div>

                <div className="flex items-center justify-between pt-1">
                  <div className="space-y-0.5">
                    <Label className="text-xs">
                      Fuzzy Invoice Number Matching
                    </Label>
                    <p className="text-[11px] text-muted-foreground">
                      Ignore minor prefixes, zeroes, or punctuation in invoice
                      codes
                    </p>
                  </div>
                  <Switch
                    checked={fuzzyInvoiceNumbers}
                    onCheckedChange={setFuzzyInvoiceNumbers}
                  />
                </div>
              </div>
            </CardContent>
            <CardFooter className="flex justify-end border-t pt-4">
              <Button
                onClick={handleStartPdfComparison}
                disabled={isCreatingComp || !leftDocId || !rightDocId}
                className="gap-2"
              >
                {isCreatingComp ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" /> Starting...
                  </>
                ) : (
                  <>
                    Run Comparison <ArrowRight className="h-4 w-4" />
                  </>
                )}
              </Button>
            </CardFooter>
          </Card>
        </TabsContent>

        {/* PDF ↔ Spreadsheet Reconciliation Wizard */}
        <TabsContent value="reconciliation" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base font-semibold">
                Reconcile Invoices with Spreadsheet
              </CardTitle>
              <CardDescription className="text-xs">
                Match one or multiple extracted invoice PDFs against an
                accounting register or ledger spreadsheet.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label className="text-xs">
                  Select Invoices (PDF Documents)
                </Label>
                <div className="max-h-40 space-y-1 overflow-y-auto rounded-md border bg-muted/20 p-2">
                  {pdfDocs.map((d) => {
                    const isSelected = reconcilePdfIds.includes(d.id)
                    return (
                      <div
                        key={d.id}
                        onClick={() => {
                          setReconcilePdfIds((prev) =>
                            isSelected
                              ? prev.filter((id) => id !== d.id)
                              : [...prev, d.id]
                          )
                        }}
                        className={`flex cursor-pointer items-center justify-between rounded p-2 text-xs transition-colors ${
                          isSelected
                            ? "border border-primary/30 bg-primary/10"
                            : "hover:bg-muted"
                        }`}
                      >
                        <span className="truncate font-medium">
                          {d.original_filename}
                        </span>
                        <span className="font-mono text-[10px] text-muted-foreground">
                          {isSelected ? "Selected" : "Click to select"}
                        </span>
                      </div>
                    )
                  })}
                </div>
                <p className="text-[11px] text-muted-foreground">
                  {reconcilePdfIds.length} invoice(s) selected
                </p>
              </div>

              <div className="space-y-2">
                <Label className="text-xs">
                  Select Ledger (Spreadsheet / CSV)
                </Label>
                <Select
                  value={spreadsheetId}
                  onValueChange={(val) => setSpreadsheetId(val || "")}
                >
                  <SelectTrigger className="text-xs">
                    <SelectValue placeholder="Select spreadsheet..." />
                  </SelectTrigger>
                  <SelectContent>
                    {spreadsheetDocs.map((d) => (
                      <SelectItem key={d.id} value={d.id} className="text-xs">
                        {d.original_filename}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Column Mapping Section */}
              {spreadsheetId && (
                <div className="space-y-3 border-t pt-4">
                  <div className="flex items-center justify-between">
                    <h4 className="text-xs font-semibold text-muted-foreground uppercase">
                      Column Mapping (Required Fields Marked *)
                    </h4>
                  </div>

                  <div className="grid grid-cols-1 gap-3 text-xs sm:grid-cols-2">
                    <div>
                      <Label className="text-xs">Invoice Number *</Label>
                      <Input
                        value={effectiveMapping.invoice_number || ""}
                        onChange={(e) =>
                          setColumnMapping((p) => ({
                            ...p,
                            invoice_number: e.target.value,
                          }))
                        }
                        className="mt-1 h-8 font-mono text-xs"
                      />
                    </div>
                    <div>
                      <Label className="text-xs">Total Amount *</Label>
                      <Input
                        value={effectiveMapping.total_amount || ""}
                        onChange={(e) =>
                          setColumnMapping((p) => ({
                            ...p,
                            total_amount: e.target.value,
                          }))
                        }
                        className="mt-1 h-8 font-mono text-xs"
                      />
                    </div>
                    <div>
                      <Label className="text-xs">Supplier Name</Label>
                      <Input
                        value={effectiveMapping.supplier_name || ""}
                        onChange={(e) =>
                          setColumnMapping((p) => ({
                            ...p,
                            supplier_name: e.target.value,
                          }))
                        }
                        className="mt-1 h-8 font-mono text-xs"
                      />
                    </div>
                    <div>
                      <Label className="text-xs">Invoice Date</Label>
                      <Input
                        value={effectiveMapping.invoice_date || ""}
                        onChange={(e) =>
                          setColumnMapping((p) => ({
                            ...p,
                            invoice_date: e.target.value,
                          }))
                        }
                        className="mt-1 h-8 font-mono text-xs"
                      />
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
            <CardFooter className="flex justify-end border-t pt-4">
              <Button
                onClick={handleStartReconciliation}
                disabled={
                  isCreatingRec ||
                  reconcilePdfIds.length === 0 ||
                  !spreadsheetId
                }
                className="gap-2"
              >
                {isCreatingRec ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" /> Reconciling...
                  </>
                ) : (
                  <>
                    Start Reconciliation <ArrowRight className="h-4 w-4" />
                  </>
                )}
              </Button>
            </CardFooter>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
