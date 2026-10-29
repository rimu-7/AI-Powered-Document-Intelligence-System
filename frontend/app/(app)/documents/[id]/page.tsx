"use client"

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
} from "lucide-react"
import Link from "next/link"
import { useRouter } from "next/navigation"

export default function DocumentDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  const router = useRouter()
  const { data: user } = useCurrentUser()
  const [tab, setTab] = useQueryState("tab", parseAsString.withDefault("invoices"))
  const [deleteOpen, setDeleteOpen] = useState(false)

  const { data: doc, isLoading, isError, error, refetch } = useDocument(id)
  const { mutate: reprocess, isPending: isReprocessing } = useReprocessDocument()
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
        <div className="h-20 bg-muted animate-pulse rounded-lg" />
        <div className="h-96 bg-muted animate-pulse rounded-lg" />
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
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-6 rounded-xl border bg-card text-card-foreground shadow-sm">
        <div className="space-y-1.5 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-xl font-bold tracking-tight truncate" title={doc.original_filename}>
              {doc.original_filename}
            </h1>
            <StatusBadge status={doc.status} />
            <StatusBadge status={doc.validation_outcome} />
          </div>
          <div className="flex items-center gap-3 text-xs text-muted-foreground flex-wrap font-mono">
            <span>Kind: {doc.file_kind}</span>
            <span>•</span>
            <span>Type: {doc.document_type}</span>
            <span>•</span>
            <Bytes bytes={doc.file_size_bytes} />
            <span>•</span>
            <DateTime value={doc.created_at} />
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0 flex-wrap">
          <Button variant="outline" size="sm" onClick={handleDownload} className="gap-1.5 text-xs">
            <Download className="h-3.5 w-3.5" />
            Download
          </Button>

          {hasPermission(user?.role, "JOB_MANAGE") && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => reprocess(id)}
              disabled={isReprocessing}
              className="gap-1.5 text-xs"
            >
              <RotateCw className={`h-3.5 w-3.5 ${isReprocessing ? "animate-spin" : ""}`} />
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
      <Tabs value={tab} onValueChange={(val) => setTab(val)} className="space-y-4">
        <TabsList className="bg-muted/60 p-1 flex-wrap">
          <TabsTrigger value="invoices" className="text-xs gap-1.5">
            <FileText className="h-3.5 w-3.5" />
            Invoices
          </TabsTrigger>
          <TabsTrigger value="pages" className="text-xs gap-1.5">
            <Layers className="h-3.5 w-3.5" />
            Pages
          </TabsTrigger>
          <TabsTrigger value="text" className="text-xs gap-1.5">
            <FileText className="h-3.5 w-3.5" />
            Extracted Text
          </TabsTrigger>
          <TabsTrigger value="tables" className="text-xs gap-1.5">
            <TableIcon className="h-3.5 w-3.5" />
            Tables & Sheets
          </TabsTrigger>
          <TabsTrigger value="issues" className="text-xs gap-1.5">
            <AlertCircle className="h-3.5 w-3.5" />
            Issues
          </TabsTrigger>
          <TabsTrigger value="jobs" className="text-xs gap-1.5">
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

  if (isLoading) return <div className="h-48 bg-muted animate-pulse rounded-lg" />
  if (!invoices || invoices.length === 0) {
    return <EmptyState title="No invoices found" description="No invoices extracted from this document." />
  }

  return (
    <div className="border rounded-lg overflow-hidden bg-card">
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
              <TableCell className="font-mono font-medium">{inv.invoice_number || "—"}</TableCell>
              <TableCell>{inv.supplier_name || "—"}</TableCell>
              <TableCell>{inv.invoice_date || "—"}</TableCell>
              <TableCell>
                <Money value={inv.total_amount} currency={inv.currency} />
              </TableCell>
              <TableCell>
                <StatusBadge status={inv.review_status} />
              </TableCell>
              <TableCell className="font-mono text-xs">v{inv.version}</TableCell>
              <TableCell className="text-right">
                <Link href={`/invoices/${inv.id}`}>
                  <Button size="sm" variant="outline" className="gap-1.5 text-xs">
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
  )
}

