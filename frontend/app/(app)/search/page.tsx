"use client"

import React, { Suspense, useState, useEffect } from "react"
import { useQueryState, parseAsString, parseAsInteger } from "nuqs"
import { PageHeader } from "@/components/page-header"
import { useSearch } from "@/features/search/hooks"
import { CurrencySelect } from "@/components/currency-select"
import type { CurrencyCode } from "@/lib/api/types"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Card, CardContent } from "@/components/ui/card"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/error-state"
import { RenderSnippet } from "@/components/render-snippet"
import { Search as SearchIcon, FileText, ExternalLink } from "lucide-react"
import Link from "next/link"

function SearchContent() {
  const [mode, setMode] = useQueryState(
    "mode",
    parseAsString.withDefault("keyword")
  )
  const [urlQuery, setUrlQuery] = useQueryState(
    "q",
    parseAsString.withDefault("")
  )
  const [page, setPage] = useQueryState("page", parseAsInteger.withDefault(1))
  const [currencyFilter, setCurrencyFilter] = useState<
    CurrencyCode | undefined
  >(undefined)

  const [inputValue, setInputValue] = useState(urlQuery)

  // 300ms debounce input -> urlQuery
  useEffect(() => {
    const timer = setTimeout(() => {
      setUrlQuery(inputValue || null)
      setPage(1)
    }, 300)
    return () => clearTimeout(timer)
  }, [inputValue, setUrlQuery, setPage])

  const limit = 20
  const offset = (page - 1) * limit

  const filters = currencyFilter ? { currency: currencyFilter } : undefined

  const { data, isLoading, isError, error, refetch } = useSearch(
    mode as "keyword" | "semantic" | "hybrid",
    urlQuery,
    filters,
    limit,
    offset
  )

  const hits = data?.items ?? []
  const total = data?.total ?? 0

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageHeader
        title="Search Documents"
        description="Search across extracted invoice fields, line items, and raw page OCR text."
      />

      {/* Search Input & Mode Switch */}
      <div className="space-y-3">
        <div className="relative">
          <SearchIcon className="absolute top-3 left-3 h-5 w-5 text-muted-foreground" />
          <Input
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder="Search keywords, supplier names, invoice numbers, items..."
            className="h-11 pl-11 text-sm shadow-sm"
            autoFocus
          />
        </div>

        <div className="flex flex-col justify-between gap-2.5 sm:flex-row sm:items-center">
          <Tabs value={mode} onValueChange={(val) => setMode(val as any)}>
            <TabsList className="h-auto flex-wrap gap-1 bg-muted p-1">
              <TabsTrigger value="keyword" className="text-xs">
                Keyword (Full-Text)
              </TabsTrigger>
              <TabsTrigger value="semantic" className="text-xs">
                Semantic (pgvector)
              </TabsTrigger>
              <TabsTrigger value="hybrid" className="text-xs">
                Hybrid (RRF)
              </TabsTrigger>
            </TabsList>
          </Tabs>

          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5">
              <span className="text-xs whitespace-nowrap text-muted-foreground">
                Currency:
              </span>
              <div className="w-36">
                <CurrencySelect
                  value={currencyFilter ?? null}
                  onChange={(c) => {
                    setCurrencyFilter(c || undefined)
                    setPage(1)
                  }}
                  placeholder="All currencies"
                  allowNull
                />
              </div>
            </div>

            {urlQuery && (
              <span className="self-start font-mono text-xs text-muted-foreground sm:self-auto">
                {total} match{total === 1 ? "" : "es"}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Results List */}
      {!urlQuery ? (
        <EmptyState
          icon={SearchIcon}
          title="Start searching"
          description="Type a search query above to find relevant documents, text snippets, and invoices."
        />
      ) : isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-24 animate-pulse rounded-lg bg-muted" />
          ))}
        </div>
      ) : isError ? (
        <ErrorState
          message={(error as any)?.message || "Search failed"}
          requestId={(error as any)?.requestId}
          onRetry={() => refetch()}
        />
      ) : hits.length === 0 ? (
        <EmptyState
          title="No results found"
          description={`No matching documents found for "${urlQuery}" using ${mode} search.`}
        />
      ) : (
        <div className="space-y-3">
          {hits.map((hit, idx) => (
            <Card
              key={idx}
              className="transition-colors hover:border-primary/50"
            >
              <CardContent className="space-y-2 p-4">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                    <Link
                      href={`/documents/${hit.document_id}`}
                      className="truncate text-sm font-medium transition-colors hover:text-primary"
                    >
                      {hit.filename}
                    </Link>
                    <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground uppercase">
                      {hit.document_type}
                    </span>
                  </div>

                  <div className="flex shrink-0 items-center gap-2">
                    <span className="font-mono text-[11px] text-muted-foreground">
                      {hit.score_kind}: {hit.score.toFixed(4)}
                    </span>
                    <Link href={`/documents/${hit.document_id}`}>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-muted-foreground hover:text-foreground"
                      >
                        <ExternalLink className="h-3.5 w-3.5" />
                      </Button>
                    </Link>
                  </div>
                </div>

                <div className="rounded border border-border/50 bg-muted/40 p-2.5">
                  <RenderSnippet text={hit.snippet} />
                </div>

                {hit.matched_pages && hit.matched_pages.length > 0 && (
                  <div className="flex items-center gap-1.5 font-mono text-[11px] text-muted-foreground">
                    <span>Matched pages:</span>
                    {hit.matched_pages.map((p) => (
                      <Link
                        key={p}
                        href={`/documents/${hit.document_id}?tab=text&page=${p}`}
                        className="underline hover:text-primary"
                      >
                        P.{p}
                      </Link>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

export default function SearchPage() {
  return (
    <Suspense
      fallback={<div className="h-96 animate-pulse rounded-lg bg-card" />}
    >
      <SearchContent />
    </Suspense>
  )
}
