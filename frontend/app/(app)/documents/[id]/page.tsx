"use client"

import { jobTypeLabel } from "@/lib/labels"
import React, { use, useState } from "react"
import { useQueryState, parseAsString } from "nuqs"
import {
  useDocument,
  useDocumentPages,
  useDocumentText,
  useDocumentTables,
  useDocumentTableRows,
  useDocumentInvoices,
  useDocumentValidations,
  useDocumentJobs,
  useReprocessDocument,
  useDeleteDocument,
} from "@/features/documents/hooks"
import { documentsApi } from "@/features/documents/api"
import { useCurrentUser } from "@/features/auth/hooks"
import { canAdmin, hasPermission } from "@/lib/permissions"
import { StatusBadge } from "@/components/status-badge"
import { DateTime } from "@/components/date-time"
import { Bytes } from "@/components/bytes"
import { Money } from "@/components/money"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/error-state"
import { ConfirmDialog } from "@/components/confirm-dialog"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Download,
  RotateCw,
  Trash2,
  FileText,
  Layers,
  Table as TableIcon,
  AlertCircle,
  Briefcase,
  ExternalLink,
  ChevronLeft,
  ChevronRight,
  Eye,
  GitCompare,
} from "lucide-react"
import Link from "next/link"
import { useRouter } from "next/navigation"

