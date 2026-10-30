"use client"

import React, { useState } from "react"
import Link from "next/link"
import { ChevronDown, ExternalLink, Loader2 } from "lucide-react"
import type { FindingOut } from "@/features/comparisons/api"
import { useComparisonFindings } from "@/features/comparisons/hooks"
import {
  fieldName,
  Kind,
  recordReason,
  Ref,
  refHref,
  showDifference,
  showValue,
  statusMeta,
  whereText,
} from "@/features/comparisons/labels"
import { cn } from "@/lib/utils"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"

export function FindingBadge({
  status,
  kind,
  className,
}: {
  status: FindingOut["status"]
  kind: Kind
  className?: string
}) {
  const meta = statusMeta(status, kind)
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <span
            className={cn(
              "inline-flex shrink-0 cursor-help items-center rounded-md border px-1.5 py-0.5 text-[11px] font-medium whitespace-nowrap",
              meta.tone,
              className
            )}
          />
        }
      >
        {meta.label}
      </TooltipTrigger>
      <TooltipContent>{meta.help}</TooltipContent>
    </Tooltip>
  )
}

function SideRef({ refData, fallback }: { refData?: Ref; fallback: string }) {
  const href = refHref(refData)
  const where = whereText(refData)
  // The side is already labelled with the file name on PDF comparisons.
  const name =
    refData?.filename && refData.filename !== fallback ? refData.filename : null
  const text = [name, where].filter(Boolean).join(" · ") || fallback
  if (!href) return <span className="truncate">{text}</span>
  return (
    <Link
      href={href}
      onClick={(e) => e.stopPropagation()}
      className="inline-flex min-w-0 items-center gap-1 truncate underline-offset-2 hover:text-foreground hover:underline"
    >
      <span className="truncate">{text}</span>
      <ExternalLink className="h-3 w-3 shrink-0" aria-hidden />
    </Link>
  )
}