function PagesTab({ documentId }: { documentId: string }) {
  const { data, isLoading } = useDocumentPages(documentId, { limit: 100 })
  const pages = data?.items ?? []

  if (isLoading) return <div className="h-64 bg-muted animate-pulse rounded-lg" />
  if (pages.length === 0) return <EmptyState title="No pages found" description="No pages parsed yet." />

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-4">
      {pages.map((p) => {
        const imageUrl = documentsApi.getPageImageUrl(documentId, p.page_number, 300)
        return (
          <div key={p.id} className="border rounded-lg overflow-hidden bg-card flex flex-col group">
            <div className="aspect-[3/4] relative bg-muted/40 overflow-hidden flex items-center justify-center">
              <img
                src={imageUrl}
                alt={`Page ${p.page_number}`}
                loading="lazy"
                className="w-full h-full object-contain group-hover:scale-105 transition-transform duration-200"
                onError={(e) => {
                  // Fallback placeholder if image endpoint fails
                  ;(e.target as HTMLElement).style.display = "none"
                }}
              />
            </div>
            <div className="p-2.5 flex items-center justify-between border-t text-xs">
              <span className="font-medium">Page {p.page_number}</span>
              <span className="text-muted-foreground font-mono text-[10px]">{p.character_count} chars</span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

function TextTab({ documentId }: { documentId: string }) {
  const [pageFrom, setPageFrom] = useState(1)
  const { data: textData, isLoading } = useDocumentText(documentId, pageFrom, pageFrom + 4)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">Pages {pageFrom}–{pageFrom + 4}</span>
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
        <div className="h-64 bg-muted animate-pulse rounded-lg" />
      ) : !textData || textData.length === 0 ? (
        <EmptyState title="No text found" description="No text extracted for the requested page range." />
      ) : (
        <div className="space-y-4">
          {textData.map((pt) => (
            <Card key={pt.page_number}>
              <CardHeader className="py-2.5 px-4 bg-muted/30 border-b">
                <CardTitle className="text-xs font-mono font-medium">Page {pt.page_number}</CardTitle>
              </CardHeader>
              <CardContent className="p-4">
                <pre className="font-mono text-xs whitespace-pre-wrap leading-relaxed text-foreground/90">
                  {pt.text || <span className="text-muted-foreground italic">(Blank page)</span>}
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

  if (isLoading) return <div className="h-48 bg-muted animate-pulse rounded-lg" />
  if (tables.length === 0) return <EmptyState title="No tables found" description="No tabular structures detected." />

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
            className="h-8 text-xs shrink-0 font-mono"
          >
            {t.sheet_name || `Table ${t.table_index + 1}`} (page {t.page_number || "—"})
          </Button>
        ))}
      </div>

      {/* Row view */}
      <div className="border rounded-lg overflow-x-auto bg-card">
        {rowsLoading ? (
          <div className="p-4 space-y-2">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-8 bg-muted animate-pulse rounded" />
            ))}
          </div>
        ) : (
          <Table>
            <TableHeader className="bg-muted/40">
              <TableRow>
                <TableHead className="w-16 font-mono text-xs">#</TableHead>
                {activeTable?.header_json?.map((col: any, idx: number) => (
                  <TableHead key={idx} className="font-medium text-xs">
                    {String(col)}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {rowsData?.items?.map((row) => (
                <TableRow key={row.row_number}>
                  <TableCell className="font-mono text-xs text-muted-foreground">{row.row_number}</TableCell>
                  {activeTable?.header_json?.map((col: any, cIdx: number) => {
                    const colKey = String(col)
                    const cellVal = (row.cells_json as any)?.[colKey] ?? (row.cells_json as any)?.[String(cIdx)]
                    return (
                      <TableCell key={cIdx} className="text-xs">
                        {cellVal === null || cellVal === undefined ? "" : String(cellVal)}
                      </TableCell>
                    )
                  })}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>
    </div>
  )
}

function IssuesTab({ documentId }: { documentId: string }) {
  const { data, isLoading } = useDocumentValidations(documentId)
  const issues = data?.items ?? []

  if (isLoading) return <div className="h-48 bg-muted animate-pulse rounded-lg" />
  if (issues.length === 0) return <EmptyState title="No validation issues" description="No errors or warnings recorded." />

  return (
    <div className="border rounded-lg overflow-hidden bg-card">
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
              <TableCell className="font-mono text-xs font-medium">{issue.rule_code}</TableCell>
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
  )
}

function JobsTab({ documentId }: { documentId: string }) {
  const { data: jobs, isLoading } = useDocumentJobs(documentId)

  if (isLoading) return <div className="h-48 bg-muted animate-pulse rounded-lg" />
  if (!jobs || jobs.length === 0) return <EmptyState title="No jobs recorded" description="No background jobs found." />

  return (
    <div className="border rounded-lg overflow-hidden bg-card">
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
              <TableCell className="font-mono text-xs font-medium">{job.job_type}</TableCell>
              <TableCell>
                <StatusBadge status={job.state} />
              </TableCell>
              <TableCell className="font-mono text-xs">{job.progress_percent}%</TableCell>
              <TableCell className="text-xs">
                {job.pages_completed} / {job.pages_total}
              </TableCell>
              <TableCell className="font-mono text-xs">#{job.attempt_number}</TableCell>
              <TableCell>
                <DateTime value={job.created_at} />
              </TableCell>
              <TableCell className="text-right">
                <Link href={`/jobs/${job.id}`}>
                  <Button variant="ghost" size="sm" className="h-7 text-xs gap-1">
                    Inspect <ExternalLink className="h-3 w-3" />
                  </Button>
                </Link>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