export default function DocumentDetailPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = use(params)
  const router = useRouter()
  const { data: user } = useCurrentUser()
  const [tab, setTab] = useQueryState(
    "tab",
    parseAsString.withDefault("invoices")
  )
  const [deleteOpen, setDeleteOpen] = useState(false)

  const { data: doc, isLoading, isError, error, refetch } = useDocument(id)
  const { mutate: reprocess, isPending: isReprocessing } =
    useReprocessDocument()
  const { mutate: deleteDoc, isPending: isDeleting } = useDeleteDocument()

  const handleDownload = async () => {
    try {
      const blob = await documentsApi.download(id)
      if (blob instanceof Blob) {
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement("a")
        a.href = url
        a.download = doc?.original_filename || `document-${id}`
        document.body.appendChild(a)
        a.click()
        window.URL.revokeObjectURL(url)
        a.remove()
      }
    } catch (err: any) {
      alert("Download failed: " + (err.message || String(err)))
    }
  }

  const handleDelete = () => {
    deleteDoc(id, {
      onSuccess: () => router.push("/documents"),
    })
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="h-20 animate-pulse rounded-lg bg-muted" />
        <div className="h-96 animate-pulse rounded-lg bg-muted" />
      </div>
    )
  }

  if (isError || !doc) {
    return (
      <ErrorState
        message={(error as any)?.message || "Document not found"}
        requestId={(error as any)?.requestId}
        onRetry={() => refetch()}
      />
    )
  }

  return (
    <div className="space-y-6">
      {/* Top Header Card */}
      <div className="flex min-w-0 flex-col justify-between gap-4 rounded-xl border bg-card p-4 text-card-foreground shadow-sm sm:p-6 md:flex-row md:items-center">
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <h1
              className="line-clamp-2 text-lg font-bold tracking-tight break-all sm:text-xl"
              title={doc.original_filename}
            >
              {doc.original_filename}
            </h1>
            <div className="flex shrink-0 items-center gap-1.5">
              <StatusBadge status={doc.status} />
              <StatusBadge status={doc.validation_outcome} />
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3 font-mono text-xs text-muted-foreground">
            <span>Kind: {doc.file_kind}</span>
            <span>•</span>
            <span>Type: {doc.document_type}</span>
            <span>•</span>
            <Bytes bytes={doc.file_size_bytes} />
            <span>•</span>
            <DateTime value={doc.created_at} />
          </div>
        </div>

        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleDownload}
            className="gap-1.5 text-xs"
          >
            <Download className="h-3.5 w-3.5" />
            Download
          </Button>

          {hasPermission(user?.role, "COMPARE_RUN") &&
            [
              "COMPLETED",
              "COMPLETED_WITH_WARNINGS",
              "REQUIRES_REVIEW",
            ].includes(doc.status) && (
              <Link
                href={
                  ["XLSX", "XLS", "CSV"].includes(doc.file_kind)
                    ? `/compare/new?mode=reconciliation&sheet=${doc.id}`
                    : `/compare/new?left=${doc.id}&pdf=${doc.id}`
                }
              >
                <Button variant="outline" size="sm" className="gap-1.5 text-xs">
                  <GitCompare className="h-3.5 w-3.5" />
                  Compare
                </Button>
              </Link>
            )}

          {hasPermission(user?.role, "JOB_MANAGE") && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => reprocess(id)}
              disabled={isReprocessing}
              className="gap-1.5 text-xs"
            >
              <RotateCw
                className={`h-3.5 w-3.5 ${isReprocessing ? "animate-spin" : ""}`}
              />
              Reprocess
            </Button>
          )}

          {canAdmin(user?.role) && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setDeleteOpen(true)}
              className="gap-1.5 text-xs text-destructive hover:bg-destructive/10"
            >
              <Trash2 className="h-3.5 w-3.5" />
              Delete
            </Button>
          )}
        </div>
      </div>

      {/* Main Tabs */}
      <Tabs
        value={tab}
        onValueChange={(val) => setTab(val)}
        className="space-y-4"
      >
        <TabsList className="h-auto flex-wrap gap-1 bg-muted/60 p-1">
          <TabsTrigger
            value="invoices"
            className="gap-1.5 px-2.5 py-1.5 text-xs"
          >
            <FileText className="h-3.5 w-3.5" />
            Invoices
          </TabsTrigger>
          <TabsTrigger value="pages" className="gap-1.5 px-2.5 py-1.5 text-xs">
            <Layers className="h-3.5 w-3.5" />
            Pages
          </TabsTrigger>
          <TabsTrigger value="text" className="gap-1.5 px-2.5 py-1.5 text-xs">
            <FileText className="h-3.5 w-3.5" />
            Extracted Text
          </TabsTrigger>
          <TabsTrigger value="tables" className="gap-1.5 px-2.5 py-1.5 text-xs">
            <TableIcon className="h-3.5 w-3.5" />
            Tables & Sheets
          </TabsTrigger>
          <TabsTrigger value="issues" className="gap-1.5 px-2.5 py-1.5 text-xs">
            <AlertCircle className="h-3.5 w-3.5" />
            Issues
          </TabsTrigger>
          <TabsTrigger value="jobs" className="gap-1.5 px-2.5 py-1.5 text-xs">
            <Briefcase className="h-3.5 w-3.5" />
            Jobs
          </TabsTrigger>
        </TabsList>

        <TabsContent value="invoices" className="focus:outline-none">
          <InvoicesTab documentId={id} />
        </TabsContent>

        <TabsContent value="pages" className="focus:outline-none">
          <PagesTab documentId={id} />
        </TabsContent>

        <TabsContent value="text" className="focus:outline-none">
          <TextTab documentId={id} />
        </TabsContent>

        <TabsContent value="tables" className="focus:outline-none">
          <TablesTab documentId={id} />
        </TabsContent>

        <TabsContent value="issues" className="focus:outline-none">
          <IssuesTab documentId={id} />
        </TabsContent>

        <TabsContent value="jobs" className="focus:outline-none">
          <JobsTab documentId={id} />
        </TabsContent>
      </Tabs>

      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Delete Document"
        description="Are you sure you want to permanently delete this document and all associated data?"
        confirmText="Delete"
        isDestructive
        isLoading={isDeleting}
        onConfirm={handleDelete}
      />
    </div>
  )
}

