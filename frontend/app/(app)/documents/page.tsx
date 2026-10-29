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
  const [filename, setFilename] = useQueryState("filename", parseAsString.withDefault(""))
  const [status, setStatus] = useQueryState("status", parseAsString.withDefault("all"))
  const [fileKind, setFileKind] = useQueryState("kind", parseAsString.withDefault("all"))
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

  const { data, isLoading, isError, error, refetch } = useDocumentsList(queryParams)

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
      <div className="flex flex-col md:flex-row gap-3 items-stretch md:items-center justify-between">
        <div className="flex flex-1 items-center gap-3">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search filename..."
              value={filename}
              onChange={(e) => {
                setFilename(e.target.value)
                setPage(1)
              }}
              className="pl-9 h-9 text-xs"
            />
          </div>

          <Select
            value={status}
            onValueChange={(val) => {
              setStatus(val)
              setPage(1)
            }}
          >
            <SelectTrigger className="w-[140px] h-9 text-xs">
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
            <SelectTrigger className="w-[130px] h-9 text-xs">
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

        <div className="text-xs text-muted-foreground flex items-center self-end md:self-center font-mono">
          Showing {total === 0 ? 0 : offset + 1}–{Math.min(offset + limit, total)} of {total}
        </div>
      </div>

      {/* Main Table */}
      {isLoading ? (
        <div className="space-y-2 border rounded-lg p-4">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="h-10 bg-muted animate-pulse rounded" />
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
          onAction={canUpload(user?.role) ? () => setUploadOpen(true) : undefined}
        />
      ) : (
        <div className="border rounded-lg overflow-hidden bg-card">
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
                  className="hover:bg-muted/30 transition-colors"
                  onMouseEnter={() => prefetchDocument(doc.id)}
                  onFocus={() => prefetchDocument(doc.id)}
                >
                  <TableCell className="font-medium">
                    <Link
                      href={`/documents/${doc.id}`}
                      className="text-foreground hover:text-primary transition-colors flex items-center gap-1.5 truncate max-w-[280px]"
                      title={doc.original_filename}
                    >
                      <span className="truncate">{doc.original_filename}</span>
                    </Link>
                  </TableCell>
                  <TableCell className="font-mono text-xs uppercase text-muted-foreground">
                    {doc.document_type}
                  </TableCell>
                  <TableCell className="font-mono text-xs uppercase text-muted-foreground">
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
                  <TableCell className="text-right space-x-1">
                    <Link href={`/documents/${doc.id}`}>
                      <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-foreground">
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

          {/* Pagination bar */}
          <div className="flex items-center justify-between px-4 py-3 border-t bg-muted/20">
            <div className="text-xs text-muted-foreground font-mono">
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
    <Suspense fallback={<div className="h-96 rounded-lg bg-card animate-pulse" />}>
      <DocumentsContent />
    </Suspense>
  )
}
