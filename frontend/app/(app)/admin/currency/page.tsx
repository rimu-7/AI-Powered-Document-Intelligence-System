"use client"

import React, { useState } from "react"
import {
  Building2,
  FileSearch,
  GraduationCap,
  History,
  Printer,
  Scale,
  Sparkles,
} from "lucide-react"
import type { CurrencyCode } from "@/lib/api/types"
import { useCurrentUser } from "@/features/auth/hooks"
import {
  useCurrencySettings,
  useUpdateCurrencySettings,
} from "@/features/organization/hooks"
import { canAdmin } from "@/lib/permissions"
import { PageHeader } from "@/components/page-header"
import { ErrorState } from "@/components/error-state"
import {
  CurrencySelect,
  getCurrencyDisplayName,
} from "@/components/currency-select"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

const ASK = "__ask__"

type Draft = {
  default_currency: CurrencyCode | null
  symbol_rules: Record<string, CurrencyCode>
}

function sameRules(a: Record<string, string>, b: Record<string, string>) {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)])
  return [...keys].every((k) => a[k] === b[k])
}

const STEPS = [
  {
    icon: Printer,
    title: "Printed on the invoice",
    text: "An ISO code (USD) or a symbol with one meaning (€, £, ₹).",
  },
  {
    icon: FileSearch,
    title: "Clues on the document",
    text: "The supplier's country in its address, or a phone prefix, web domain or tax ID such as ABN or GSTIN.",
  },
  {
    icon: History,
    title: "Supplier history",
    text: "The currency of this supplier's earlier invoices.",
  },
  {
    icon: Scale,
    title: "Your symbol rules",
    text: "For example, '$' always means USD.",
  },
  {
    icon: GraduationCap,
    title: "Learned from reviewers",
    text: "A symbol your reviewers keep resolving the same way.",
  },
  {
    icon: Building2,
    title: "Default currency",
    text: "Used when nothing else decides, and never against a printed symbol.",
  },
]

