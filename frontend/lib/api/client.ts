import axios, { AxiosError, InternalAxiosRequestConfig } from "axios"
import { normalizeError } from "./errors"
import { getCookieExpiryTimestamp } from "@/lib/auth/cookies"
import { requestTokenRefresh, authChannel } from "@/lib/auth/refresh-lock"

export const apiClient = axios.create({
  baseURL: "/bff/api/v1",
  timeout: 30000,
  headers: {
    "X-Requested-With": "docintel",
  },
})

// Request interceptor: attach X-Request-ID and handle upload timeouts
apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  if (!config.headers["X-Request-ID"]) {
    config.headers["X-Request-ID"] =
      typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : `req-${Date.now()}`
  }

  // Disable timeout for file uploads
  if (config.data instanceof FormData) {
    config.timeout = 0
  }

  return config
})

// Response interceptor: single flight refresh on TOKEN_EXPIRED
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & {
      _retried?: boolean
    }

    if (
      error.response?.status === 401 &&
      originalRequest &&
      !originalRequest._retried
    ) {
      const errData = error.response.data as
        { error?: { code?: string } } | undefined
      const code = errData?.error?.code

      // Only TOKEN_EXPIRED triggers refresh; terminal auth errors send straight to /login
      if (
        code === "TOKEN_EXPIRED" ||
        (!code && !originalRequest.url?.includes("/auth/"))
      ) {
        originalRequest._retried = true

        try {
          const refreshRes = await requestTokenRefresh(async () => {
            const res = await axios.post(
              "/bff/auth/refresh",
              {},
              { headers: { "X-Requested-With": "docintel" } }
            )
            return { ok: res.data?.ok }
          })

          if (refreshRes.ok) {
            return apiClient(originalRequest)
          }
        } catch {
          // Refresh failed - proceed to logout
        }
      }

      // Hard redirect to login if auth is invalid or refresh fails
      if (
        typeof window !== "undefined" &&
        !window.location.pathname.startsWith("/login")
      ) {
        authChannel?.postMessage({ type: "LOGOUT" })
        // eslint-disable-next-line @next/next/no-location-assign-relative-destination
        window.location.href = `/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`
      }
    }

    return Promise.reject(normalizeError(error))
  }
)

// Proactive refresh scheduler
let proactiveTimer: NodeJS.Timeout | null = null

export function initProactiveRefresh() {
  if (typeof window === "undefined") return

  const scheduleNext = () => {
    if (proactiveTimer) clearTimeout(proactiveTimer)

    const exp = getCookieExpiryTimestamp()
    if (!exp) return

    const now = Date.now()
    const msUntilRefresh = exp - now - 60_000 // refresh 60s before expiry

    if (msUntilRefresh <= 0) {
      // Already close to expiry, trigger refresh if visible
      if (document.visibilityState === "visible") {
        requestTokenRefresh(async () => {
          const res = await axios.post(
            "/bff/auth/refresh",
            {},
            { headers: { "X-Requested-With": "docintel" } }
          )
          scheduleNext()
          return { ok: res.data?.ok }
        }).catch(() => {})
      }
    } else {
      proactiveTimer = setTimeout(
        () => {
          if (document.visibilityState === "visible") {
            requestTokenRefresh(async () => {
              const res = await axios.post(
                "/bff/auth/refresh",
                {},
                { headers: { "X-Requested-With": "docintel" } }
              )
              scheduleNext()
              return { ok: res.data?.ok }
            }).catch(() => {})
          }
        },
        Math.min(msUntilRefresh, 2147483647)
      )
    }
  }

  scheduleNext()
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      scheduleNext()
    }
  })
}
