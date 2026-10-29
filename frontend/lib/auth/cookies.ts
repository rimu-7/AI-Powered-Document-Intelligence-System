export const COOKIE_ACCESS_TOKEN = "di_at"
export const COOKIE_REFRESH_TOKEN = "di_rt"
export const COOKIE_ACCESS_EXPIRY = "di_at_exp"

export interface CookieOptions {
  secure?: boolean
  maxAge?: number
  path?: string
  httpOnly?: boolean
  sameSite?: "lax" | "strict" | "none"
}

export function getCookieExpiryTimestamp(): number | null {
  if (typeof document === "undefined") return null
  const match = document.cookie.match(new RegExp(`(^|;\\s*)${COOKIE_ACCESS_EXPIRY}=([^;]*)`))
  if (!match || !match[2]) return null
  const exp = parseInt(decodeURIComponent(match[2]), 10)
  return Number.isNaN(exp) ? null : exp
}

