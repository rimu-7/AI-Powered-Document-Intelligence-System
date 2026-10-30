import { env } from "@/lib/env"

/**
 * Browsers always send Origin on cross-site state-changing requests, so a
 * missing Origin means a non-browser client (no CSRF risk). Otherwise the
 * origin must be exactly the app's own; plain localhost is accepted only in
 * development (compared by hostname, never by substring).
 */
export function isTrustedOrigin(origin: string | null): boolean {
  if (!origin) return true
  if (origin === env.APP_ORIGIN) return true
  if (process.env.NODE_ENV === "production") return false
  try {
    const { hostname } = new URL(origin)
    return hostname === "localhost" || hostname === "127.0.0.1"
  } catch {
    return false
  }
}
