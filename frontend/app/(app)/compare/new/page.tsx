"use client"

import React, { Suspense, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import {
  ArrowRight,
  Check,
  FileSpreadsheet,
  GitCompare,
  Loader2,
  Sparkles,
} from "lucide-react"
import { PageHeader } from "@/components/page-header"
import {
  useDocumentMappingSuggestions,
  useDocumentsList,
} from "@/features/documents/hooks"
import type { DocumentOut } from "@/features/documents/api"
import {
  useCreateComparison,
  useCreateReconciliation,
} from "@/features/comparisons/hooks"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
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
import { cn } from "@/lib/utils"

const READY = new Set([
  "COMPLETED",
  "COMPLETED_WITH_WARNINGS",
  "REQUIRES_REVIEW",
])
const SHEET_KINDS = new Set(["XLSX", "XLS", "CSV"])
const NONE = "__none__"

/** Spreadsheet columns the reconciliation can use; the first two are required. */
const MAPPED_FIELDS: { field: string; label: string; required?: boolean }[] = [
  { field: "invoice_number", label: "Invoice number", required: true },
  { field: "total_amount", label: "Total", required: true },
  { field: "supplier_name", label: "Supplier" },
  { field: "invoice_date", label: "Invoice date" },
  { field: "currency", label: "Currency" },
  { field: "subtotal", label: "Subtotal" },
  { field: "tax_amount", label: "Tax" },
]

function DocumentSelect({
  value,
  onChange,
  docs,
  exclude,
  placeholder,
  label,
}: {
  value: string
  onChange: (id: string) => void
  docs: DocumentOut[]
  exclude?: string
  placeholder: string
  label: string
}) {
  const name = (id: string) =>
    docs.find((d) => d.id === id)?.original_filename ?? placeholder
  return (
    <Select
      value={value || null}
      onValueChange={(v) => onChange(String(v ?? ""))}
    >
      <SelectTrigger className="w-full text-xs" aria-label={label}>
        <SelectValue>
          {(v: string | null) => (
            <span className={cn("truncate", !v && "text-muted-foreground")}>
              {v ? name(v) : placeholder}
            </span>
          )}
        </SelectValue>
      </SelectTrigger>
      <SelectContent>
        {docs.length === 0 ? (
          <div className="p-2 text-center text-xs text-muted-foreground">
            No processed documents yet
          </div>
        ) : (
          docs.map((d) => (
            <SelectItem
              key={d.id}
              value={d.id}
              disabled={d.id === exclude}
              className="text-xs"
            >
              <span className="truncate">{d.original_filename}</span>
              {d.page_count ? (
                <span className="ml-1.5 text-muted-foreground">
                  {d.page_count} {d.page_count === 1 ? "page" : "pages"}
                </span>
              ) : null}
            </SelectItem>
          ))
        )}
      </SelectContent>
    </Select>
  )
}

function Tolerance({
  value,
  onChange,
}: {
  value: string
  onChange: (v: string) => void
}) {
  return (
    <div className="space-y-1">
      <Label className="text-xs" htmlFor="tolerance">
        Allowed difference in amounts
      </Label>
      <Input
        id="tolerance"
        inputMode="decimal"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="0.01"
        className="h-8 font-mono text-xs"
      />
      <p className="text-[11px] text-muted-foreground">
        Amounts that differ by this much or less count as equal (0–100).
      </p>
    </div>
  )
}

function validTolerance(v: string) {
  const n = Number(v.trim() || "0.01")
  return Number.isFinite(n) && n >= 0 && n <= 100
}

function NewComparison() {
  const router = useRouter()
  const search = useSearchParams()
  const [mode, setMode] = useState<"pdf" | "reconciliation">(
    search.get("mode") === "reconciliation" ? "reconciliation" : "pdf"
  )

  const { data: docsData, isLoading: docsLoading } = useDocumentsList({
    limit: 200,
  })
  const ready = (docsData?.items ?? []).filter((d) => READY.has(d.status))
  const invoiceDocs = ready.filter((d) => !SHEET_KINDS.has(d.file_kind))
  const sheetDocs = ready.filter((d) => SHEET_KINDS.has(d.file_kind))

  // PDF ↔ PDF
  const [leftId, setLeftId] = useState(search.get("left") ?? "")
  const [rightId, setRightId] = useState(search.get("right") ?? "")
  const [tolerance, setTolerance] = useState("0.01")
  const [supplierThreshold, setSupplierThreshold] = useState(90)
  const [fuzzyNumbers, setFuzzyNumbers] = useState(true)
  const [defaultCurrency, setDefaultCurrency] = useState<CurrencyCode | null>(
    null
  )

  // PDF ↔ spreadsheet
  const [pdfIds, setPdfIds] = useState<string[]>(
    search.get("pdf") ? [search.get("pdf") as string] : []
  )
  const [sheetId, setSheetId] = useState(search.get("sheet") ?? "")
  const [recTolerance, setRecTolerance] = useState("0.01")
  const [recCurrency, setRecCurrency] = useState<CurrencyCode | null>(null)
  // What the user picked; null = "not in this sheet". Unset fields use the suggestion.
  const [overrides, setOverrides] = useState<Record<string, string | null>>({})
  const [sheetChoice, setSheetChoice] = useState<string[] | null>(null)

  const { data: suggestions, isLoading: mappingLoading } =
    useDocumentMappingSuggestions(sheetId)
  const sheets = suggestions ?? []
  const sheetNames = sheets.map((s) => s.sheet_name ?? "Sheet")
  const selectedSheets = sheetChoice ?? sheetNames
  const usedSheets = sheets.filter((s) =>
    selectedSheets.includes(s.sheet_name ?? "Sheet")
  )
  const headers = [...new Set(usedSheets.flatMap((s) => s.headers))].filter(
    Boolean
  )
  const suggested: Record<string, string> = {}
  for (const s of usedSheets)
    for (const [f, h] of Object.entries(s.suggested_mapping))
      if (!(f in suggested)) suggested[f] = h
  const mapping: Record<string, string> = {}
  for (const { field } of MAPPED_FIELDS) {
    const pick = field in overrides ? overrides[field] : suggested[field]
    if (pick && headers.includes(pick)) mapping[field] = pick
  }
  const missingRequired = MAPPED_FIELDS.filter(
    (f) => f.required && !mapping[f.field]
  )

  const { mutate: createComp, isPending: creatingComp } = useCreateComparison()
  const { mutate: createRec, isPending: creatingRec } =
    useCreateReconciliation()

  const pdfReady =
    !!leftId && !!rightId && leftId !== rightId && validTolerance(tolerance)
  const recReady =
    pdfIds.length > 0 &&
    !!sheetId &&
    selectedSheets.length > 0 &&
    missingRequired.length === 0 &&
    validTolerance(recTolerance)

  const startPdf = () =>
    createComp(
      {
        comparison_type: "PDF_PDF",
        left_document_id: leftId,
        right_document_id: rightId,
        options: {
          amount_tolerance: tolerance.trim() || "0.01",
          supplier_fuzzy_threshold: supplierThreshold,
          fuzzy_invoice_numbers: fuzzyNumbers,
          default_currency: defaultCurrency ?? undefined,
        },
      },
      { onSuccess: (res) => router.push(`/compare/${res.comparison_id}`) }
    )

  const startRec = () =>
    createRec(
      {
        pdf_document_ids: pdfIds,
        spreadsheet_document_id: sheetId,
        column_mapping: mapping,
        sheet_names:
          sheetChoice && sheetChoice.length < sheetNames.length
            ? sheetChoice
            : undefined,
        options: {
          amount_tolerance: recTolerance.trim() || "0.01",
          supplier_fuzzy_threshold: 90,
          fuzzy_invoice_numbers: true,
          default_currency: recCurrency ?? undefined,
        },
      },
      { onSuccess: (res) => router.push(`/compare/${res.comparison_id}`) }
    )

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader
        title="New comparison"
        description="Pick what to check. Invoices are paired by invoice number and supplier, and every amount, date and line is compared."
      />

      <Tabs value={mode} onValueChange={(v) => setMode(v as typeof mode)}>
        <TabsList className="grid h-auto w-full grid-cols-1 gap-1 p-1 sm:grid-cols-2">
          <TabsTrigger value="pdf" className="gap-2 py-2 text-xs">
            <GitCompare className="h-4 w-4" />
            Document ↔ document
          </TabsTrigger>
          <TabsTrigger value="reconciliation" className="gap-2 py-2 text-xs">
            <FileSpreadsheet className="h-4 w-4" />
            Invoices ↔ spreadsheet
          </TabsTrigger>
        </TabsList>

        <TabsContent value="pdf" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base font-semibold">
                Compare two documents
              </CardTitle>
              <CardDescription className="text-xs">
                For example an original and a revised invoice, or a purchase
                batch against the supplier&apos;s copy. You will see which
                invoices match, which differ (and in which fields), and which
                exist on only one side.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <div className="min-w-0 space-y-1.5">
                  <Label className="text-xs">First document</Label>
                  <DocumentSelect
                    label="First document"
                    value={leftId}
                    onChange={setLeftId}
                    docs={invoiceDocs}
                    exclude={rightId}
                    placeholder={docsLoading ? "Loading…" : "Choose a document"}
                  />
                </div>
                <div className="min-w-0 space-y-1.5">
                  <Label className="text-xs">Second document</Label>
                  <DocumentSelect
                    label="Second document"
                    value={rightId}
                    onChange={setRightId}
                    docs={invoiceDocs}
                    exclude={leftId}
                    placeholder={docsLoading ? "Loading…" : "Choose a document"}
                  />
                </div>
              </div>

              <details className="group rounded-md border px-3 py-2">
                <summary className="cursor-pointer text-xs font-medium text-muted-foreground select-none">
                  Matching settings
                </summary>
                <div className="grid grid-cols-1 gap-4 pt-3 pb-1 sm:grid-cols-2">
                  <Tolerance value={tolerance} onChange={setTolerance} />
                  <div className="space-y-1">
                    <Label className="text-xs" htmlFor="supplier-threshold">
                      Supplier name similarity: {supplierThreshold}%
                    </Label>
                    <input
                      id="supplier-threshold"
                      type="range"
                      min={70}
                      max={100}
                      value={supplierThreshold}
                      onChange={(e) =>
                        setSupplierThreshold(Number(e.target.value))
                      }
                      className="w-full accent-primary"
                    />
                    <p className="text-[11px] text-muted-foreground">
                      How alike two supplier names must be to count as the same
                      supplier (&quot;ABC Ltd&quot; vs &quot;A.B.C.
                      Limited&quot;).
                    </p>
                  </div>
                  <div className="space-y-1 sm:col-span-2">
                    <Label className="text-xs">
                      Currency to assume when none is stated
                    </Label>
                    <CurrencySelect
                      value={defaultCurrency}
                      onChange={setDefaultCurrency}
                      placeholder="Don't assume (safer)"
                      allowNull
                    />
                  </div>
                  <div className="flex items-center justify-between gap-4 sm:col-span-2">
                    <div className="space-y-0.5">
                      <Label className="text-xs">
                        Catch scanning errors in invoice numbers
                      </Label>
                      <p className="text-[11px] text-muted-foreground">
                        Numbers that differ by one character (O vs 0) and have
                        the same total are shown for you to confirm. They are
                        never counted as a match on their own.
                      </p>
                    </div>
                    <Switch
                      checked={fuzzyNumbers}
                      onCheckedChange={setFuzzyNumbers}
                    />
                  </div>
                </div>
              </details>
            </CardContent>
            <CardFooter className="flex justify-end border-t pt-4">
              <Button
                onClick={startPdf}
                disabled={creatingComp || !pdfReady}
                className="gap-2"
              >
                {creatingComp ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" /> Starting…
                  </>
                ) : (
                  <>
                    Compare <ArrowRight className="h-4 w-4" />
                  </>
                )}
              </Button>
            </CardFooter>
          </Card>
        </TabsContent>

        <TabsContent value="reconciliation" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base font-semibold">
                Check invoices against a spreadsheet
              </CardTitle>
              <CardDescription className="text-xs">
                Each invoice in the chosen documents is looked up in the
                spreadsheet. You will see rows that match, rows with different
                amounts or dates, invoices missing from the spreadsheet, rows
                with no invoice, and duplicate rows.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <Label className="text-xs">Invoice documents</Label>
                  {invoiceDocs.length > 1 && (
                    <button
                      type="button"
                      className="text-[11px] text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
                      onClick={() =>
                        setPdfIds(
                          pdfIds.length === invoiceDocs.length
                            ? []
                            : invoiceDocs.map((d) => d.id)
                        )
                      }
                    >
                      {pdfIds.length === invoiceDocs.length
                        ? "Clear"
                        : "Select all"}
                    </button>
                  )}
                </div>
                <div className="max-h-48 space-y-0.5 overflow-y-auto rounded-md border p-1">
                  {invoiceDocs.length === 0 ? (
                    <p className="p-2 text-center text-xs text-muted-foreground">
                      {docsLoading
                        ? "Loading…"
                        : "No processed invoice documents yet"}
                    </p>
                  ) : (
                    invoiceDocs.map((d) => {
                      const on = pdfIds.includes(d.id)
                      return (
                        <label
                          key={d.id}
                          className={cn(
                            "flex cursor-pointer items-center gap-2.5 rounded px-2 py-1.5 text-xs hover:bg-muted",
                            on && "bg-primary/5"
                          )}
                        >
                          <Checkbox
                            checked={on}
                            onCheckedChange={(v) =>
                              setPdfIds((prev) =>
                                v
                                  ? [...prev, d.id]
                                  : prev.filter((x) => x !== d.id)
                              )
                            }
                          />
                          <span className="min-w-0 flex-1 truncate">
                            {d.original_filename}
                          </span>
                          {d.page_count ? (
                            <span className="shrink-0 text-[11px] text-muted-foreground">
                              {d.page_count}p
                            </span>
                          ) : null}
                        </label>
                      )
                    })
                  )}
                </div>
                <p className="text-[11px] text-muted-foreground">
                  {pdfIds.length} selected
                </p>
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs">
                  Spreadsheet (XLSX, XLS or CSV)
                </Label>
                <DocumentSelect
                  label="Spreadsheet"
                  value={sheetId}
                  onChange={(id) => {
                    setSheetId(id)
                    setOverrides({})
                    setSheetChoice(null)
                  }}
                  docs={sheetDocs}
                  placeholder={
                    docsLoading ? "Loading…" : "Choose a spreadsheet"
                  }
                />
              </div>

              {sheetId && (
                <div className="space-y-3 rounded-md border p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h4 className="text-xs font-semibold">
                      Which column holds what?
                    </h4>
                    <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
                      <Sparkles className="h-3 w-3" /> Filled in from the column
                      names. Change anything that is wrong.
                    </span>
                  </div>

                  {sheets.length > 1 && (
                    <div className="flex flex-wrap gap-x-4 gap-y-1.5">
                      {sheetNames.map((name) => (
                        <label
                          key={name}
                          className="flex cursor-pointer items-center gap-1.5 text-xs"
                        >
                          <Checkbox
                            checked={selectedSheets.includes(name)}
                            onCheckedChange={(v) =>
                              setSheetChoice(
                                v
                                  ? [...selectedSheets, name]
                                  : selectedSheets.filter((x) => x !== name)
                              )
                            }
                          />
                          {name}
                        </label>
                      ))}
                    </div>
                  )}

                  {mappingLoading ? (
                    <div className="flex items-center gap-2 py-2 text-xs text-muted-foreground">
                      <Loader2 className="h-3.5 w-3.5 animate-spin" /> Reading
                      columns…
                    </div>
                  ) : headers.length === 0 ? (
                    <p className="text-xs text-muted-foreground">
                      No columns found in the selected sheets.
                    </p>
                  ) : (
                    <div className="grid grid-cols-1 gap-x-4 gap-y-2.5 sm:grid-cols-2">
                      {MAPPED_FIELDS.map(({ field, label, required }) => {
                        const value = mapping[field] ?? NONE
                        return (
                          <div key={field} className="min-w-0 space-y-1">
                            <Label className="text-[11px] text-muted-foreground">
                              {label}
                              {required && " *"}
                            </Label>
                            <Select
                              value={value}
                              onValueChange={(v) =>
                                setOverrides((o) => ({
                                  ...o,
                                  [field]: v === NONE ? null : String(v),
                                }))
                              }
                            >
                              <SelectTrigger
                                className={cn(
                                  "h-8 w-full text-xs",
                                  required &&
                                    value === NONE &&
                                    "border-destructive/60"
                                )}
                                aria-label={`Column for ${label}`}
                              >
                                <SelectValue>
                                  {(v: string) =>
                                    v === NONE ? (
                                      <span className="text-muted-foreground">
                                        {required
                                          ? "Choose a column"
                                          : "Not in this sheet"}
                                      </span>
                                    ) : (
                                      <span className="inline-flex min-w-0 items-center gap-1.5 truncate">
                                        {suggested[field] === v &&
                                          !(field in overrides) && (
                                            <Check className="h-3 w-3 shrink-0 text-emerald-600" />
                                          )}
                                        <span className="truncate">{v}</span>
                                      </span>
                                    )
                                  }
                                </SelectValue>
                              </SelectTrigger>
                              <SelectContent>
                                {!required && (
                                  <SelectItem value={NONE} className="text-xs">
                                    Not in this sheet
                                  </SelectItem>
                                )}
                                {headers.map((h) => (
                                  <SelectItem
                                    key={h}
                                    value={h}
                                    className="text-xs"
                                  >
                                    {h}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </div>
                        )
                      })}
                    </div>
                  )}
                  {missingRequired.length > 0 && !mappingLoading && (
                    <p className="text-[11px] text-destructive">
                      Choose the column for{" "}
                      {missingRequired
                        .map((f) => f.label.toLowerCase())
                        .join(" and ")}
                      .
                    </p>
                  )}
                </div>
              )}

              <details className="rounded-md border px-3 py-2">
                <summary className="cursor-pointer text-xs font-medium text-muted-foreground select-none">
                  Matching settings
                </summary>
                <div className="grid grid-cols-1 gap-4 pt-3 pb-1 sm:grid-cols-2">
                  <Tolerance value={recTolerance} onChange={setRecTolerance} />
                  <div className="space-y-1">
                    <Label className="text-xs">
                      Currency to assume when none is stated
                    </Label>
                    <CurrencySelect
                      value={recCurrency}
                      onChange={setRecCurrency}
                      placeholder="Don't assume (safer)"
                      allowNull
                    />
                    <p className="text-[11px] text-muted-foreground">
                      Useful when the spreadsheet has no currency column.
                    </p>
                  </div>
                </div>
              </details>
            </CardContent>
            <CardFooter className="flex justify-end border-t pt-4">
              <Button
                onClick={startRec}
                disabled={creatingRec || !recReady}
                className="gap-2"
              >
                {creatingRec ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" /> Starting…
                  </>
                ) : (
                  <>
                    Check invoices <ArrowRight className="h-4 w-4" />
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

export default function NewComparisonPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto h-96 max-w-3xl animate-pulse rounded-lg bg-muted" />
      }
    >
      <NewComparison />
    </Suspense>
  )
}
