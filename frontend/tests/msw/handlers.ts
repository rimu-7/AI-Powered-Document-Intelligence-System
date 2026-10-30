import { http, HttpResponse } from "msw"

export const mockUser = {
  id: "usr-admin-1",
  email: "admin@docintel.local",
  full_name: "Admin Reviewer",
  role: "ADMIN" as const,
  organization_id: "org-1",
  is_active: true,
  created_at: "2026-10-01T00:00:00Z",
}

export const mockPublicConfig = {
  max_upload_bytes: 104857600,
  max_upload_pages: 500,
  allowed_extensions: [
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".tiff",
    ".tif",
    ".xlsx",
    ".xls",
    ".csv",
  ],
  registration_mode: "open",
  uploadthing_direct_enabled: false,
}

export const mockInvoice = {
  id: "inv-001",
  organization_id: "org-1",
  document_id: "doc-001",
  source_page_number: 1,
  invoice_number: "INV-2026-001",
  invoice_date: "2026-10-15",
  due_date: "2026-11-15",
  supplier_name: "Acme Supplies Inc.",
  supplier_tax_id: "US-987654321",
  customer_name: "DocIntel Corp",
  customer_tax_id: "US-123456789",
  currency: "USD",
  subtotal: "1000.00",
  tax_amount: "100.00",
  total_amount: "1100.00",
  review_status: "NEEDS_REVIEW" as const,
  rejection_reason: null,
  assigned_to_user_id: null,
  assigned_at: null,
  assigned_by: null,
  version: 1,
  corrected_fields_json: [],
  source_evidence_json: {
    total_amount: {
      page: 1,
      bounding_box: [100, 200, 300, 250],
      snippet: "Total: $1,100.00",
    },
  },
  line_items: [
    {
      id: "li-1",
      invoice_id: "inv-001",
      line_number: 1,
      description: "Cloud Hosting Credits",
      quantity: "10",
      unit_price: "100.00",
      total_price: "1000.00",
    },
  ],
  created_at: "2026-10-16T08:00:00Z",
  updated_at: "2026-10-16T08:00:00Z",
}

export const mockValidationIssues = [
  {
    id: "val-1",
    invoice_id: "inv-001",
    rule_code: "TAX_MISMATCH",
    rule_name: "Tax calculation mismatch",
    severity: "CRITICAL" as const,
    field_name: "tax_amount",
    message: "Calculated tax does not match stated tax",
    resolution_status: "OPEN" as const,
    acknowledged_by_user_id: null,
    acknowledged_at: null,
    created_at: "2026-10-16T08:00:00Z",
  },
]

