"use client"

import React, { useCallback } from "react"
import { useDropzone } from "react-dropzone"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { useUpload, UploadItem } from "./upload-context"
import { usePublicConfig } from "@/features/auth/hooks"
import { formatBytes } from "@/lib/format"
import {
  Upload,
  FileText,
  CheckCircle2,
  AlertCircle,
  Copy,
  X,
  Loader2,
} from "lucide-react"
import Link from "next/link"

export function UploadSheet() {
  const { items, isOpen, setIsOpen, addFiles, removeItem, clearFinished } =
    useUpload()
  const { data: config } = usePublicConfig()

  const maxFileBytes = config?.upload_max_file_bytes ?? 200 * 1024 * 1024
  const maxFiles = config?.upload_max_files ?? 20

  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      if (items.length + acceptedFiles.length > maxFiles) {
        alert(`You can upload at most ${maxFiles} files at once.`)
        return
      }
      addFiles(acceptedFiles)
    },
    [addFiles, items.length, maxFiles]
  )

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    maxSize: maxFileBytes,
    accept: {
      "application/pdf": [".pdf"],
      "image/png": [".png"],
      "image/jpeg": [".jpg", ".jpeg"],
      "image/tiff": [".tiff", ".tif"],
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [
        ".xlsx",
      ],
      "application/vnd.ms-excel": [".xls"],
      "text/csv": [".csv"],
    },
  })

  return (
    <Sheet open={isOpen} onOpenChange={setIsOpen}>
      <SheetContent className="flex h-full w-full flex-col overflow-hidden p-6 sm:max-w-lg">
        <SheetHeader>
          <SheetTitle className="text-xl">Upload Documents</SheetTitle>
          <SheetDescription>
            Drop invoices, receipts, scans, or spreadsheets (up to 20 files, max{" "}
            {formatBytes(maxFileBytes)}).
          </SheetDescription>
        </SheetHeader>

        <div className="mt-4 flex flex-1 flex-col gap-4 overflow-hidden">
          {/* Dropzone */}
          <div
            {...getRootProps()}
            className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-6 text-center transition-colors ${
              isDragActive
                ? "border-primary bg-primary/5"
                : "border-border hover:border-primary/50 hover:bg-muted/30"
            }`}
          >
            <input {...getInputProps()} />
            <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-full bg-muted text-muted-foreground">
              <Upload className="h-5 w-5" />
            </div>
            <p className="text-sm font-medium">
              {isDragActive
                ? "Drop files here..."
                : "Click to select or drag and drop"}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              PDF, PNG, JPG, TIFF, XLSX, XLS, CSV
            </p>
          </div>

          {/* Files List */}
          <div className="flex items-center justify-between pt-2">
            <span className="text-xs font-medium text-muted-foreground">
              {items.length} {items.length === 1 ? "file" : "files"} in batch
            </span>
            {items.some(
              (i) =>
                i.status === "done" ||
                i.status === "rejected" ||
                i.status === "duplicate"
            ) && (
              <Button
                variant="ghost"
                size="sm"
                onClick={clearFinished}
                className="h-7 text-xs text-muted-foreground hover:text-foreground"
              >
                Clear finished
              </Button>
            )}
          </div>

          <div className="flex-1 space-y-2.5 overflow-y-auto pr-1">
            {items.map((item) => (
              <UploadItemRow
                key={item.id}
                item={item}
                onRemove={() => removeItem(item.id)}
              />
            ))}
          </div>
        </div>
      </SheetContent>
    </Sheet>
  )
}

function UploadItemRow({
  item,
  onRemove,
}: {
  item: UploadItem
  onRemove: () => void
}) {
  const isFinished =
    item.status === "done" ||
    item.status === "rejected" ||
    item.status === "duplicate"

  return (
    <div className="flex flex-col gap-1.5 rounded-lg border bg-card p-3 text-xs text-card-foreground">
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 flex-1 items-center gap-2 truncate">
          <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
          <span className="truncate font-medium" title={item.file.name}>
            {item.file.name}
          </span>
          <span className="shrink-0 font-mono text-[10px] text-muted-foreground">
            {formatBytes(item.file.size)}
          </span>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          {item.status === "uploading" && (
            <span className="font-mono text-[11px] font-medium text-blue-600">
              {item.progress}%
            </span>
          )}
          {item.status === "verifying" && (
            <span className="flex items-center gap-1 text-[11px] text-amber-600">
              <Loader2 className="h-3 w-3 animate-spin" /> Verifying
            </span>
          )}
          {item.status === "done" && (
            <span className="flex items-center gap-1 text-[11px] font-medium text-emerald-600">
              <CheckCircle2 className="h-3.5 w-3.5" /> Ready
            </span>
          )}
          {item.status === "duplicate" && (
            <span className="flex items-center gap-1 text-[11px] font-medium text-amber-600">
              <Copy className="h-3.5 w-3.5" /> Duplicate
            </span>
          )}
          {item.status === "rejected" && (
            <span className="flex items-center gap-1 text-[11px] font-medium text-rose-600">
              <AlertCircle className="h-3.5 w-3.5" /> Rejected
            </span>
          )}
          {isFinished && (
            <button
              onClick={onRemove}
              className="rounded p-0.5 text-muted-foreground transition-colors hover:text-foreground"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      {item.status === "uploading" && (
        <Progress value={item.progress} className="h-1.5" />
      )}

      {item.status === "duplicate" && item.duplicateOfId && (
        <div className="mt-0.5 flex items-center gap-1.5 text-amber-700 dark:text-amber-400">
          <span>Already exists:</span>
          <Link
            href={`/documents/${item.duplicateOfId}`}
            className="font-medium underline hover:text-amber-800"
          >
            View Document
          </Link>
        </div>
      )}

      {item.status === "rejected" && item.error && (
        <p className="mt-0.5 text-[11px] text-rose-600 dark:text-rose-400">
          {item.error}
        </p>
      )}

      {item.status === "done" && item.documentId && (
        <div className="mt-0.5 flex items-center gap-2">
          <Link
            href={`/documents/${item.documentId}`}
            className="font-medium text-primary underline hover:text-primary/80"
          >
            Open Document →
          </Link>
          {item.jobId && (
            <Link
              href={`/jobs/${item.jobId}`}
              className="ml-2 text-muted-foreground hover:underline"
            >
              View Processing Job
            </Link>
          )}
        </div>
      )}
    </div>
  )
}