/** One compared invoice: the headline, why it got its status, and its fields on demand. */
export function RecordCard({
  comparisonId,
  record,
  kind,
  sides,
}: {
  comparisonId: string
  record: FindingOut
  kind: Kind
  sides: { left: string; right: string }
}) {
  const [open, setOpen] = useState(false)
  const ev = (record.evidence_json ?? {}) as {
    left?: Ref
    right?: Ref
    right_candidates?: Ref[]
    first_occurrence?: Ref
  }
  const paired =
    record.left_value_json != null &&
    record.right_value_json != null &&
    !Array.isArray(record.right_value_json)
  const reason = recordReason(record.status, record.difference_json, kind)
  const candidates = ev.right_candidates ?? []
  const otherSupplier = record.status !== "AMBIGUOUS"
  const candidateNames: unknown[] = otherSupplier
    ? (((record.difference_json ?? {}) as { suppliers?: unknown[] })
        .suppliers ?? [])
    : Array.isArray(record.right_value_json)
      ? record.right_value_json
      : []

  const { data, isLoading } = useComparisonFindings(
    comparisonId,
    { record_position: record.position, limit: 200 },
    { ready: open && paired }
  )
  const fields = data?.items ?? []

  return (
    <div
      className={cn(
        "rounded-lg border bg-card transition-colors",
        open && "border-primary/30"
      )}
    >
      <button
        type="button"
        onClick={() => paired && setOpen((o) => !o)}
        aria-expanded={paired ? open : undefined}
        className={cn(
          "flex w-full items-start gap-3 p-3.5 text-left",
          paired ? "cursor-pointer hover:bg-muted/30" : "cursor-default"
        )}
      >
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <FindingBadge status={record.status} kind={kind} />
            <span className="truncate font-mono text-xs font-semibold text-foreground">
              {showValue(record.left_value_json ?? record.right_value_json)}
            </span>
          </div>
          {reason && <p className="text-xs text-muted-foreground">{reason}</p>}
          <div className="grid grid-cols-1 gap-x-4 gap-y-0.5 text-[11px] text-muted-foreground sm:grid-cols-2">
            {ev.left && (
              <span className="flex min-w-0 gap-1">
                <span className="shrink-0 font-medium">{sides.left}:</span>
                <SideRef refData={ev.left} fallback={sides.left} />
              </span>
            )}
            {ev.right && (
              <span className="flex min-w-0 gap-1">
                <span className="shrink-0 font-medium">{sides.right}:</span>
                <SideRef refData={ev.right} fallback={sides.right} />
              </span>
            )}
            {ev.first_occurrence && (
              <span className="flex min-w-0 gap-1">
                <span className="shrink-0 font-medium">First seen:</span>
                <SideRef refData={ev.first_occurrence} fallback={sides.right} />
              </span>
            )}
          </div>
          {candidates.length > 0 && (
            <div className="space-y-0.5 pt-0.5 text-[11px] text-muted-foreground">
              <p className="font-medium">
                {otherSupplier
                  ? `Same number in ${sides.right}, other supplier:`
                  : `Possible matches in ${sides.right}:`}
              </p>
              <ul className="space-y-0.5 pl-3">
                {candidates.map((c, i) => (
                  <li key={i} className="flex min-w-0 gap-1">
                    <span className="shrink-0">
                      {showValue(candidateNames[i])}
                    </span>
                    <span className="shrink-0">—</span>
                    <SideRef refData={c} fallback={sides.right} />
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
        {paired && (
          <ChevronDown
            className={cn(
              "mt-0.5 h-4 w-4 shrink-0 text-muted-foreground transition-transform",
              open && "rotate-180"
            )}
            aria-hidden
          />
        )}
      </button>

      {open && paired && (
        <div className="border-t px-3.5 pt-2 pb-3.5">
          {isLoading ? (
            <div className="flex items-center gap-2 py-3 text-xs text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading fields…
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[520px] text-xs">
                <thead>
                  <tr className="text-left text-[11px] text-muted-foreground">
                    <th className="py-1.5 pr-3 font-medium">Field</th>
                    <th className="py-1.5 pr-3 font-medium">{sides.left}</th>
                    <th className="py-1.5 pr-3 font-medium">{sides.right}</th>
                    <th className="py-1.5 font-medium">Result</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {fields.map((f) => {
                    const diff = showDifference(f.difference_json)
                    const fev = (f.evidence_json ?? {}) as {
                      left?: Ref
                      right?: Ref
                    }
                    const bad = f.status === "MISMATCH"
                    return (
                      <tr
                        key={f.id}
                        className={cn(bad && "bg-rose-500/[0.04]")}
                      >
                        <td className="py-2 pr-3 align-top font-medium whitespace-nowrap">
                          {fieldName(f.field_name)}
                        </td>
                        <td className="py-2 pr-3 align-top">
                          <span className="font-mono break-words">
                            {showValue(f.left_value_json)}
                          </span>
                          {whereText(
                            fev.left?.field ? fev.left : undefined
                          ) && (
                            <span className="block text-[10px] text-muted-foreground">
                              {whereText(fev.left)}
                            </span>
                          )}
                        </td>
                        <td className="py-2 pr-3 align-top">
                          <span
                            className={cn(
                              "font-mono break-words",
                              bad &&
                                "font-semibold text-rose-700 dark:text-rose-400"
                            )}
                          >
                            {showValue(f.right_value_json)}
                          </span>
                          {whereText(
                            fev.right?.field ? fev.right : undefined
                          ) && (
                            <span className="block text-[10px] text-muted-foreground">
                              {whereText(fev.right)}
                            </span>
                          )}
                        </td>
                        <td className="py-2 align-top">
                          <div className="flex flex-col items-start gap-0.5">
                            <FindingBadge status={f.status} kind={kind} />
                            {diff && (
                              <span className="font-mono text-[10px] text-muted-foreground">
                                {diff}
                              </span>
                            )}
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
