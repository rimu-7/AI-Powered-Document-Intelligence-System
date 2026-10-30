import React from "react"
import { describe, it, expect, vi, beforeEach } from "vitest"
import { screen, fireEvent, waitFor } from "@testing-library/react"
import { http, HttpResponse } from "msw"
import { server } from "../msw/server"
import { renderWithProviders } from "../utils"
import { mockInvoice } from "../msw/handlers"
import InvoiceReviewPage from "@/app/(app)/invoices/[id]/page"
import { ProcessingPanel } from "@/features/jobs/components/processing-panel"

const replace = vi.fn()
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace, back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}))

// One document, three pages, one invoice per page.
const invoices = [1, 2, 3].map((n) => ({
  ...mockInvoice,
  id: `inv-00${n}`,
  invoice_number: `INV-00${n}`,
  segment_index: n - 1,
  page_start: n,
  page_end: n,
}))

beforeEach(() => {
  replace.mockClear()
  server.use(
    http.get("*/bff/api/v1/invoices/:id", ({ params }) =>
      HttpResponse.json(invoices.find((i) => i.id === params.id) ?? invoices[0])
    ),
    http.get("*/bff/api/v1/documents/:id/invoices", () =>
      // Out of order on purpose: the page sorts by page.
      HttpResponse.json([invoices[2], invoices[0], invoices[1]])
    ),
    http.get("*/bff/api/v1/documents/:id/pages", () =>
      HttpResponse.json({
        items: [1, 2, 3].map((n) => ({
          id: `p${n}`,
          document_id: "doc-001",
          page_number: n,
          page_width: 612,
          page_height: 792,
        })),
        total: 3,
        limit: 200,
        offset: 0,
      })
    )
  )
})

describe("Viewer and invoice panel stay in sync", () => {
  it("opens the invoice printed on the page chosen in the viewer", async () => {
    renderWithProviders(<InvoiceReviewPage params={{ id: "inv-001" }} />)
    expect(await screen.findByText("Invoice: INV-001")).toBeInTheDocument()
    expect(await screen.findByText("1 / 3")).toBeInTheDocument() // invoice 1 of 3

    fireEvent.click(await screen.findByRole("button", { name: "Page 3" }))
    expect(replace).toHaveBeenCalledWith("/invoices/inv-003?page=3", {
      scroll: false,
    })

    fireEvent.click(screen.getByRole("button", { name: "Previous page" }))
    expect(replace).toHaveBeenLastCalledWith("/invoices/inv-002?page=2", {
      scroll: false,
    })
  })

  it("steps through the document's invoices from the header", async () => {
    renderWithProviders(<InvoiceReviewPage params={{ id: "inv-002" }} />)
    expect(await screen.findByText("Invoice: INV-002")).toBeInTheDocument()
    fireEvent.click(
      await screen.findByRole("button", {
        name: "Next invoice in this document",
      })
    )
    expect(replace).toHaveBeenCalledWith("/invoices/inv-003?page=3", {
      scroll: false,
    })
    fireEvent.click(
      screen.getByRole("button", { name: "Previous invoice in this document" })
    )
    expect(replace).toHaveBeenLastCalledWith("/invoices/inv-001?page=1", {
      scroll: false,
    })
  })

  it("does not switch away from unsaved edits", async () => {
    renderWithProviders(<InvoiceReviewPage params={{ id: "inv-001" }} />)
    expect(await screen.findByText("Invoice: INV-001")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: /Edit/i }))
    fireEvent.click(await screen.findByRole("button", { name: "Page 2" }))
    expect(replace).not.toHaveBeenCalled()
    expect(
      screen.getByText(/Page of invoice INV-002 \(finish editing to switch\)/)
    ).toBeInTheDocument()
  })
})

describe("ProcessingPanel", () => {
  it("shows live progress, then the outcome", async () => {
    server.use(
      http.get("*/bff/api/v1/jobs/active", () =>
        HttpResponse.json([
          {
            job_id: "j1",
            document_id: "d1",
            filename: "march-invoices.pdf",
            file_kind: "PDF",
            state: "PARSING",
            pages_total: 100,
            pages_completed: 34,
            pages_failed: 0,
            progress_percent: "34.00",
            created_at: new Date().toISOString(),
            completed_at: null,
            sanitized_error_message: null,
            invoices: 0,
            open_reviews: 0,
          },
          {
            job_id: "j2",
            document_id: "d2",
            filename: "april.pdf",
            file_kind: "PDF",
            state: "REQUIRES_REVIEW",
            pages_total: 3,
            pages_completed: 3,
            pages_failed: 0,
            progress_percent: "100.00",
            created_at: new Date().toISOString(),
            completed_at: new Date().toISOString(),
            sanitized_error_message: null,
            invoices: 3,
            open_reviews: 2,
          },
        ])
      )
    )
    renderWithProviders(<ProcessingPanel />)
    expect(await screen.findByText("Processing 1 document")).toBeInTheDocument()
    expect(screen.getByText("Reading pages 34/100")).toBeInTheDocument()
    expect(screen.getByRole("progressbar")).toHaveAttribute(
      "aria-valuenow",
      "34"
    )
    expect(
      screen.getByText("2 invoices added to the queue")
    ).toBeInTheDocument()
  })

  it("stays hidden when nothing is processing", async () => {
    const { container } = renderWithProviders(<ProcessingPanel />)
    await waitFor(() => expect(container).toBeEmptyDOMElement())
  })
})
