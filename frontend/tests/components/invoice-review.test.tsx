import React from "react"
import { describe, it, expect, vi } from "vitest"
import { screen, fireEvent, waitFor } from "@testing-library/react"
import { http, HttpResponse } from "msw"
import { server } from "../msw/server"
import { renderWithProviders } from "../utils"
import InvoiceReviewPage from "@/app/(app)/invoices/[id]/page"
import { mockInvoice } from "../msw/handlers"

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    back: vi.fn(),
  }),
}))

describe("InvoiceReviewPage component", () => {
  it("renders invoice workspace details from MSW", async () => {
    renderWithProviders(<InvoiceReviewPage params={{ id: "inv-001" }} />)

    // Wait for invoice number and supplier name to load
    expect(await screen.findByText("Invoice: INV-2026-001")).toBeInTheDocument()
    expect(screen.getByText("Acme Supplies Inc.")).toBeInTheDocument()
    expect(screen.getByText("$1,100.00")).toBeInTheDocument()
    expect(screen.getByText(/Line Items \(1\)/i)).toBeInTheDocument()
  })

  it("handles edit mode toggle and form fields", async () => {
    renderWithProviders(<InvoiceReviewPage params={{ id: "inv-001" }} />)

    expect(await screen.findByText("Invoice: INV-2026-001")).toBeInTheDocument()

    // Click Edit button
    const editButton = screen.getByRole("button", { name: /Edit/i })
    fireEvent.click(editButton)

    // Expect Cancel and Save changes buttons
    expect(screen.getByRole("button", { name: /Cancel/i })).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: /Save Changes/i })
    ).toBeInTheDocument()
  })

  it("sends null for currency when Not set is selected in edit form", async () => {
    let capturedBody: any = null
    server.use(
      http.patch(
        "*/bff/api/v1/invoices/:id/corrections",
        async ({ request }) => {
          capturedBody = await request.json()
          return HttpResponse.json({
            invoice: {
              ...mockInvoice,
              currency: null,
              version: 2,
            },
            revalidation_job_id: "job-123",
          })
        }
      )
    )

    renderWithProviders(<InvoiceReviewPage params={{ id: "inv-001" }} />)
    expect(await screen.findByText("Invoice: INV-2026-001")).toBeInTheDocument()

    // Click Edit
    fireEvent.click(screen.getByRole("button", { name: /Edit/i }))

    // Open Currency Select
    const currencyCombobox = screen.getByRole("combobox")
    fireEvent.click(currencyCombobox)

    // Select "Not set"
    const notSetItem = screen.getByText("Not set")
    fireEvent.click(notSetItem)

    // Enter correction reason
    const reasonInput = screen.getByPlaceholderText(
      /Explain why fields were corrected/i
    )
    fireEvent.change(reasonInput, {
      target: { value: "Currency was unclear on scan" },
    })

    // Click Save Changes
    const saveBtn = screen.getByRole("button", { name: /Save Changes/i })
    fireEvent.click(saveBtn)

    await waitFor(() => {
      expect(capturedBody).not.toBeNull()
    })

    expect(capturedBody.changes).toContainEqual({
      field_path: "currency",
      value: null,
    })
  })

  it("renders suggested candidates for INVALID_CURRENCY and clicking one activates edit mode", async () => {
    server.use(
      http.get("*/bff/api/v1/invoices/:id/validations", () => {
        return HttpResponse.json([
          {
            id: "val-invalid-curr",
            invoice_id: "inv-001",
            rule_code: "INVALID_CURRENCY",
            severity: "WARNING",
            message: "Currency symbol '$' is ambiguous",
            field_path: "currency",
            resolution_status: "OPEN",
            details_json: {
              candidates: ["USD", "CAD", "AUD"],
            },
          },
        ])
      })
    )

    renderWithProviders(<InvoiceReviewPage params={{ id: "inv-001" }} />)
    expect(await screen.findByText("Invoice: INV-2026-001")).toBeInTheDocument()

    // Switch to Issues tab
    const issuesTab = screen.getByRole("tab", { name: /Issues/i })
    fireEvent.click(issuesTab)

    // Expect candidate buttons
    expect(await screen.findByText("Suggested currencies:")).toBeInTheDocument()
    const usdBtn = screen.getByRole("button", { name: "USD" })
    const cadBtn = screen.getByRole("button", { name: "CAD" })
    expect(usdBtn).toBeInTheDocument()
    expect(cadBtn).toBeInTheDocument()

    // Clicking CAD should switch into edit mode with CAD selected and reason prefilled
    fireEvent.click(cadBtn)

    // Check we are now in edit mode
    expect(
      screen.getByRole("button", { name: /Save Changes/i })
    ).toBeInTheDocument()
    // Combobox should display CAD
    expect(screen.getByRole("combobox")).toHaveTextContent(
      "CAD – Canadian Dollar"
    )
    // Reason should be filled
    expect(
      screen.getByPlaceholderText(/Explain why fields were corrected/i)
    ).toHaveValue("Resolve INVALID_CURRENCY: set to CAD")
  })

  it("opens approve dialog and displays blocking validation issues warning", async () => {
    renderWithProviders(<InvoiceReviewPage params={{ id: "inv-001" }} />)

    expect(await screen.findByText("Invoice: INV-2026-001")).toBeInTheDocument()

    // Click Approve button in header
    const approveBtn = screen.getByRole("button", { name: /Approve/i })
    fireEvent.click(approveBtn)

    // Approve Dialog should open
    expect(await screen.findByText("Approve Invoice")).toBeInTheDocument()
    // It should warn about blocking validation issues
    expect(screen.getByText(/Open Blocking Issues \(1\)/i)).toBeInTheDocument()
    expect(
      screen.getByText(/I acknowledge these issues and wish to approve anyway/i)
    ).toBeInTheDocument()
  })
})