export const handlers = [
  http.get("*/bff/api/v1/auth/me", () => {
    return HttpResponse.json(mockUser)
  }),

  http.get("*/bff/api/v1/config/public", () => {
    return HttpResponse.json(mockPublicConfig)
  }),

  http.get("*/bff/api/v1/documents", () => {
    return HttpResponse.json({
      items: [
        {
          id: "doc-001",
          organization_id: "org-1",
          filename: "sample-invoice.pdf",
          file_size_bytes: 102400,
          file_hash: "hash123",
          file_kind: "PDF",
          content_type: "application/pdf",
          page_count: 1,
          status: "EXTRACTED",
          created_at: "2026-10-16T08:00:00Z",
          updated_at: "2026-10-16T08:00:00Z",
        },
      ],
      total: 1,
      limit: 20,
      offset: 0,
    })
  }),

  http.get("*/bff/api/v1/documents/:id", ({ params }) => {
    return HttpResponse.json({
      id: params.id,
      organization_id: "org-1",
      filename: "sample-invoice.pdf",
      file_size_bytes: 102400,
      file_hash: "hash123",
      file_kind: "PDF",
      content_type: "application/pdf",
      page_count: 1,
      status: "EXTRACTED",
      created_at: "2026-10-16T08:00:00Z",
      updated_at: "2026-10-16T08:00:00Z",
    })
  }),

  http.get("*/bff/api/v1/documents/:id/pages", () => {
    return HttpResponse.json([
      {
        id: "page-1",
        document_id: "doc-001",
        page_number: 1,
        page_width: 800,
        page_height: 1000,
        ocr_confidence: 0.98,
        status: "COMPLETED",
      },
    ])
  }),

  http.get("*/bff/api/v1/invoices/:id", ({ params }) => {
    return HttpResponse.json({
      ...mockInvoice,
      id: params.id,
    })
  }),

  http.get("*/bff/api/v1/invoices/:id/line-items", () => {
    return HttpResponse.json(mockInvoice.line_items)
  }),

  http.get("*/bff/api/v1/invoices/:id/validations", () => {
    return HttpResponse.json(mockValidationIssues)
  }),

  http.get("*/bff/api/v1/invoices/:id/history", () => {
    return HttpResponse.json([])
  }),

  http.patch("*/bff/api/v1/invoices/:id/corrections", async ({ request }) => {
    const body = (await request.json()) as any
    if (body.expected_version && body.expected_version < mockInvoice.version) {
      return HttpResponse.json(
        {
          error: {
            code: "VERSION_CONFLICT",
            message: "Invoice has been modified by another reviewer",
            status: 409,
          },
        },
        { status: 409 }
      )
    }
    return HttpResponse.json({
      invoice: {
        ...mockInvoice,
        version: mockInvoice.version + 1,
      },
      revalidation_job_id: "job-reval-1",
    })
  }),

  http.post("*/bff/api/v1/invoices/:id/correct", async ({ request }) => {
    const body = (await request.json()) as any
    if (body.expected_version && body.expected_version < mockInvoice.version) {
      return HttpResponse.json(
        {
          error: {
            code: "VERSION_CONFLICT",
            message: "Invoice has been modified by another reviewer",
            status: 409,
          },
        },
        { status: 409 }
      )
    }
    return HttpResponse.json({
      ...mockInvoice,
      ...body.updates,
      version: mockInvoice.version + 1,
    })
  }),

  http.post("*/bff/api/v1/invoices/:id/approve", async ({ request }) => {
    const body = (await request.json()) as any
    if (
      mockValidationIssues.some(
        (v) =>
          (v.severity === "CRITICAL" ||
            (v.severity as string) === "BLOCKING") &&
          v.resolution_status === "OPEN"
      )
    ) {
      return HttpResponse.json(
        {
          error: {
            code: "BLOCKING_ISSUES_EXIST",
            message:
              "All blocking validation issues must be resolved or acknowledged before approval.",
            status: 400,
          },
        },
        { status: 400 }
      )
    }
    return HttpResponse.json({
      ...mockInvoice,
      review_status: "APPROVED",
      version: (body.expected_version ?? 1) + 1,
    })
  }),

  http.get("*/bff/api/v1/jobs", () => {
    return HttpResponse.json({
      items: [
        {
          id: "job-001",
          document_id: "doc-001",
          pipeline_name: "INVOICE_PROCESSING",
          state: "COMPLETED",
          progress_percent: 100,
          pages_total: 1,
          pages_completed: 1,
          created_at: "2026-10-16T08:00:00Z",
          finished_at: "2026-10-16T08:01:00Z",
        },
      ],
      total: 1,
      limit: 20,
      offset: 0,
    })
  }),

  http.get("*/bff/api/v1/search/keyword", () => {
    return HttpResponse.json({
      items: [
        {
          document_id: "doc-001",
          filename: "sample-invoice.pdf",
          score: 1.0,
          score_kind: "BM25",
          matched_pages: [1],
          snippet: "Invoice «INV-2026-001» from «Acme Supplies Inc.»",
        },
      ],
      total: 1,
      limit: 20,
      offset: 0,
    })
  }),
]
