"use client"

import React, { Suspense, useState } from "react"
import { useQueryState, parseAsString, parseAsInteger } from "nuqs"
import { PageHeader } from "@/components/page-header"
import { useDocumentsList, useDeleteDocument } from "@/features/documents/hooks"
import { useCurrentUser } from "@/features/auth/hooks"
import { useUpload } from "@/features/upload/upload-context"
import { canUpload, canAdmin } from "@/lib/permissions"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { StatusBadge } from "@/components/status-badge"
import { DateTime } from "@/components/date-time"
import { Bytes } from "@/components/bytes"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/error-state"
import { ConfirmDialog } from "@/components/confirm-dialog"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Upload,
  Search,
  Trash2,
  ExternalLink,
  ChevronLeft,
  ChevronRight,
} from "lucide-react"
import Link from "next/link"
import { useQueryClient } from "@tanstack/react-query"
import { qk } from "@/lib/api/keys"
import { documentsApi } from "@/features/documents/api"

function DocumentsContent() {
  const { data: user } = useCurrentUser()
  const { setIsOpen: setUploadOpen } = useUpload()
  const queryClient = useQueryClient()
  const { mutate: deleteDoc, isPending: isDeleting } = useDeleteDocument()

  // URL state with nuqs (§2 & §3.3)
  const [filename, setFilename] = useQueryState(
    "filename",
    parseAsString.withDefault("")
  )
  const [status, setStatus] = useQueryState(
    "status",
    parseAsString.withDefault("all")
  )
  const [fileKind, setFileKind] = useQueryState(
    "kind",
    parseAsString.withDefault("all")
  )
  const [docType] = useQueryState("type", parseAsString.withDefault("all"))
  const [page, setPage] = useQueryState("page", parseAsInteger.withDefault(1))

  const [deleteTargetId, setDeleteTargetId] = useState<string | null>(null)

  const limit = 20
  const offset = (page - 1) * limit

  const queryParams = {
    limit,
    offset,
    filename: filename || undefined,
    status: status !== "all" ? status : undefined,
    file_kind: fileKind !== "all" ? fileKind : undefined,
    document_type: docType !== "all" ? docType : undefined,
  }

  const { data, isLoading, isError, error, refetch } =
    useDocumentsList(queryParams)

  const documents = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = Math.ceil(total / limit) || 1

  const prefetchDocument = (id: string) => {
    queryClient.prefetchQuery({
      queryKey: qk.documents.detail(id),
      queryFn: () => documentsApi.get(id),
      staleTime: 30_000,
    })
  }

  const handleDelete = () => {
    if (deleteTargetId) {
      deleteDoc(deleteTargetId, {
        onSuccess: () => setDeleteTargetId(null),
      })
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Documents"
        description="Search, inspect, and manage uploaded financial records and files."
      >
        {canUpload(user?.role) && (
          <Button onClick={() => setUploadOpen(true)} className="gap-2">
            <Upload className="h-4 w-4" />
            <span>Upload Files</span>
          </Button>
        )}
      </PageHeader>

      {/* Filter Toolbar */}
      <div className="flex flex-col items-stretch justify-between gap-3 md:flex-row md:items-center">
        <div className="flex flex-1 flex-wrap items-center gap-2.5 sm:flex-nowrap">
          <div className="relative min-w-[180px] flex-1">
            <Search className="absolute top-2.5 left-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search filename..."
              value={filename}
              onChange={(e) => {
                setFilename(e.target.value)
                setPage(1)
              }}
              className="h-9 pl-9 text-xs"
            />
          </div>

          <div className="flex w-full items-center gap-2 sm:w-auto">
            <Select
              value={status}
              onValueChange={(val) => {
                setStatus(val)
                setPage(1)
              }}
            >
              <SelectTrigger className="h-9 flex-1 text-xs sm:w-[140px]">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Statuses</SelectItem>
                <SelectItem value="RECEIVED">Received</SelectItem>
                <SelectItem value="PARSING">Parsing</SelectItem>
                <SelectItem value="PARSED">Parsed</SelectItem>
                <SelectItem value="EXTRACTING">Extracting</SelectItem>
                <SelectItem value="EXTRACTED">Extracted</SelectItem>
                <SelectItem value="VALIDATING">Validating</SelectItem>
                <SelectItem value="VALIDATED">Validated</SelectItem>
                <SelectItem value="PROCESSED">Processed</SelectItem>
                <SelectItem value="FAILED">Failed</SelectItem>
              </SelectContent>
            </Select>

            <Select
              value={fileKind}
              onValueChange={(val) => {
                setFileKind(val)
                setPage(1)
              }}
            >
              <SelectTrigger className="h-9 flex-1 text-xs sm:w-[130px]">
                <SelectValue placeholder="File Kind" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Kinds</SelectItem>
                <SelectItem value="PDF">PDF</SelectItem>
                <SelectItem value="IMAGE">Image</SelectItem>
                <SelectItem value="SPREADSHEET">Spreadsheet</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="flex items-center self-start font-mono text-xs text-muted-foreground md:self-center">
          Showing {total === 0 ? 0 : offset + 1}–
          {Math.min(offset + limit, total)} of {total}
        </div>
      </div>

      {/* Main Table */}
      {isLoading ? (
        <div className="space-y-2 rounded-lg border p-4">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="h-10 animate-pulse rounded bg-muted" />
          ))}
        </div>
      ) : isError ? (
        <ErrorState
          message={(error as any)?.message || "Failed to load documents"}
          requestId={(error as any)?.requestId}
          onRetry={() => refetch()}
        />
      ) : documents.length === 0 ? (
        <EmptyState
          title="No documents found"
          description={
            filename || status !== "all"
              ? "No documents matched your current search filters."
              : "Upload documents to begin extraction, validation, and review."
          }
          actionLabel={canUpload(user?.role) ? "Upload Document" : undefined}
          onAction={
            canUpload(user?.role) ? () => setUploadOpen(true) : undefined
          }
        />
      ) : (
        <div className="space-y-4">
          {/* Mobile / Tablet Container Cards */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:hidden">
            {documents.map((doc) => (
              <div
                key={doc.id}
                className="flex flex-col justify-between space-y-3 rounded-lg border bg-card p-4 transition-colors hover:border-primary/40"
                onMouseEnter={() => prefetchDocument(doc.id)}
                onFocus={() => prefetchDocument(doc.id)}
              >
                <div className="space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    <Link
                      href={`/documents/${doc.id}`}
                      className="line-clamp-2 text-sm font-medium text-foreground transition-colors hover:text-primary"
                      title={doc.original_filename}
                    >
                      {doc.original_filename}
                    </Link>
                    <div className="flex shrink-0 items-center gap-1">
                      <Link href={`/documents/${doc.id}`}>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-muted-foreground hover:text-foreground"
                        >
                          <ExternalLink className="h-3.5 w-3.5" />
                        </Button>
                      </Link>
                      {canAdmin(user?.role) && (
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => setDeleteTargetId(doc.id)}
                          className="h-7 w-7 text-muted-foreground hover:text-destructive"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      )}
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <StatusBadge status={doc.status} />
                    {doc.validation_outcome && (
                      <StatusBadge status={doc.validation_outcome} />
                    )}
                    <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground uppercase">
                      {doc.file_kind} · {doc.document_type}
                    </span>
                  </div>
                </div>

                <div className="flex items-center justify-between border-t pt-2 text-[11px] text-muted-foreground">
                  <Bytes bytes={doc.file_size_bytes} />
                  <DateTime value={doc.created_at} />
                </div>
              </div>
            ))}
          </div>

          {/* Desktop Table View */}
          <div className="hidden overflow-hidden rounded-lg border bg-card lg:block">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/40">
                  <TableHead className="w-[300px]">Filename</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Kind</TableHead>
                  <TableHead>Size</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Validation</TableHead>
                  <TableHead>Uploaded</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {documents.map((doc) => (
                  <TableRow
                    key={doc.id}
                    className="transition-colors hover:bg-muted/30"
                    onMouseEnter={() => prefetchDocument(doc.id)}
                    onFocus={() => prefetchDocument(doc.id)}
                  >
                    <TableCell className="font-medium">
                      <Link
                        href={`/documents/${doc.id}`}
                        className="flex max-w-[280px] items-center gap-1.5 truncate text-foreground transition-colors hover:text-primary"
                        title={doc.original_filename}
                      >
                        <span className="truncate">
                          {doc.original_filename}
                        </span>
                      </Link>
                    </TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground uppercase">
                      {doc.document_type}
                    </TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground uppercase">
                      {doc.file_kind}
                    </TableCell>
                    <TableCell>
                      <Bytes bytes={doc.file_size_bytes} />
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={doc.status} />
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={doc.validation_outcome} />
                    </TableCell>
                    <TableCell>
                      <DateTime value={doc.created_at} />
                    </TableCell>
                    <TableCell className="space-x-1 text-right">
                      <Link href={`/documents/${doc.id}`}>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-muted-foreground hover:text-foreground"
                        >
                          <ExternalLink className="h-4 w-4" />
                        </Button>
                      </Link>
                      {canAdmin(user?.role) && (
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => setDeleteTargetId(doc.id)}
                          className="h-8 w-8 text-muted-foreground hover:text-destructive"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          {/* Pagination bar */}
          <div className="flex items-center justify-between rounded-lg border bg-card px-4 py-3">
            <div className="font-mono text-xs text-muted-foreground">
              Page {page} of {totalPages}
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="h-8 gap-1 text-xs"
              >
                <ChevronLeft className="h-3.5 w-3.5" /> Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="h-8 gap-1 text-xs"
              >
                Next <ChevronRight className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation */}
      <ConfirmDialog
        open={!!deleteTargetId}
        onOpenChange={(open) => !open && setDeleteTargetId(null)}
        title="Delete Document"
        description="Are you sure you want to delete this document? This will permanently remove its extracted invoices, tables, and validation history."
        confirmText="Delete"
        isDestructive
        isLoading={isDeleting}
        onConfirm={handleDelete}
      />
    </div>
  )
}

export default function DocumentsPage() {
  return (
    <Suspense
      fallback={<div className="h-96 animate-pulse rounded-lg bg-card" />}
    >
      <DocumentsContent />
    </Suspense>
  )
}
