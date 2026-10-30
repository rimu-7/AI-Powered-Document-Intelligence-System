import React, { Suspense } from "react"
import { describe, it, expect, vi } from "vitest"
import { act, screen, fireEvent, waitFor, within } from "@testing-library/react"
import { http, HttpResponse } from "msw"
import { NuqsTestingAdapter } from "nuqs/adapters/testing"
import { server } from "../msw/server"
import { renderWithProviders } from "../utils"
import { page } from "../msw/handlers"
import ComparisonResultsPage from "@/app/(app)/compare/[id]/page"
import DocumentDetailPage from "@/app/(app)/documents/[id]/page"
import { InvoiceHistory } from "@/features/invoices/components/invoice-history"

/** Pages read route params with use(); resolve them inside act. */
async function renderPage(ui: React.ReactElement) {
  await act(async () => {
    renderWithProviders(ui)
  })
}

const push = vi.fn()
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/",
}))

const docs = [
  {
    id: "d-left",
    side: "left",
    filename: "original.pdf",
    file_kind: "PDF",
    deleted: false,
  },
  {
    id: "d-right",
    side: "right",
    filename: "revised.pdf",
    file_kind: "PDF",
    deleted: false,
  },
]

function comparison(status: string) {
  return {
    id: "cmp-1",
    comparison_type: "PDF_PDF",
    left_document_id: "d-left",
    right_document_id: "d-right",
    matching_strategy: "invoice_number+supplier/v1",
    status,
    parameters_json: { amount_tolerance: "0.01" },
    summary_json:
      status === "COMPLETED"
        ? {
            matched_count: 1,
            mismatched_count: 1,
            ambiguous_count: 0,
            missing_left_count: 0,
            missing_right_count: 1,
          }
        : {},
    processing_run_id: "run-1",
    stale_reason: null,
    created_by: null,
    created_at: "2026-10-30T10:00:00Z",
    completed_at: status === "COMPLETED" ? "2026-10-30T10:00:05Z" : null,
    documents: docs,
    error_message: null,
  }
}

const ref = (doc: string, inv: string) => ({
  document_id: doc,
  filename: doc === "d-left" ? "original.pdf" : "revised.pdf",
  invoice_record_id: inv,
  page_start: 1,
})

const records = [
  {
    id: "f0",
    position: 0,
    record_key: "INV-1 | ABC",
    field_name: "__record__",
    status: "MISMATCH",
    left_value_json: "INV-1 / ABC Ltd",
    right_value_json: "INV-1 / ABC Ltd",
    difference_json: {
      match_quality: "exact",
      mismatched_fields: ["total_amount"],
    },
    evidence_json: { left: ref("d-left", "i1"), right: ref("d-right", "i2") },
  },
  {
    id: "f9",
    position: 9,
    record_key: "INV-2 | ABC",
    field_name: "__record__",
    status: "MISSING_RIGHT",
    left_value_json: "INV-2 / ABC Ltd",
    right_value_json: null,
    difference_json: null,
    evidence_json: { left: ref("d-left", "i3") },
  },
]

const fields = [
  {
    id: "f1",
    position: 1,
    record_key: "INV-1 | ABC",
    field_name: "total_amount",
    status: "MISMATCH",
    left_value_json: "100.00",
    right_value_json: "120.00",
    difference_json: { difference: "20.00", tolerance: "0.01" },
    evidence_json: {},
  },
]

