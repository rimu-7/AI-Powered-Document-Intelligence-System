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
  const { items, isOpen, setIsOpen, addFiles, removeItem, clearFinished } = useUpload()
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
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
      "application/vnd.ms-excel": [".xls"],
      "text/csv": [".csv"],
    },
  })

  return (
    <Sheet open={isOpen} onOpenChange={setIsOpen}>
      <SheetContent className="w-full sm:max-w-lg flex flex-col h-full overflow-hidden p-6">
        <SheetHeader>
          <SheetTitle className="text-xl">Upload Documents</SheetTitle>
          <SheetDescription>
            Drop invoices, receipts, scans, or spreadsheets (up to 20 files, max {formatBytes(maxFileBytes)}).
          </SheetDescription>
        </SheetHeader>

        <div className="mt-4 flex-1 flex flex-col gap-4 overflow-hidden">
          {/* Dropzone */}
          <div
            {...getRootProps()}
            className={`border-2 border-dashed rounded-lg p-6 flex flex-col items-center justify-center text-center cursor-pointer transition-colors ${
              isDragActive
                ? "border-primary bg-primary/5"
                : "border-border hover:border-primary/50 hover:bg-muted/30"
            }`}
          >
            <input {...getInputProps()} />
            <div className="h-10 w-10 rounded-full bg-muted flex items-center justify-center mb-2 text-muted-foreground">
              <Upload className="h-5 w-5" />
            </div>
            <p className="text-sm font-medium">
              {isDragActive ? "Drop files here..." : "Click to select or drag and drop"}
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              PDF, PNG, JPG, TIFF, XLSX, XLS, CSV
            </p>
          </div>

          {/* Files List */}
          <div className="flex items-center justify-between pt-2">
            <span className="text-xs font-medium text-muted-foreground">
              {items.length} {items.length === 1 ? "file" : "files"} in batch
            </span>
            {items.some((i) => i.status === "done" || i.status === "rejected" || i.status === "duplicate") && (
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

          <div className="flex-1 overflow-y-auto space-y-2.5 pr-1">
            {items.map((item) => (
              <UploadItemRow key={item.id} item={item} onRemove={() => removeItem(item.id)} />
            ))}
          </div>
        </div>
      </SheetContent>
    </Sheet>
  )
}

function UploadItemRow({ item, onRemove }: { item: UploadItem; onRemove: () => void }) {
  const isFinished = item.status === "done" || item.status === "rejected" || item.status === "duplicate"

  return (
    <div className="flex flex-col gap-1.5 p-3 rounded-lg border bg-card text-card-foreground text-xs">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 truncate flex-1 min-w-0">
          <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
          <span className="font-medium truncate" title={item.file.name}>
            {item.file.name}
          </span>
          <span className="text-muted-foreground text-[10px] shrink-0 font-mono">
            {formatBytes(item.file.size)}
          </span>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {item.status === "uploading" && (
            <span className="text-blue-600 font-mono text-[11px] font-medium">{item.progress}%</span>
          )}
          {item.status === "verifying" && (
            <span className="flex items-center gap-1 text-amber-600 text-[11px]">
              <Loader2 className="h-3 w-3 animate-spin" /> Verifying
            </span>
          )}
          {item.status === "done" && (
            <span className="flex items-center gap-1 text-emerald-600 font-medium text-[11px]">
              <CheckCircle2 className="h-3.5 w-3.5" /> Ready
            </span>
          )}
          {item.status === "duplicate" && (
            <span className="flex items-center gap-1 text-amber-600 font-medium text-[11px]">
              <Copy className="h-3.5 w-3.5" /> Duplicate
            </span>
          )}
          {item.status === "rejected" && (
            <span className="flex items-center gap-1 text-rose-600 font-medium text-[11px]">
              <AlertCircle className="h-3.5 w-3.5" /> Rejected
            </span>
          )}
          {isFinished && (
            <button
              onClick={onRemove}
              className="text-muted-foreground hover:text-foreground p-0.5 rounded transition-colors"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      {item.status === "uploading" && <Progress value={item.progress} className="h-1.5" />}

      {item.status === "duplicate" && item.duplicateOfId && (
        <div className="flex items-center gap-1.5 text-amber-700 dark:text-amber-400 mt-0.5">
          <span>Already exists:</span>
          <Link
            href={`/documents/${item.duplicateOfId}`}
            className="underline font-medium hover:text-amber-800"
          >
            View Document
          </Link>
        </div>
      )}

      {item.status === "rejected" && item.error && (
        <p className="text-rose-600 dark:text-rose-400 text-[11px] mt-0.5">{item.error}</p>
      )}

      {item.status === "done" && item.documentId && (
        <div className="flex items-center gap-2 mt-0.5">
          <Link
            href={`/documents/${item.documentId}`}
            className="text-primary underline font-medium hover:text-primary/80"
          >
            Open Document →
          </Link>
          {item.jobId && (
            <Link
              href={`/jobs/${item.jobId}`}
              className="text-muted-foreground hover:underline ml-2"
            >
              View Processing Job
            </Link>
          )}
        </div>
      )}
    </div>
  )
}
