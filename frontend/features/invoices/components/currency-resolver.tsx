"use client"

import React, { useState } from "react"
import Link from "next/link"
import { Check, Loader2, Sparkles } from "lucide-react"
import type { CurrencyCode } from "@/lib/api/types"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  CurrencySelect,
  getCurrencyDisplayName,
} from "@/components/currency-select"
import { useCorrectInvoice } from "@/features/invoices/hooks"
import {
  useCurrencySettings,
  useUpdateCurrencySettings,
} from "@/features/organization/hooks"

export interface CurrencyResolverProps {
  invoiceId: string
  version: number
  /** The symbol printed on the invoice ("$", "kr"), or null when none is printed. */
  printed: string | null
  suggestions: CurrencyCode[]
  isAdmin: boolean
  onConflict?: () => void
}

/**
 * One-click confirmation for an invoice whose currency could not be decided
 * automatically. Admins can turn the choice into an organization rule so the
 * same question is never asked again (and waiting invoices are resolved too).
 */
export function CurrencyResolver({
  invoiceId,
  version,
  printed,
  suggestions,
  isAdmin,
  onConflict,
}: CurrencyResolverProps) {
  const symbol = printed?.trim() || null
  const { data: settings } = useCurrencySettings()
  const { mutateAsync: correct, isPending: isCorrecting } = useCorrectInvoice()
  const { mutateAsync: saveSettings, isPending: isSaving } =
    useUpdateCurrencySettings()
  const [remember, setRemember] = useState(true)
  const [other, setOther] = useState<CurrencyCode | null>(null)
  const [chosen, setChosen] = useState<CurrencyCode | null>(null)
  const busy = isCorrecting || isSaving

  const quick = suggestions.slice(0, 4)
  const top = quick[0] ?? null
  const othersWaiting = Math.max((settings?.pending_invoices ?? 1) - 1, 0)
  // A rule for a symbol may only pick one of that symbol's currencies.
  const canRemember = isAdmin && (!symbol || suggestions.length > 0)
  const ruleAllowed = (code: CurrencyCode) =>
    !symbol || suggestions.includes(code)

  const rememberLabel = (() => {
    const code = chosen ?? other ?? top
    const target = code ? ` as ${code}` : ""
    const tail =
      othersWaiting > 0
        ? ` and resolve ${othersWaiting} other waiting ${othersWaiting === 1 ? "invoice" : "invoices"}`
        : ""
    return symbol
      ? `Always read '${symbol}'${target}${tail}`
      : `Use ${code ?? "this currency"} as the default when none is printed${tail}`
  })()

  const confirm = async (code: CurrencyCode) => {
    setChosen(code)
    try {
      await correct({
        id: invoiceId,
        payload: {
          expected_version: version,
          reason: symbol
            ? `Currency '${symbol}' confirmed as ${code}`
            : `Currency confirmed as ${code}`,
          changes: [{ field_path: "currency", value: code }],
        },
      })
    } catch (err: any) {
      setChosen(null)
      if (err?.status === 409 && err?.code === "VERSION_CONFLICT")
        onConflict?.()
      return
    }
    if (canRemember && remember && settings && ruleAllowed(code)) {
      await saveSettings({
        default_currency: symbol ? settings.default_currency : code,
        symbol_rules: symbol
          ? { ...settings.symbol_rules, [symbol]: code }
          : settings.symbol_rules,
        apply_to_pending: true,
      }).catch(() => undefined)
    }
  }

  return (
    <div
      className="mx-3 mb-2 rounded-md border border-amber-500/30 bg-amber-500/5 p-3"
      onClick={(e) => e.stopPropagation()}
    >
      <p className="text-xs font-medium text-foreground">
        {symbol
          ? `'${symbol}' is used by several currencies. Which one is this?`
          : "No currency is printed on this invoice. Which one is it?"}
      </p>

      {quick.length > 0 && (
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          {quick.map((code, i) => (
            <Button
              key={code}
              type="button"
              size="sm"
              variant={i === 0 ? "default" : "outline"}
              disabled={busy}
              onClick={() => confirm(code)}
              className="h-7 gap-1.5 px-2.5 text-xs"
              title={getCurrencyDisplayName(code)}
              aria-label={i === 0 ? `${code} (most likely)` : code}
            >
              {chosen === code && busy ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : i === 0 ? (
                <Sparkles className="h-3 w-3" aria-hidden />
              ) : null}
              <span className="font-mono font-semibold">{code}</span>
              {i === 0 && (
                <span className="font-normal opacity-80">most likely</span>
              )}
            </Button>
          ))}
        </div>
      )}

      <div className="mt-2 flex items-center gap-2">
        <div className="min-w-0 flex-1">
          <CurrencySelect
            value={other}
            onChange={setOther}
            candidates={suggestions}
            allowNull={false}
            disabled={busy}
            placeholder={
              quick.length ? "Another currency…" : "Choose currency…"
            }
          />
        </div>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          className="h-9 gap-1 text-xs"
          disabled={!other || busy}
          onClick={() => other && confirm(other)}
        >
          {chosen === other && busy ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : (
            <Check className="h-3 w-3" />
          )}
          Confirm
        </Button>
      </div>

      {canRemember ? (
        <label
          className={cn(
            "mt-3 flex cursor-pointer items-start gap-2 text-[11px] text-muted-foreground",
            busy && "opacity-60"
          )}
        >
          <Checkbox
            checked={remember}
            onCheckedChange={(v) => setRemember(v === true)}
            disabled={busy}
            className="mt-px"
          />
          <span>
            {rememberLabel}.{" "}
            <Link
              href="/admin/currency"
              className="underline underline-offset-2 hover:text-foreground"
            >
              Currency rules
            </Link>
          </span>
        </label>
      ) : (
        <p className="mt-3 text-[11px] text-muted-foreground">
          {symbol && suggestions.length > 0
            ? `Once reviewers confirm '${symbol}' the same way ${settings?.learn_threshold ?? 2} times, it is resolved automatically.`
            : "An administrator can set a default currency for invoices like this."}
        </p>
      )}
    </div>
  )
}
