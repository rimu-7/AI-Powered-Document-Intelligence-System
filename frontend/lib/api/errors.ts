export interface ApiErrorPayload {
  code: string
  message: string
  request_id?: string
  details?: unknown
}

export class ApiError extends Error {
  status: number
  code: string
  override message: string
  requestId?: string
  details?: unknown
  retryAfter?: number

  constructor(params: {
    status: number
    code?: string
    message: string
    requestId?: string
    details?: unknown
    retryAfter?: number
  }) {
    super(params.message)
    this.name = "ApiError"
    this.status = params.status
    this.code = params.code || "UNKNOWN_ERROR"
    this.message = params.message
    this.requestId = params.requestId
    this.details = params.details
    this.retryAfter = params.retryAfter
    Object.setPrototypeOf(this, ApiError.prototype)
  }
}

export function normalizeError(err: unknown): ApiError {
  if (err instanceof ApiError) {
    return err
  }

  // Axios error shape
  if (typeof err === "object" && err !== null && "isAxiosError" in err) {
    const axiosErr = err as {
      response?: {
        status?: number
        data?: { error?: ApiErrorPayload; detail?: string | ApiErrorPayload }
        headers?: Record<string, string>
      }
      message?: string
    }

    const response = axiosErr.response
    const status = response?.status || 500
    const retryAfterHeader = response?.headers?.["retry-after"]
    const retryAfter = retryAfterHeader
      ? parseInt(retryAfterHeader, 10)
      : undefined

    const data = response?.data as any
    const errObj =
      data?.error ||
      (typeof data?.detail === "object" ? data?.detail : undefined)
    if (errObj && typeof errObj === "object") {
      let message =
        errObj.message || errObj.msg || "An unexpected error occurred"
      const rawDetails =
        errObj.details ??
        (Array.isArray(data?.detail) ? data?.detail : undefined)
      if (Array.isArray(rawDetails) && rawDetails.length > 0) {
        const detailMsgs = rawDetails
          .map((d: any) => d?.message || d?.msg)
          .filter(Boolean)
        if (detailMsgs.length > 0) {
          message = detailMsgs.join("; ")
        }
      }
      return new ApiError({
        status,
        code: errObj.code || "API_ERROR",
        message,
        requestId: errObj.request_id || response?.headers?.["x-request-id"],
        details: rawDetails,
        retryAfter,
      })
    }

    if (typeof response?.data?.detail === "string") {
      return new ApiError({
        status,
        code: "HTTP_ERROR",
        message: response.data.detail,
        requestId: response?.headers?.["x-request-id"],
        retryAfter,
      })
    }

    return new ApiError({
      status,
      code: "NETWORK_ERROR",
      message: axiosErr.message || "Network request failed",
      requestId: response?.headers?.["x-request-id"],
      retryAfter,
    })
  }

  if (err instanceof Error) {
    return new ApiError({
      status: 500,
      code: "INTERNAL_ERROR",
      message: err.message,
    })
  }

  return new ApiError({
    status: 500,
    code: "UNKNOWN_ERROR",
    message: String(err) || "Unknown error occurred",
  })
}
