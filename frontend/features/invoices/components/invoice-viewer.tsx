"use client"

import React, { useState, useRef } from "react"
import { useDocumentPages } from "@/features/documents/hooks"
import { documentsApi } from "@/features/documents/api"
import { Button } from "@/components/ui/button"
import {
  ChevronLeft,
  ChevronRight,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  FileText,
  AlertCircle,
  Loader2,
} from "lucide-react"

export interface EvidenceBox {
  page_number?: number
  bounding_box?: [number, number, number, number] | number[] // [x0, y0, x1, y1] or [ymin, xmin, ymax, xmax]
  sheet?: string
  row?: number
  cell?: string
  text?: string
}

interface InvoiceViewerProps {
  documentId: string
  pageStart?: number | null
  activeEvidence?: EvidenceBox | null
}

export function InvoiceViewer({
  documentId,
  pageStart = 1,
  activeEvidence,
}: InvoiceViewerProps) {
  const { data: pagesData, isLoading } = useDocumentPages(documentId, { limit: 100 })
  const pages = pagesData?.items ?? []

  const [userPage, setUserPage] = useState<number | null>(null)
  const [prevEvidence, setPrevEvidence] = useState<EvidenceBox | null | undefined>(activeEvidence)
  const [zoom, setZoom] = useState<number>(100)
  const [imgRetryCount, setImgRetryCount] = useState<number>(0)
  const imgRef = useRef<HTMLImageElement>(null)

  if (activeEvidence !== prevEvidence) {
    setPrevEvidence(activeEvidence)
    if (activeEvidence?.page_number) {
      setUserPage(activeEvidence.page_number)
    }
  }

  const currentPage = userPage ?? (activeEvidence?.page_number || pageStart || 1)

  const currentKey = `${documentId}:${currentPage}:${imgRetryCount}`
  const [loadedKey, setLoadedKey] = useState<string | null>(null)
  const [errorKey, setErrorKey] = useState<string | null>(null)

  const imgLoading = loadedKey !== currentKey && errorKey !== currentKey
  const imgError = errorKey === currentKey

  const setCurrentPage = (updater: number | ((p: number) => number)) => {
    setUserPage((prev) => {
      const cur = prev ?? (activeEvidence?.page_number || pageStart || 1)
      return typeof updater === "function" ? updater(cur) : updater
    })
  }

  const totalPages = pages.length || 1
  const currentPageMeta = pages.find((p) => p.page_number === currentPage)
  const pageWidth = currentPageMeta?.page_width || 612
  const pageHeight = currentPageMeta?.page_height || 792

  const baseImageUrl = documentsApi.getPageImageUrl(documentId, currentPage, 1200)
  const imageUrl = imgRetryCount > 0 ? `${baseImageUrl}&r=${imgRetryCount}` : baseImageUrl

  // Compute highlight overlay coordinates
  let overlayStyle: React.CSSProperties | null = null
  if (
    activeEvidence &&
    activeEvidence.page_number === currentPage &&
    activeEvidence.bounding_box &&
    activeEvidence.bounding_box.length === 4
  ) {
    const [b0, b1, b2, b3] = activeEvidence.bounding_box

    // Check if normalized (0..1) or point coordinates
    const isNormalized = b0 <= 1 && b1 <= 1 && b2 <= 1 && b3 <= 1
    if (isNormalized) {
      const left = Math.min(b0, b2) * 100
      const top = Math.min(b1, b3) * 100
      const width = Math.abs(b2 - b0) * 100
      const height = Math.abs(b3 - b1) * 100
      overlayStyle = {
        left: `${left}%`,
        top: `${top}%`,
        width: `${width}%`,
        height: `${height}%`,
      }
    } else {
      const minX = Math.min(b0, b2)
      const minY = Math.min(b1, b3)
      const w = Math.abs(b2 - b0)
      const h = Math.abs(b3 - b1)
      overlayStyle = {
        left: `${(minX / pageWidth) * 100}%`,
        top: `${(minY / pageHeight) * 100}%`,
        width: `${(w / pageWidth) * 100}%`,
        height: `${(h / pageHeight) * 100}%`,
      }
    }
  }

  return (
    <div className="flex flex-col h-full border rounded-lg overflow-hidden bg-card">
      {/* Top Viewer Controls */}
      <div className="flex items-center justify-between px-3 py-2 border-b bg-muted/40 text-xs shrink-0">
        <div className="flex items-center gap-1.5">
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
            disabled={currentPage <= 1}
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="font-mono text-xs select-none">
            {currentPage} / {totalPages}
          </span>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
            disabled={currentPage >= totalPages}
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>

        {activeEvidence?.sheet && (
          <div className="text-xs bg-muted px-2 py-0.5 rounded font-mono text-muted-foreground">
            Sheet: {activeEvidence.sheet} | Row: {activeEvidence.row} | Cell: {activeEvidence.cell}
          </div>
        )}

        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => setZoom((z) => Math.max(50, z - 20))}
            title="Zoom out"
          >
            <ZoomOut className="h-3.5 w-3.5" />
          </Button>
          <button
            onClick={() => setZoom(100)}
            className="font-mono text-[11px] w-10 text-center hover:bg-muted py-0.5 rounded transition-colors"
            title="Reset to 100%"
          >
            {zoom}%
          </button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => setZoom((z) => Math.min(250, z + 20))}
            title="Zoom in"
          >
            <ZoomIn className="h-3.5 w-3.5" />
          </Button>
          {zoom !== 100 && (
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 text-muted-foreground hover:text-foreground"
              onClick={() => setZoom(100)}
              title="Reset zoom"
            >
              <RotateCcw className="h-3 w-3" />
            </Button>
          )}
        </div>
      </div>

      {/* Viewer Main Stage */}
      <div className="flex-1 overflow-auto p-4 flex items-start justify-center bg-zinc-950/10 dark:bg-zinc-950/50 relative">
        {isLoading ? (
          <div className="h-96 w-72 bg-muted/60 animate-pulse rounded-md m-auto" />
        ) : imgError ? (
          <div className="flex flex-col items-center justify-center p-8 text-center rounded-lg border border-dashed border-border/80 bg-background/50 max-w-sm m-auto">
            <div className="h-10 w-10 rounded-full bg-rose-500/10 text-rose-500 flex items-center justify-center mb-3">
              <AlertCircle className="h-5 w-5" />
            </div>
            <p className="text-sm font-medium">Unable to load page {currentPage}</p>
            <p className="text-xs text-muted-foreground mt-1">
              The page image could not be rendered from document storage.
            </p>
            <Button
              variant="outline"
              size="sm"
              className="mt-4 text-xs gap-1.5"
              onClick={() => {
                setErrorKey(null)
                setImgRetryCount((c) => c + 1)
              }}
            >
              <RotateCcw className="h-3.5 w-3.5" />
              Try again
            </Button>
          </div>
        ) : (
          <div
            className="relative shadow-lg border rounded-md bg-white transition-all duration-150 origin-top overflow-hidden m-auto shrink-0"
            style={{ width: `${zoom}%`, maxWidth: zoom <= 100 ? "100%" : "none" }}
          >
            {imgLoading && (
              <div className="absolute inset-0 flex items-center justify-center bg-muted/30 backdrop-blur-xs z-10 min-h-[300px]">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground/60" />
              </div>
            )}
            <img
              key={currentKey}
              ref={imgRef}
              src={imageUrl}
              alt=""
              className="w-full h-auto object-contain block select-none pointer-events-none"
              onLoad={() => {
                setLoadedKey(currentKey)
              }}
              onError={() => {
                setErrorKey(currentKey)
              }}
            />

            {/* Bounding Box Highlight Overlay */}
            {overlayStyle && !imgLoading && !imgError && (
              <div
                style={overlayStyle}
                className="absolute border-2 border-primary bg-primary/25 rounded shadow-[0_0_12px_rgba(var(--primary),0.6)] transition-all duration-200 pointer-events-none animate-pulse"
              >
                {activeEvidence?.text && (
                  <span className="absolute -top-6 left-0 bg-primary text-primary-foreground text-[10px] px-1.5 py-0.5 rounded font-mono shadow truncate max-w-xs font-semibold">
                    {activeEvidence.text}
                  </span>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Page Thumbnails Strip */}
      {pages.length > 1 && (
        <div className="flex items-center gap-2 p-2.5 border-t bg-muted/20 overflow-x-auto h-20 shrink-0">
          {pages.map((p) => {
            const thumbUrl = documentsApi.getPageImageUrl(documentId, p.page_number, 120)
            const isSelected = p.page_number === currentPage
            return (
              <button
                key={p.id}
                onClick={() => setCurrentPage(p.page_number)}
                className={`relative h-14 aspect-[3/4] rounded border overflow-hidden shrink-0 transition-all focus:outline-none flex items-center justify-center bg-muted/40 ${
                  isSelected
                    ? "ring-2 ring-primary border-primary shadow-sm"
                    : "border-border/60 opacity-70 hover:opacity-100 hover:border-foreground/30"
                }`}
              >
                <FileText className="h-4 w-4 text-muted-foreground/40 absolute pointer-events-none" />
                <img
                  src={thumbUrl}
                  alt=""
                  className="w-full h-full object-cover relative z-10"
                  loading="lazy"
                  onError={(e) => {
                    ;(e.target as HTMLElement).style.display = "none"
                  }}
                />
                <span className="absolute bottom-0.5 right-0.5 z-20 bg-background/90 backdrop-blur-xs text-[9px] px-1 py-0.2 rounded font-mono font-semibold text-foreground">
                  {p.page_number}
                </span>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
