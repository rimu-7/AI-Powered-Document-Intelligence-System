import { describe, it, expect } from "vitest"
import { normalizeError, ApiError } from "@/lib/api/errors"

describe("Error Normalization", () => {
  it("preserves ApiError instance", () => {
    const err = new ApiError({
      status: 404,
      code: "NOT_FOUND",
      message: "Document not found",
      requestId: "req-123",
    })

    const normalized = normalizeError(err)
    expect(normalized).toBe(err)
    expect(normalized.status).toBe(404)
    expect(normalized.code).toBe("NOT_FOUND")
    expect(normalized.requestId).toBe("req-123")
  })

  it("normalizes Axios error with backend envelope", () => {
    const axiosError = {
      isAxiosError: true,
      response: {
        status: 422,
        headers: { "x-request-id": "req-xyz", "retry-after": "5" },
        data: {
          error: {
            code: "VALIDATION_FAILED",
            message: "Invalid column mapping",
            request_id: "req-xyz",
            details: { field: "total_amount" },
          },
        },
      },
    }

    const normalized = normalizeError(axiosError)
    expect(normalized.status).toBe(422)
    expect(normalized.code).toBe("VALIDATION_FAILED")
    expect(normalized.message).toBe("Invalid column mapping")
    expect(normalized.requestId).toBe("req-xyz")
    expect(normalized.retryAfter).toBe(5)
    expect(normalized.details).toEqual({ field: "total_amount" })
  })

  it("normalizes generic Error instances", () => {
    const err = new Error("Disk full")
    const normalized = normalizeError(err)
    expect(normalized.status).toBe(500)
    expect(normalized.code).toBe("INTERNAL_ERROR")
    expect(normalized.message).toBe("Disk full")
  })

  it("extracts specific detail messages from 422 validation errors", () => {
    const axiosError = {
      isAxiosError: true,
      response: {
        status: 422,
        data: {
          error: {
            code: "REQUEST_VALIDATION_FAILED",
            message: "Request validation failed",
            details: [
              {
                loc: ["body", "left_document_id"],
                message: "Value error, left and right documents must differ",
                type: "value_error",
              },
            ],
          },
        },
      },
    }

    const normalized = normalizeError(axiosError)
    expect(normalized.status).toBe(422)
    expect(normalized.message).toBe(
      "Value error, left and right documents must differ"
    )
  })
})