describe("Comparison results", () => {
  it("shows progress, then the results as soon as the run finishes", async () => {
    let calls = 0
    const findingRequests: URL[] = []
    server.use(
      http.get("*/bff/api/v1/comparisons/:id", () =>
        HttpResponse.json(comparison(calls++ === 0 ? "RUNNING" : "COMPLETED"))
      ),
      http.get("*/bff/api/v1/comparisons/:id/findings", ({ request }) => {
        const url = new URL(request.url)
        findingRequests.push(url)
        if (url.searchParams.get("record_position") === "0")
          return HttpResponse.json(page(fields))
        const status = url.searchParams.get("finding_status")
        return HttpResponse.json(
          page(records.filter((r) => !status || r.status === status))
        )
      })
    )

    await renderPage(
      <Suspense fallback={null}>
        <ComparisonResultsPage params={Promise.resolve({ id: "cmp-1" })} />
      </Suspense>
    )

    expect(await screen.findByText("Comparing…")).toBeInTheDocument()
    // No findings are requested while the run is still going.
    expect(findingRequests).toHaveLength(0)

    // The page polls; results appear without a reload.
    expect(
      await screen.findByText("Different: Total.", {}, { timeout: 4000 })
    ).toBeInTheDocument()
    expect(screen.getByText("original.pdf")).toBeInTheDocument()
    expect(screen.getByText("revised.pdf")).toBeInTheDocument()

    // Expanding a record loads its fields with a readable difference.
    fireEvent.click(screen.getByText("Different: Total.").closest("button")!)
    const table = await screen.findByRole("table")
    expect(within(table).getByText("Total")).toBeInTheDocument()
    expect(within(table).getByText("120.00")).toBeInTheDocument()
    expect(within(table).getByText("+20.00")).toBeInTheDocument()

    // Summary tiles filter with the backend's real parameter and values.
    fireEvent.click(
      within(screen.getByRole("group", { name: "Filter results" })).getByRole(
        "button",
        { name: /Only on left/ }
      )
    )
    await waitFor(() =>
      expect(
        findingRequests.some(
          (u) => u.searchParams.get("finding_status") === "MISSING_RIGHT"
        )
      ).toBe(true)
    )
    await waitFor(() =>
      expect(screen.queryByText("Different: Total.")).not.toBeInTheDocument()
    )
  })

  it("explains a failed run and offers to run it again", async () => {
    server.use(
      http.get("*/bff/api/v1/comparisons/:id", () =>
        HttpResponse.json({
          ...comparison("FAILED"),
          error_message: "Document not available",
        })
      ),
      http.post("*/bff/api/v1/comparisons/:id/rerun", () =>
        HttpResponse.json(
          {
            comparison_id: "cmp-2",
            job_id: "run-2",
            status_url: "/api/v1/jobs/run-2",
          },
          { status: 202 }
        )
      )
    )
    await renderPage(
      <Suspense fallback={null}>
        <ComparisonResultsPage params={Promise.resolve({ id: "cmp-1" })} />
      </Suspense>
    )
    expect(
      await screen.findByText("Document not available")
    ).toBeInTheDocument()
    fireEvent.click(await screen.findByRole("button", { name: /Run again/ }))
    await waitFor(() => expect(push).toHaveBeenCalledWith("/compare/cmp-2"))
  })
})

describe("Document page", () => {
  it("lists the document's jobs from the paged API response", async () => {
    server.use(
      http.get("*/bff/api/v1/documents/:id/jobs", () =>
        HttpResponse.json(
          page([
            {
              id: "job-1",
              document_id: "doc-001",
              job_type: "DOCUMENT_PROCESSING",
              state: "REQUIRES_REVIEW",
              attempt_number: 1,
              pages_total: 3,
              pages_completed: 3,
              pages_failed: 0,
              progress_percent: 100,
              created_at: "2026-10-30T10:00:00Z",
              updated_at: "2026-10-30T10:00:00Z",
            },
          ])
        )
      )
    )
    await renderPage(
      <NuqsTestingAdapter searchParams="?tab=jobs">
        <Suspense fallback={null}>
          <DocumentDetailPage params={Promise.resolve({ id: "doc-001" })} />
        </Suspense>
      </NuqsTestingAdapter>
    )
    expect(
      (await screen.findAllByText("Document processing")).length
    ).toBeGreaterThan(0)
  })
})

describe("Invoice history", () => {
  it("shows who changed what, and why", () => {
    renderWithProviders(
      <InvoiceHistory
        actions={[
          {
            id: "a1",
            invoice_record_id: "inv-1",
            review_task_id: null,
            reviewer_id: "u1",
            reviewer_name: "Dana Reviewer",
            action_type: "CORRECTION",
            field_path: "line_items[1].unit_price",
            old_value_json: "10.00",
            new_value_json: "12.00",
            reason: "Price on page 2",
            invoice_version: 3,
            created_at: "2026-10-30T10:00:00Z",
          },
        ]}
      />
    )
    expect(screen.getByText("Line 2 · unit price")).toBeInTheDocument()
    expect(screen.getByText("10.00")).toBeInTheDocument()
    expect(screen.getByText("12.00")).toBeInTheDocument()
    expect(screen.getByText("“Price on page 2”")).toBeInTheDocument()
    expect(screen.getByText(/Dana Reviewer/)).toBeInTheDocument()
  })
})