function InvoicesTab({ documentId }: { documentId: string }) {
  const { data: invoices, isLoading } = useDocumentInvoices(documentId)

  if (isLoading)
    return <div className="h-48 animate-pulse rounded-lg bg-muted" />
  if (!invoices || invoices.length === 0) {
    return (
      <EmptyState
        title="No invoices found"
        description="No invoices extracted from this document."
      />
    )
  }

  return (
    <div className="space-y-3">
      {/* Mobile / Tablet Container Cards */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:hidden">
        {invoices.map((inv) => (
          <div
            key={inv.id}
            className="flex flex-col justify-between space-y-3 rounded-lg border bg-card p-4 text-xs transition-colors hover:border-primary/40"
          >
            <div className="space-y-2">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <span className="font-mono text-xs font-semibold text-foreground">
                    {inv.invoice_number || "—"}
                  </span>
                  <p className="mt-0.5 font-medium text-muted-foreground">
                    {inv.supplier_name || "—"}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  <StatusBadge status={inv.review_status} />
                  <span className="rounded bg-muted px-1 py-0.5 font-mono text-[10px] text-muted-foreground">
                    v{inv.version}
                  </span>
                </div>
              </div>

              <div className="flex items-center justify-between border-t border-border/50 pt-1 text-[11px]">
                <span className="text-muted-foreground">
                  {inv.invoice_date || "—"}
                </span>
                <span className="font-mono font-semibold text-foreground">
                  <Money
                    value={inv.total_amount}
                    currency={inv.currency}
                    raw={inv.currency_raw}
                  />
                </span>
              </div>
            </div>

            <Link href={`/invoices/${inv.id}`}>
              <Button
                size="sm"
                variant="outline"
                className="h-7 w-full gap-1.5 text-xs"
              >
                <Eye className="h-3 w-3" />
                Review Workspace
              </Button>
            </Link>
          </div>
        ))}
      </div>

      {/* Desktop Table View */}
      <div className="hidden overflow-hidden rounded-lg border bg-card lg:block">
        <Table>
          <TableHeader className="bg-muted/40">
            <TableRow>
              <TableHead>Invoice #</TableHead>
              <TableHead>Supplier</TableHead>
              <TableHead>Date</TableHead>
              <TableHead>Total Amount</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Version</TableHead>
              <TableHead className="text-right">Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {invoices.map((inv) => (
              <TableRow key={inv.id} className="hover:bg-muted/30">
                <TableCell className="font-mono font-medium">
                  {inv.invoice_number || "—"}
                </TableCell>
                <TableCell>{inv.supplier_name || "—"}</TableCell>
                <TableCell>{inv.invoice_date || "—"}</TableCell>
                <TableCell>
                  <Money
                    value={inv.total_amount}
                    currency={inv.currency}
                    raw={inv.currency_raw}
                  />
                </TableCell>
                <TableCell>
                  <StatusBadge status={inv.review_status} />
                </TableCell>
                <TableCell className="font-mono text-xs">
                  v{inv.version}
                </TableCell>
                <TableCell className="text-right">
                  <Link href={`/invoices/${inv.id}`}>
                    <Button
                      size="sm"
                      variant="outline"
                      className="gap-1.5 text-xs"
                    >
                      <Eye className="h-3.5 w-3.5" />
                      Review Workspace
                    </Button>
                  </Link>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}

const PAGES_PER_SCREEN = 48

function PagesTab({ documentId }: { documentId: string }) {
  const [offset, setOffset] = React.useState(0)
  const { data, isLoading, isPlaceholderData } = useDocumentPages(documentId, {
    limit: PAGES_PER_SCREEN,
    offset,
  })
  const pages = data?.items ?? []
  const total = data?.total ?? 0

  if (isLoading)
    return <div className="h-64 animate-pulse rounded-lg bg-muted" />
  if (pages.length === 0)
    return (
      <EmptyState title="No pages found" description="No pages parsed yet." />
    )

  const from = offset + 1
  const to = Math.min(offset + pages.length, total)
  return (
    <div className="space-y-4">
      {total > PAGES_PER_SCREEN && (
        <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
          <span>
            Pages {from}–{to} of {total}
          </span>
          <div className="flex gap-1.5">
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-xs"
              disabled={offset === 0 || isPlaceholderData}
              onClick={() => setOffset(Math.max(0, offset - PAGES_PER_SCREEN))}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-xs"
              disabled={to >= total || isPlaceholderData}
              onClick={() => setOffset(offset + PAGES_PER_SCREEN)}
            >
              Next
            </Button>
          </div>
        </div>
      )}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
        {pages.map((p) => {
          const imageUrl = documentsApi.getPageImageUrl(
            documentId,
            p.page_number,
            300
          )
          return (
            <div
              key={p.id}
              className="group flex flex-col overflow-hidden rounded-lg border bg-card"
            >
              <div className="relative flex aspect-[3/4] items-center justify-center overflow-hidden bg-muted/40">
                <FileText className="pointer-events-none absolute h-8 w-8 text-muted-foreground/30" />
                <img
                  src={imageUrl}
                  alt={`Page ${p.page_number}`}
                  loading="lazy"
                  className="relative z-10 h-full w-full object-contain transition-transform duration-200 group-hover:scale-105"
                  onError={(e) => {
                    // Fallback placeholder if image endpoint fails
                    ;(e.target as HTMLElement).style.display = "none"
                  }}
                />
              </div>
              <div className="flex items-center justify-between border-t p-2.5 text-xs">
                <span className="font-medium">Page {p.page_number}</span>
                <span className="font-mono text-[10px] text-muted-foreground">
                  {p.character_count} chars
                </span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function TextTab({ documentId }: { documentId: string }) {
  const [pageFrom, setPageFrom] = useState(1)
  const { data: textData, isLoading } = useDocumentText(
    documentId,
    pageFrom,
    pageFrom + 4
  )

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">
          Pages {pageFrom}–{pageFrom + 4}
        </span>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setPageFrom((p) => Math.max(1, p - 5))}
            disabled={pageFrom <= 1}
            className="h-8 gap-1 text-xs"
          >
            <ChevronLeft className="h-3.5 w-3.5" /> Previous
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setPageFrom((p) => p + 5)}
            className="h-8 gap-1 text-xs"
          >
            Next <ChevronRight className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="h-64 animate-pulse rounded-lg bg-muted" />
      ) : !textData || textData.length === 0 ? (
        <EmptyState
          title="No text found"
          description="No text extracted for the requested page range."
        />
      ) : (
        <div className="space-y-4">
          {textData.map((pt) => (
            <Card key={pt.page_number}>
              <CardHeader className="border-b bg-muted/30 px-4 py-2.5">
                <CardTitle className="font-mono text-xs font-medium">
                  Page {pt.page_number}
                </CardTitle>
              </CardHeader>
              <CardContent className="p-4">
                <pre className="overflow-x-auto font-mono text-xs leading-relaxed break-words whitespace-pre-wrap text-foreground/90">
                  {pt.text || (
                    <span className="text-muted-foreground italic">
                      (Blank page)
                    </span>
                  )}
                </pre>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

function TablesTab({ documentId }: { documentId: string }) {
  const { data, isLoading } = useDocumentTables(documentId)
  const tables = data?.items ?? []
  const [selectedTableId, setSelectedTableId] = useState<string | null>(null)

  const activeTableId = selectedTableId || tables[0]?.id
  const { data: rowsData, isLoading: rowsLoading } = useDocumentTableRows(
    documentId,
    activeTableId || "",
    { limit: 50 }
  )

  if (isLoading)
    return <div className="h-48 animate-pulse rounded-lg bg-muted" />
  if (tables.length === 0)
    return (
      <EmptyState
        title="No tables found"
        description="No tabular structures detected."
      />
    )

  const activeTable = tables.find((t) => t.id === activeTableId) || tables[0]

  return (
    <div className="space-y-4">
      {/* Table selector */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1">
        {tables.map((t) => (
          <Button
            key={t.id}
            variant={t.id === activeTableId ? "default" : "outline"}
            size="sm"
            onClick={() => setSelectedTableId(t.id)}
            className="h-8 shrink-0 font-mono text-xs"
          >
            {t.sheet_name || `Table ${t.table_index + 1}`} (page{" "}
            {t.page_number || "—"})
          </Button>
        ))}
      </div>

      {/* Row view */}
      {rowsLoading ? (
        <div className="space-y-2 rounded-lg border bg-card p-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-8 animate-pulse rounded bg-muted" />
          ))}
        </div>
      ) : (
        <div className="space-y-3">
          {/* Mobile / Tablet Container Cards */}
          <div className="space-y-2 lg:hidden">
            {rowsData?.items?.map((row) => (
              <div
                key={row.row_number}
                className="space-y-1.5 rounded-lg border bg-card p-3 text-xs"
              >
                <div className="border-b pb-1 font-mono text-[11px] font-semibold text-muted-foreground">
                  Row #{row.row_number}
                </div>
                <div className="space-y-1">
                  {activeTable?.header_json?.map((col: any, cIdx: number) => {
                    const colKey = String(col)
                    const cellVal =
                      (row.cells_json as any)?.[colKey] ??
                      (row.cells_json as any)?.[String(cIdx)]
                    if (
                      cellVal === null ||
                      cellVal === undefined ||
                      cellVal === ""
                    )
                      return null
                    return (
                      <div
                        key={cIdx}
                        className="flex items-start justify-between gap-2 text-xs"
                      >
                        <span className="shrink-0 text-muted-foreground">
                          {colKey}:
                        </span>
                        <span className="text-right font-medium break-all text-foreground">
                          {String(cellVal)}
                        </span>
                      </div>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>

          {/* Desktop Table View */}
          <div className="hidden overflow-x-auto rounded-lg border bg-card lg:block">
            <Table>
              <TableHeader className="bg-muted/40">
                <TableRow>
                  <TableHead className="w-16 font-mono text-xs">#</TableHead>
                  {activeTable?.header_json?.map((col: any, idx: number) => (
                    <TableHead key={idx} className="text-xs font-medium">
                      {String(col)}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {rowsData?.items?.map((row) => (
                  <TableRow key={row.row_number}>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {row.row_number}
                    </TableCell>
                    {activeTable?.header_json?.map((col: any, cIdx: number) => {
                      const colKey = String(col)
                      const cellVal =
                        (row.cells_json as any)?.[colKey] ??
                        (row.cells_json as any)?.[String(cIdx)]
                      return (
                        <TableCell key={cIdx} className="text-xs">
                          {cellVal === null || cellVal === undefined
                            ? ""
                            : String(cellVal)}
                        </TableCell>
                      )
                    })}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      )}
    </div>
  )
}

function IssuesTab({ documentId }: { documentId: string }) {
  const { data, isLoading } = useDocumentValidations(documentId)
  const issues = data?.items ?? []

  if (isLoading)
    return <div className="h-48 animate-pulse rounded-lg bg-muted" />
  if (issues.length === 0)
    return (
      <EmptyState
        title="No validation issues"
        description="No errors or warnings recorded."
      />
    )

  return (
    <div className="space-y-3">
      {/* Mobile / Tablet Container Cards */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:hidden">
        {issues.map((issue) => (
          <div
            key={issue.id}
            className="space-y-2 rounded-lg border bg-card p-3.5 text-xs"
          >
            <div className="flex items-start justify-between gap-2">
              <span className="font-mono text-xs font-semibold text-foreground">
                {issue.rule_code}
              </span>
              <StatusBadge status={issue.severity} />
            </div>
            <p className="text-xs text-foreground/90">{issue.message}</p>
            <div className="flex items-center justify-between border-t pt-2 text-[11px] text-muted-foreground">
              <span className="font-mono">{issue.field_path || "General"}</span>
              <StatusBadge status={issue.resolution_status} />
            </div>
          </div>
        ))}
      </div>

      {/* Desktop Table View */}
      <div className="hidden overflow-hidden rounded-lg border bg-card lg:block">
        <Table>
          <TableHeader className="bg-muted/40">
            <TableRow>
              <TableHead>Severity</TableHead>
              <TableHead>Rule Code</TableHead>
              <TableHead>Message</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Field</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {issues.map((issue) => (
              <TableRow key={issue.id}>
                <TableCell>
                  <StatusBadge status={issue.severity} />
                </TableCell>
                <TableCell className="font-mono text-xs font-medium">
                  {issue.rule_code}
                </TableCell>
                <TableCell className="text-xs">{issue.message}</TableCell>
                <TableCell>
                  <StatusBadge status={issue.resolution_status} />
                </TableCell>
                <TableCell className="font-mono text-xs text-muted-foreground">
                  {issue.field_path || "—"}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}

function JobsTab({ documentId }: { documentId: string }) {
  const { data: jobs, isLoading } = useDocumentJobs(documentId)

  if (isLoading)
    return <div className="h-48 animate-pulse rounded-lg bg-muted" />
  if (!jobs || jobs.length === 0)
    return (
      <EmptyState
        title="No jobs recorded"
        description="No background jobs found."
      />
    )

  return (
    <div className="space-y-3">
      {/* Mobile / Tablet Container Cards */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:hidden">
        {jobs.map((job) => (
          <div
            key={job.id}
            className="space-y-2.5 rounded-lg border bg-card p-3.5 text-xs"
          >
            <div className="flex items-start justify-between gap-2">
              <div>
                <span className="text-xs font-semibold">
                  {jobTypeLabel(job.job_type)}
                </span>
                <span className="block font-mono text-[10px] text-muted-foreground">
                  Attempt #{job.attempt_number}
                </span>
              </div>
              <StatusBadge status={job.state} />
            </div>
            <div className="flex items-center justify-between font-mono text-[11px] text-muted-foreground">
              <span>
                {job.pages_completed} / {job.pages_total} pages
              </span>
              <span className="font-semibold text-foreground">
                {job.progress_percent}%
              </span>
            </div>
            <div className="flex items-center justify-between border-t pt-2 text-[11px] text-muted-foreground">
              <DateTime value={job.created_at} />
              <Link href={`/jobs/${job.id}`}>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 gap-1 px-2 text-xs"
                >
                  Inspect <ExternalLink className="h-3 w-3" />
                </Button>
              </Link>
            </div>
          </div>
        ))}
      </div>

      {/* Desktop Table View */}
      <div className="hidden overflow-hidden rounded-lg border bg-card lg:block">
        <Table>
          <TableHeader className="bg-muted/40">
            <TableRow>
              <TableHead>Job Type</TableHead>
              <TableHead>State</TableHead>
              <TableHead>Progress</TableHead>
              <TableHead>Pages</TableHead>
              <TableHead>Attempt</TableHead>
              <TableHead>Created</TableHead>
              <TableHead className="text-right">Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {jobs.map((job) => (
              <TableRow key={job.id}>
                <TableCell className="font-mono text-xs font-medium">
                  {jobTypeLabel(job.job_type)}
                </TableCell>
                <TableCell>
                  <StatusBadge status={job.state} />
                </TableCell>
                <TableCell className="font-mono text-xs">
                  {job.progress_percent}%
                </TableCell>
                <TableCell className="text-xs">
                  {job.pages_completed} / {job.pages_total}
                </TableCell>
                <TableCell className="font-mono text-xs">
                  #{job.attempt_number}
                </TableCell>
                <TableCell>
                  <DateTime value={job.created_at} />
                </TableCell>
                <TableCell className="text-right">
                  <Link href={`/jobs/${job.id}`}>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 gap-1 text-xs"
                    >
                      Inspect <ExternalLink className="h-3 w-3" />
                    </Button>
                  </Link>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
