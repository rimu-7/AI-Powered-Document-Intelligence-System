"use client"

import React, { createContext, useContext, useState, useCallback } from "react"
import { uploadApi } from "./api"
import { useQueryClient } from "@tanstack/react-query"
import { invalidateForMutation } from "@/lib/api/invalidation"

export type UploadItemStatus =
  | "queued"
  | "uploading"
  | "verifying"
  | "processing"
  | "done"
  | "rejected"
  | "duplicate"

export interface UploadItem {
  id: string
  file: File
  progress: number
  status: UploadItemStatus
  error?: string
  documentId?: string | null
  jobId?: string | null
  duplicateOfId?: string | null
}

interface UploadContextType {
  items: UploadItem[]
  isOpen: boolean
  setIsOpen: (open: boolean) => void
  activeCount: number
  addFiles: (files: File[]) => void
  removeItem: (id: string) => void
  clearFinished: () => void
}

const UploadContext = createContext<UploadContextType | null>(null)

export function UploadProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<UploadItem[]>([])
  const [isOpen, setIsOpen] = useState(false)
  const queryClient = useQueryClient()

  const activeCount = items.filter(
    (i) => i.status === "uploading" || i.status === "verifying" || i.status === "queued"
  ).length

  const updateItem = useCallback((id: string, updates: Partial<UploadItem>) => {
    setItems((prev) => prev.map((item) => (item.id === id ? { ...item, ...updates } : item)))
  }, [])

  const processFile = useCallback(
    async (item: UploadItem) => {
      updateItem(item.id, { status: "uploading", progress: 0 })

      try {
        let ticket: any = null
        let directAvailable = true

        try {
          ticket = await uploadApi.createDirectUpload(item.file.name, item.file.size)
        } catch (err: any) {
          if (err.status === 409 || err.code === "DIRECT_UPLOAD_UNAVAILABLE") {
            directAvailable = false
          } else if (err.code === "DUPLICATE_DOCUMENT" || err.status === 409) {
            updateItem(item.id, {
              status: "duplicate",
              error: err.message,
              duplicateOfId: err.details?.existing_document_id,
            })
            return
          } else {
            throw err
          }
        }

        if (directAvailable && ticket) {
          // Direct upload via presigned / signed URL
          await uploadApi.uploadToSignedUrl(ticket.upload_url, item.file, (pct) => {
            updateItem(item.id, { progress: pct })
          })

          updateItem(item.id, { status: "verifying", progress: 100 })
          const completeRes = await uploadApi.completeDirectUpload(ticket.upload_id)

          updateItem(item.id, {
            status: "done",
            documentId: ticket.document_id,
            jobId: completeRes?.job_id,
          })
        } else {
          // Fallback to standard multipart upload
          const fallbackRes = await uploadApi.uploadMultipartFallback(
            [item.file],
            typeof crypto !== "undefined" ? crypto.randomUUID() : undefined,
            (pct) => updateItem(item.id, { progress: pct })
          )

          const firstResult = fallbackRes?.results?.[0]
          if (firstResult?.status === "rejected") {
            const errMsg = typeof firstResult.error === "object" && firstResult.error !== null
              ? (firstResult.error as any).message
              : "Upload rejected"
            updateItem(item.id, {
              status: "rejected",
              error: errMsg || "Upload rejected",
            })
          } else {
            updateItem(item.id, {
              status: "done",
              documentId: firstResult?.document_id,
              jobId: firstResult?.job_id,
            })
          }
        }

        await invalidateForMutation(queryClient, "upload_documents")
      } catch (err: any) {
        updateItem(item.id, {
          status: "rejected",
          error: err.message || "Upload failed",
        })
      }
    },
    [queryClient, updateItem]
  )

  const addFiles = useCallback(
    (files: File[]) => {
      const newItems: UploadItem[] = files.map((file) => ({
        id: typeof crypto !== "undefined" ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`,
        file,
        progress: 0,
        status: "queued",
      }))

      setItems((prev) => [...prev, ...newItems])
      setIsOpen(true)

      // Process up to 3 at a time
      const queue = [...newItems]
      const running = new Set<string>()

      const runNext = async () => {
        if (queue.length === 0) return
        if (running.size >= 3) return

        const next = queue.shift()
        if (!next) return

        running.add(next.id)
        try {
          await processFile(next)
        } finally {
          running.delete(next.id)
          runNext()
        }
      }

      for (let i = 0; i < 3; i++) {
        runNext()
      }
    },
    [processFile]
  )

  const removeItem = useCallback((id: string) => {
    setItems((prev) => prev.filter((i) => i.id !== id))
  }, [])

  const clearFinished = useCallback(() => {
    setItems((prev) => prev.filter((i) => i.status === "uploading" || i.status === "queued" || i.status === "verifying"))
  }, [])

  return (
    <UploadContext.Provider
      value={{
        items,
        isOpen,
        setIsOpen,
        activeCount,
        addFiles,
        removeItem,
        clearFinished,
      }}
    >
      {children}
    </UploadContext.Provider>
  )
}

export function useUpload() {
  const ctx = useContext(UploadContext)
  if (!ctx) {
    throw new Error("useUpload must be used within an UploadProvider")
  }
  return ctx
}
