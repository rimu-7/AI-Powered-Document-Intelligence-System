"use client"

import React, { useState, useMemo } from "react"
import { usePublicConfig } from "@/features/auth/hooks"
import type { CurrencyCode } from "@/lib/api/types"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command"
import { Check, ChevronsUpDown } from "lucide-react"

export const ALL_CURRENCY_CODES: CurrencyCode[] = [
  "USD",
  "EUR",
  "GBP",
  "JPY",
  "CNY",
  "CHF",
  "CAD",
  "AUD",
  "NZD",
  "SEK",
  "NOK",
  "DKK",
  "PLN",
  "CZK",
  "HUF",
  "INR",
  "BDT",
  "PKR",
  "LKR",
  "SGD",
  "HKD",
  "KRW",
  "TWD",
  "THB",
  "MYR",
  "IDR",
  "PHP",
  "VND",
  "AED",
  "SAR",
  "QAR",
  "BHD",
  "KWD",
  "OMR",
  "JOD",
  "TND",
  "ILS",
  "TRY",
  "ZAR",
  "NGN",
  "KES",
  "EGP",
  "MAD",
  "BRL",
  "MXN",
  "ARS",
  "CLP",
  "COP",
  "PEN",
  "RUB",
  "UAH",
  "RON",
  "BGN",
  "ISK",
  "CLF",
]

export function getCurrencyDisplayName(code: string, locale = "en-US"): string {
  try {
    const dn = new Intl.DisplayNames([locale], { type: "currency" })
    return dn.of(code) || code
  } catch {
    return code
  }
}

export interface CurrencySelectProps {
  value: CurrencyCode | null | undefined
  onChange: (value: CurrencyCode | null) => void
  candidates?: CurrencyCode[] | null
  disabled?: boolean
  placeholder?: string
  className?: string
  allowNull?: boolean
  id?: string
  "aria-invalid"?: boolean
}

export function CurrencySelect({
  value,
  onChange,
  candidates,
  disabled = false,
  placeholder = "Select currency...",
  className,
  allowNull = true,
  id,
  "aria-invalid": ariaInvalid,
}: CurrencySelectProps) {
  const [open, setOpen] = useState(false)
  const { data: config } = usePublicConfig()

  const currencyOptions = useMemo(() => {
    if (config?.currencies && config.currencies.length > 0) {
      return config.currencies.map((c) => c.code)
    }
    return ALL_CURRENCY_CODES
  }, [config])

  const sortedCurrencies = useMemo(() => {
    return [...currencyOptions].sort((a, b) => a.localeCompare(b))
  }, [currencyOptions])

  const validCandidates = useMemo(() => {
    if (!candidates || !Array.isArray(candidates)) return []
    const set = new Set(currencyOptions)
    return candidates.filter((c): c is CurrencyCode => set.has(c))
  }, [candidates, currencyOptions])

  const selectedLabel = useMemo(() => {
    if (!value) return null
    const name = getCurrencyDisplayName(value)
    return `${value} – ${name}`
  }, [value])

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={
          <Button
            id={id}
            variant="outline"
            role="combobox"
            aria-expanded={open}
            aria-invalid={ariaInvalid}
            disabled={disabled}
            className={cn(
              "h-9 w-full justify-between bg-transparent px-3 text-xs font-normal",
              !value && "text-muted-foreground",
              className
            )}
          />
        }
      >
        <span className="truncate">{selectedLabel ?? placeholder}</span>
        <ChevronsUpDown className="ml-2 h-3.5 w-3.5 shrink-0 opacity-50" />
      </PopoverTrigger>

      <PopoverContent className="w-[300px] p-0" align="start">
        <Command>
          <CommandInput
            placeholder="Search currency..."
            className="h-8 text-xs"
          />
          <CommandList className="max-h-60 overflow-y-auto">
            <CommandEmpty>No currency found.</CommandEmpty>

            {allowNull && (
              <CommandGroup heading="Options">
                <CommandItem
                  value="not-set none clear"
                  onSelect={() => {
                    onChange(null)
                    setOpen(false)
                  }}
                  className="text-xs"
                >
                  <Check
                    className={cn(
                      "mr-2 h-3.5 w-3.5",
                      !value ? "opacity-100" : "opacity-0"
                    )}
                  />
                  <span className="text-muted-foreground italic">Not set</span>
                </CommandItem>
              </CommandGroup>
            )}

            {validCandidates.length > 0 && (
              <>
                <CommandSeparator />
                <CommandGroup heading="Suggested">
                  {validCandidates.map((code) => {
                    const name = getCurrencyDisplayName(code)
                    const isSelected = value === code
                    return (
                      <CommandItem
                        key={`suggested-${code}`}
                        value={`suggested ${code} ${name}`}
                        onSelect={() => {
                          onChange(code)
                          setOpen(false)
                        }}
                        className="text-xs"
                      >
                        <Check
                          className={cn(
                            "mr-2 h-3.5 w-3.5",
                            isSelected ? "opacity-100" : "opacity-0"
                          )}
                        />
                        <span className="font-mono font-medium">{code}</span>
                        <span className="truncate text-muted-foreground">
                          – {name}
                        </span>
                      </CommandItem>
                    )
                  })}
                </CommandGroup>
              </>
            )}

            <CommandSeparator />
            <CommandGroup heading="All Currencies">
              {sortedCurrencies.map((code) => {
                const name = getCurrencyDisplayName(code)
                const isSelected = value === code
                return (
                  <CommandItem
                    key={code}
                    value={`${code} ${name}`}
                    onSelect={() => {
                      onChange(code)
                      setOpen(false)
                    }}
                    className="text-xs"
                  >
                    <Check
                      className={cn(
                        "mr-2 h-3.5 w-3.5",
                        isSelected ? "opacity-100" : "opacity-0"
                      )}
                    />
                    <span className="font-mono font-medium">{code}</span>
                    <span className="truncate text-muted-foreground">
                      – {name}
                    </span>
                  </CommandItem>
                )
              })}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
