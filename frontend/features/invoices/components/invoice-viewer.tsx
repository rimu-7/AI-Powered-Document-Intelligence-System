"use client"

import React, { useState, useRef, useEffect } from "react"
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
  /** The page to show (controlled by the parent so other panels can follow it). */
  page: number
  onPageChange: (page: number) => void
  activeEvidence?: EvidenceBox | null
  /** Shown in the toolbar, e.g. which invoice the current page belongs to. */
  pageLabel?: React.ReactNode
}

// The pages endpoint returns at most 200 rows per request.
const PAGE_CHUNK = 200
const ZOOM_KEY = "docintel.viewer.zoom"

function readZoom(): number {
  try {
    const v = Number(window.sessionStorage.getItem(ZOOM_KEY))
    return v >= 50 && v <= 250 ? v : 100
  } catch {
    return 100
  }
}

export function InvoiceViewer({
  documentId,
  page,
  onPageChange,
  activeEvidence,
  pageLabel,
}: InvoiceViewerProps) {
  // Metadata (size) of the current page; the total comes with any chunk.
  const chunkOffset =
    Math.floor((Math.max(page, 1) - 1) / PAGE_CHUNK) * PAGE_CHUNK
  const { data: pagesData, isLoading } = useDocumentPages(documentId, {
    limit: PAGE_CHUNK,
    offset: chunkOffset,
  })
  const pages = pagesData?.items ?? []
  const totalPages = pagesData?.total || 1

  const [zoom, setZoomState] = useState<number>(readZoom)
  const setZoom = (updater: (z: number) => number) =>
    setZoomState((z) => {
      const next = updater(z)
      try {
        window.sessionStorage.setItem(ZOOM_KEY, String(next))
      } catch {
        // storage unavailable: zoom just isn't remembered
      }
      return next
    })
  const [imgRetryCount, setImgRetryCount] = useState<number>(0)
  const imgRef = useRef<HTMLImageElement>(null)
  const thumbsRef = useRef<HTMLDivElement>(null)

  const currentPage = Math.min(Math.max(page, 1), totalPages)
  const goTo = (n: number) => {
    const next = Math.min(Math.max(n, 1), totalPages)
    if (next !== currentPage) onPageChange(next)
  }

  // Keep the selected thumbnail visible when the page changes from elsewhere.
  useEffect(() => {
    const el = thumbsRef.current?.querySelector<HTMLElement>(
      `[data-page="${currentPage}"]`
    )
    el?.scrollIntoView({ block: "nearest", inline: "center" })
  }, [currentPage])

  const currentKey = `${documentId}:${currentPage}:${imgRetryCount}`
  const [loadedKey, setLoadedKey] = useState<string | null>(null)
  const [errorKey, setErrorKey] = useState<string | null>(null)

  const isRetrying = imgRetryCount < 3 && errorKey === currentKey
  const imgLoading =
    (loadedKey !== currentKey && errorKey !== currentKey) || isRetrying
  const imgError = errorKey === currentKey && !isRetrying

  // Auto-retry transient load errors (e.g. while document processing finishes)
  useEffect(() => {
    let timeout: NodeJS.Timeout
    if (errorKey === currentKey && imgRetryCount < 3) {
      timeout = setTimeout(() => {
        setErrorKey(null)
        setImgRetryCount((c) => c + 1)
      }, 1500)
    }
    return () => clearTimeout(timeout)
  }, [errorKey, currentKey, imgRetryCount])

  const currentPageMeta = pages.find((p) => p.page_number === currentPage)
  const pageWidth = currentPageMeta?.page_width || 612
  const pageHeight = currentPageMeta?.page_height || 792

  const baseImageUrl = documentsApi.getPageImageUrl(
    documentId,
    currentPage,
    1200
  )
  const imageUrl =
    imgRetryCount > 0 ? `${baseImageUrl}&r=${imgRetryCount}` : baseImageUrl

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
    <div className="flex h-full flex-col overflow-hidden rounded-lg border bg-card">
      {/* Top Viewer Controls */}
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b bg-muted/40 px-2.5 py-1.5 text-xs sm:px-3 sm:py-2">
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => goTo(currentPage - 1)}
            aria-label="Previous page"
            disabled={currentPage <= 1}
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="px-1 font-mono text-xs select-none">
            {currentPage} / {totalPages}
          </span>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => goTo(currentPage + 1)}
            aria-label="Next page"
            disabled={currentPage >= totalPages}
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>

        {activeEvidence?.sheet ? (
          <div className="max-w-[200px] truncate rounded bg-muted px-2 py-0.5 font-mono text-[11px] text-muted-foreground">
            {activeEvidence.sheet} | R{activeEvidence.row}
          </div>
        ) : (
          pageLabel && (
            <div className="flex min-w-0 items-center text-[11px]">
              {pageLabel}
            </div>
          )
        )}

        <div className="flex items-center gap-0.5 sm:gap-1">
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
            onClick={() => setZoom(() => 100)}
            className="w-9 rounded py-0.5 text-center font-mono text-[11px] transition-colors hover:bg-muted sm:w-10"
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
              onClick={() => setZoom(() => 100)}
              title="Reset zoom"
            >
              <RotateCcw className="h-3 w-3" />
            </Button>
          )}
        </div>
      </div>

      {/* Viewer Main Stage */}
      <div className="relative flex flex-1 items-start justify-center overflow-auto bg-zinc-950/10 p-4 dark:bg-zinc-950/50">
        {isLoading ? (
          <div className="m-auto h-96 w-72 animate-pulse rounded-md bg-muted/60" />
        ) : imgError ? (
          <div className="m-auto flex max-w-sm flex-col items-center justify-center rounded-lg border border-dashed border-border/80 bg-background/50 p-8 text-center">
            <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-rose-500/10 text-rose-500">
              <AlertCircle className="h-5 w-5" />
            </div>
            <p className="text-sm font-medium">
              Unable to load page {currentPage}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              The page image could not be rendered from document storage.
            </p>
            <Button
              variant="outline"
              size="sm"
              className="mt-4 gap-1.5 text-xs"
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
            className="relative m-auto shrink-0 origin-top overflow-hidden rounded-md border bg-white shadow-lg transition-all duration-150"
            style={{
              width: `${zoom}%`,
              maxWidth: zoom <= 100 ? "100%" : "none",
            }}
          >
            {imgLoading && (
              <div className="absolute inset-0 z-10 flex min-h-[300px] items-center justify-center bg-muted/30 backdrop-blur-xs">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground/60" />
              </div>
            )}
            <img
              key={currentKey}
              ref={imgRef}
              src={imageUrl}
              alt=""
              className="pointer-events-none block h-auto w-full object-contain select-none"
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
                className="pointer-events-none absolute animate-pulse rounded border-2 border-primary bg-primary/25 shadow-[0_0_12px_rgba(var(--primary),0.6)] transition-all duration-200"
              >
                {activeEvidence?.text && (
                  <span className="absolute -top-6 left-0 max-w-xs truncate rounded bg-primary px-1.5 py-0.5 font-mono text-[10px] font-semibold text-primary-foreground shadow">
                    {activeEvidence.text}
                  </span>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Page Thumbnails Strip */}
      {totalPages > 1 && (
        <div
          ref={thumbsRef}
          className="flex h-16 shrink-0 items-center gap-2 overflow-x-auto border-t bg-muted/20 p-2 sm:h-20 sm:p-2.5"
        >
          {Array.from({ length: totalPages }, (_, i) => i + 1).map((n) => {
            const isSelected = n === currentPage
            return (
              <button
                key={n}
                type="button"
                data-page={n}
                onClick={() => goTo(n)}
                aria-label={`Page ${n}`}
                aria-current={isSelected ? "page" : undefined}
                className={`relative flex aspect-[3/4] h-12 shrink-0 items-center justify-center overflow-hidden rounded-md border bg-muted/40 transition-all focus:outline-none sm:h-14 ${
                  isSelected
                    ? "border-primary shadow-xs ring-2 ring-primary"
                    : "border-border/60 opacity-70 hover:border-foreground/30 hover:opacity-100"
                }`}
              >
                <FileText className="pointer-events-none absolute h-4 w-4 text-muted-foreground/40" />
                <img
                  src={documentsApi.getPageImageUrl(documentId, n, 240)}
                  alt=""
                  className="relative z-10 h-full w-full object-cover"
                  loading="lazy"
                  onError={(e) => {
                    ;(e.target as HTMLElement).style.display = "none"
                  }}
                />
                <span className="py-0.2 absolute right-0.5 bottom-0.5 z-20 rounded bg-background/90 px-1 font-mono text-[9px] font-semibold text-foreground shadow-xs backdrop-blur-xs">
                  {n}
                </span>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