export default function CurrencyRulesPage() {
  const { data: user } = useCurrentUser()
  const isAdmin = canAdmin(user?.role)
  const { data, isLoading, isError, error, refetch } = useCurrencySettings()
  const { mutate: save, isPending } = useUpdateCurrencySettings()

  // Unsaved edits; null means "showing what is saved".
  const [draft, setDraft] = useState<Draft | null>(null)
  const [applyToPending, setApplyToPending] = useState(true)

  const saved: Draft | null = data
    ? {
        default_currency: data.default_currency ?? null,
        symbol_rules: data.symbol_rules,
      }
    : null
  const current = draft ?? saved
  const defaultCurrency = current?.default_currency ?? null
  const rules = current?.symbol_rules ?? {}
  const dirty =
    !!draft &&
    !!saved &&
    (draft.default_currency !== saved.default_currency ||
      sameRules(draft.symbol_rules, saved.symbol_rules) === false)

  const edit = (patch: Partial<Draft>) =>
    setDraft({
      default_currency: defaultCurrency,
      symbol_rules: rules,
      ...patch,
    })

  const setDefaultCurrency = (code: CurrencyCode | null) =>
    edit({ default_currency: code })

  const setRule = (symbol: string, value: string) => {
    const next = { ...rules }
    if (value === ASK) delete next[symbol]
    else next[symbol] = value as CurrencyCode
    edit({ symbol_rules: next })
  }

  const handleSave = () =>
    save(
      {
        default_currency: defaultCurrency,
        symbol_rules: rules,
        apply_to_pending: applyToPending,
      },
      { onSuccess: () => setDraft(null) }
    )

  const pending = data?.pending_invoices ?? 0

  return (
    <div className="space-y-6">
      <PageHeader
        title="Currency Rules"
        description="How the currency is decided when an invoice does not print it clearly."
      >
        {isAdmin && (
          <Button onClick={handleSave} disabled={!dirty || isPending}>
            {isPending ? "Saving…" : "Save rules"}
          </Button>
        )}
      </PageHeader>

      {isError ? (
        <ErrorState
          message={(error as any)?.message || "Failed to load currency rules"}
          requestId={(error as any)?.requestId}
          onRetry={() => refetch()}
        />
      ) : isLoading || !data ? (
        <div className="grid gap-4 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-40 animate-pulse rounded-lg bg-muted" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <div className="min-w-0 space-y-6 lg:col-span-2">
            {pending > 0 && (
              <div className="flex items-start gap-3 rounded-lg border border-amber-500/30 bg-amber-500/5 p-4">
                <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
                <div className="flex-1 space-y-1 text-sm">
                  <p className="font-medium text-foreground">
                    {pending} {pending === 1 ? "invoice is" : "invoices are"}{" "}
                    waiting for a currency
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Add a rule or a default below. Saving resolves every waiting
                    invoice it applies to and revalidates it.
                  </p>
                </div>
                {isAdmin && !dirty && (
                  <Button
                    size="sm"
                    variant="outline"
                    className="shrink-0"
                    disabled={isPending}
                    onClick={handleSave}
                  >
                    Resolve waiting invoices
                  </Button>
                )}
              </div>
            )}

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Default currency</CardTitle>
                <CardDescription className="text-xs">
                  {
                    "For invoices that print no currency at all, and for ambiguous symbols the default can stand for: a USD default reads '$' as USD but never turns '$' into euros."
                  }
                </CardDescription>
              </CardHeader>
              <CardContent className="max-w-sm">
                <CurrencySelect
                  value={defaultCurrency}
                  onChange={setDefaultCurrency}
                  disabled={!isAdmin || isPending}
                  placeholder="No default: ask a reviewer"
                />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Ambiguous symbols</CardTitle>
                <CardDescription className="text-xs">
                  {
                    "Symbols shared by several currencies. A rule applies when the document itself and the supplier's history do not decide."
                  }
                </CardDescription>
              </CardHeader>
              <CardContent className="divide-y p-0">
                {data.symbols.map((s) => {
                  const value = rules[s.symbol] ?? ASK
                  return (
                    <div
                      key={s.symbol}
                      className="flex flex-col gap-3 px-6 py-4 sm:flex-row sm:items-center sm:justify-between"
                    >
                      <div className="flex min-w-0 items-center gap-4">
                        <span className="flex h-10 w-12 shrink-0 items-center justify-center rounded-md border bg-muted/40 font-mono text-lg font-semibold">
                          {s.symbol}
                        </span>
                        <div className="min-w-0 space-y-1">
                          <p className="truncate font-mono text-[11px] text-muted-foreground">
                            {s.candidates.join(" · ")}
                          </p>
                          {s.learned && !rules[s.symbol] && (
                            <p className="inline-flex items-center gap-1 rounded bg-sky-500/10 px-1.5 py-0.5 text-[10px] font-medium text-sky-700 dark:text-sky-400">
                              <GraduationCap className="h-3 w-3" />
                              Learned: {s.learned} from {s.learned_from}{" "}
                              reviewer decisions
                            </p>
                          )}
                        </div>
                      </div>
                      <Select
                        value={value}
                        onValueChange={(v) => setRule(s.symbol, String(v))}
                        disabled={!isAdmin || isPending}
                      >
                        <SelectTrigger
                          className="h-9 w-full text-xs sm:w-[230px]"
                          aria-label={`Rule for ${s.symbol}`}
                        >
                          <SelectValue>
                            {(v: string) =>
                              v === ASK
                                ? s.learned
                                  ? `Automatic (learned ${s.learned})`
                                  : "Decide per invoice"
                                : `${v} – ${getCurrencyDisplayName(v)}`
                            }
                          </SelectValue>
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value={ASK} className="text-xs">
                            {s.learned
                              ? `Automatic (learned ${s.learned})`
                              : "Decide per invoice"}
                          </SelectItem>
                          {s.candidates.map((code) => (
                            <SelectItem
                              key={code}
                              value={code}
                              className="text-xs"
                            >
                              <span className="font-mono font-medium">
                                {code}
                              </span>{" "}
                              – {getCurrencyDisplayName(code)}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  )
                })}
              </CardContent>
            </Card>

            {isAdmin ? (
              <label className="flex cursor-pointer items-center gap-2 text-sm text-muted-foreground">
                <Checkbox
                  checked={applyToPending}
                  onCheckedChange={(v) => setApplyToPending(v === true)}
                  disabled={isPending}
                />
                Also resolve invoices that are waiting for a currency
                {pending > 0 ? ` (${pending})` : ""}
              </label>
            ) : (
              <p className="text-xs text-muted-foreground">
                Only administrators can change currency rules.
              </p>
            )}
          </div>

          <Card className="h-fit">
            <CardHeader>
              <CardTitle className="text-base">How it is decided</CardTitle>
              <CardDescription className="text-xs">
                The first step with a clear answer wins. Each invoice shows
                which step decided and why.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ol className="space-y-4">
                {STEPS.map((step, i) => (
                  <li key={step.title} className="flex gap-3">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border bg-muted/40 text-muted-foreground">
                      <step.icon className="h-3.5 w-3.5" />
                    </span>
                    <div className="space-y-0.5">
                      <p className="text-xs font-medium text-foreground">
                        {i + 1}. {step.title}
                      </p>
                      <p className="text-[11px] leading-relaxed text-muted-foreground">
                        {step.text}
                      </p>
                    </div>
                  </li>
                ))}
              </ol>
              <p className="mt-5 border-t pt-4 text-[11px] leading-relaxed text-muted-foreground">
                Learning needs {data.learn_threshold} matching reviewer
                decisions and none that disagree. Automatic choices never block
                approval, and a reviewer can change any of them.
              </p>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}
