import React from "react"
import { describe, it, expect, vi } from "vitest"
import { screen, fireEvent, waitFor } from "@testing-library/react"
import { http, HttpResponse } from "msw"
import { server } from "../msw/server"
import { renderWithProviders } from "../utils"
import { mockInvoice } from "../msw/handlers"
import InvoiceReviewPage from "@/app/(app)/invoices/[id]/page"
import CurrencyRulesPage from "@/app/(app)/admin/currency/page"
import { CurrencySourceBadge } from "@/components/currency-source-badge"

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/admin/currency",
}))

const dollarInvoice = {
  ...mockInvoice,
  currency: null,
  currency_raw: "$",
  currency_source: null,
  currency_suggestions: ["USD", "CAD", "AUD", "NZD", "SGD"],
}

function serveInvoice(invoice: Record<string, unknown>) {
  server.use(
    http.get("*/bff/api/v1/invoices/:id", () => HttpResponse.json(invoice))
  )
}

describe("CurrencySourceBadge", () => {
  it("labels automatic decisions and stays quiet for human ones", () => {
    const { rerender } = renderWithProviders(
      <CurrencySourceBadge source="ORGANIZATION_RULE" reason="rule" />
    )
    expect(screen.getByText("auto · rule")).toBeInTheDocument()
    rerender(<CurrencySourceBadge source="PRINTED" />)
    expect(screen.getByText("printed")).toBeInTheDocument()
    rerender(<CurrencySourceBadge source="HUMAN" />)
    expect(screen.queryByText(/auto|printed/)).not.toBeInTheDocument()
  })
})

describe("Currency resolution on the review page", () => {
  it("shows how an automatic currency was decided", async () => {
    serveInvoice({
      ...mockInvoice,
      currency: "USD",
      currency_raw: "$",
      currency_source: "SUPPLIER_HISTORY",
      currency_reason:
        "'$' read as USD: 3 earlier invoices from this supplier used USD",
    })
    renderWithProviders(<InvoiceReviewPage params={{ id: "inv-001" }} />)
    expect(await screen.findByText("auto · supplier")).toBeInTheDocument()
    expect(screen.queryByText(/needs confirmation/)).not.toBeInTheDocument()
  })

  it("confirms the most likely currency in one click and saves a rule", async () => {
    serveInvoice(dollarInvoice)
    let correction: any = null
    let settings: any = null
    server.use(
      http.patch(
        "*/bff/api/v1/invoices/:id/corrections",
        async ({ request }) => {
          correction = await request.json()
          return HttpResponse.json({
            invoice: { ...dollarInvoice, currency: "USD", version: 2 },
            revalidation_job_id: "job-1",
            comparisons_marked_stale: 0,
          })
        }
      ),
      http.put(
        "*/bff/api/v1/organization/currency-settings",
        async ({ request }) => {
          settings = await request.json()
          return HttpResponse.json({ ...settings, resolved_invoices: 2 })
        }
      )
    )

    renderWithProviders(<InvoiceReviewPage params={{ id: "inv-001" }} />)
    expect(
      await screen.findByText(/'\$' is used by several currencies/)
    ).toBeInTheDocument()
    expect(
      await screen.findByText(
        /Always read '\$' as USD and resolve 2 other waiting invoices/
      )
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "USD (most likely)" }))

    await waitFor(() => expect(settings).not.toBeNull())
    expect(correction.changes).toEqual([
      { field_path: "currency", value: "USD" },
    ])
    expect(correction.expected_version).toBe(1)
    expect(settings).toMatchObject({
      symbol_rules: { $: "USD" },
      apply_to_pending: true,
    })
  })

  it("only corrects this invoice when the rule is unticked", async () => {
    serveInvoice(dollarInvoice)
    let correction: any = null
    const settingsSpy = vi.fn()
    server.use(
      http.patch(
        "*/bff/api/v1/invoices/:id/corrections",
        async ({ request }) => {
          correction = await request.json()
          return HttpResponse.json({
            invoice: { ...dollarInvoice, currency: "CAD", version: 2 },
            revalidation_job_id: "job-2",
            comparisons_marked_stale: 0,
          })
        }
      ),
      http.put("*/bff/api/v1/organization/currency-settings", () => {
        settingsSpy()
        return HttpResponse.json({})
      })
    )

    renderWithProviders(<InvoiceReviewPage params={{ id: "inv-001" }} />)
    await screen.findByText(/Always read/)
    fireEvent.click(screen.getByRole("checkbox", { checked: true }))
    fireEvent.click(screen.getByRole("button", { name: /^CAD$/ }))

    await waitFor(() => expect(correction).not.toBeNull())
    expect(correction.changes[0].value).toBe("CAD")
    expect(settingsSpy).not.toHaveBeenCalled()
  })
})

describe("Currency rules page", () => {
  it("shows waiting invoices, symbols and what was learned", async () => {
    renderWithProviders(<CurrencyRulesPage />)
    expect(
      await screen.findByText(/3 invoices are waiting for a currency/)
    ).toBeInTheDocument()
    expect(
      screen.getByText("Learned: SEK from 3 reviewer decisions")
    ).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Save rules" })).toBeDisabled()
  })
})
