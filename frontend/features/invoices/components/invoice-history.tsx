import React from "react"
import { CheckCircle2, PencilLine, UserRound, XCircle } from "lucide-react"
import type { ReviewActionOut } from "@/features/invoices/api"
import { DateTime } from "@/components/date-time"
import { cn } from "@/lib/utils"

const ACTIONS: Record<
  ReviewActionOut["action_type"],
  { label: string; icon: React.ElementType; tone: string }
> = {
  CORRECTION: {
    label: "Corrected",
    icon: PencilLine,
    tone: "text-sky-600 dark:text-sky-400",
  },
  APPROVAL: {
    label: "Approved",
    icon: CheckCircle2,
    tone: "text-emerald-600 dark:text-emerald-400",
  },
  REJECTION: {
    label: "Rejected",
    icon: XCircle,
    tone: "text-red-600 dark:text-red-400",
  },
  ASSIGNMENT: {
    label: "Assigned",
    icon: UserRound,
    tone: "text-muted-foreground",
  },
}

/** "line_items[2].unit_price" -> "Line 3 · unit price" */
export function fieldLabel(path: string | null | undefined): string {
  if (!path) return ""
  const line = /^line_items\[(\d+)\]\.(.+)$/.exec(path)
  if (line) return `Line ${Number(line[1]) + 1} · ${line[2].replace(/_/g, " ")}`
  return path.replace(/_/g, " ")
}

function show(value: unknown): string {
  if (value === null || value === undefined || value === "") return "empty"
  if (typeof value === "object") return JSON.stringify(value)
  return String(value)
}

/** Everything reviewers did to this invoice, newest first. */
export function InvoiceHistory({ actions }: { actions: ReviewActionOut[] }) {
  if (actions.length === 0)
    return (
      <div className="py-8 text-center text-xs text-muted-foreground">
        No one has changed this invoice yet. Corrections, approvals and
        rejections appear here.
      </div>
    )

  const newestFirst = [...actions].reverse()
  return (
    <ol className="relative space-y-3 border-l pl-4">
      {newestFirst.map((a) => {
        const meta = ACTIONS[a.action_type] ?? ACTIONS.ASSIGNMENT
        const Icon = meta.icon
        return (
          <li key={a.id} className="relative">
            <span className="absolute top-0.5 -left-[23px] flex h-3.5 w-3.5 items-center justify-center rounded-full bg-background">
              <Icon className={cn("h-3.5 w-3.5", meta.tone)} aria-hidden />
            </span>
            <div className="space-y-1.5 rounded-lg border bg-card p-3 text-xs">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className={cn("font-semibold", meta.tone)}>
                  {meta.label}
                  {a.field_path && (
                    <span className="font-normal text-foreground">
                      {" "}
                      {fieldLabel(a.field_path)}
                    </span>
                  )}
                </span>
                <DateTime
                  value={a.created_at}
                  className="text-[11px] text-muted-foreground"
                />
              </div>
              {a.action_type === "CORRECTION" && (
                <p className="font-mono text-[11px] break-all">
                  <span className="text-muted-foreground line-through">
                    {show(a.old_value_json)}
                  </span>
                  <span className="px-1.5 text-muted-foreground">→</span>
                  <span className="font-medium">{show(a.new_value_json)}</span>
                </p>
              )}
              {a.reason && (
                <p className="text-muted-foreground">“{a.reason}”</p>
              )}
              <p className="text-[11px] text-muted-foreground">
                {a.reviewer_name ?? "Unknown reviewer"}
                {a.invoice_version != null && ` · version ${a.invoice_version}`}
              </p>
            </div>
          </li>
        )
      })}
    </ol>
  )
}
