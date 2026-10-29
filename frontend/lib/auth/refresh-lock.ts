import { getCookieExpiryTimestamp } from "./cookies"

export interface RefreshResult {
  ok: boolean
  skipped?: boolean
  error?: string
}

let activeRefreshPromise: Promise<RefreshResult> | null = null

export async function requestTokenRefresh(
  performRefreshApi: () => Promise<RefreshResult>
): Promise<RefreshResult> {
  // 1. Single-flight in one tab: return existing in-flight promise
  if (activeRefreshPromise) {
    return activeRefreshPromise
  }

  activeRefreshPromise = (async () => {
    try {
      // 2. Single-flight across tabs via Web Locks API (if supported)
      if (typeof window !== "undefined" && "locks" in navigator) {
        return await navigator.locks.request("docintel-refresh", async () => {
          // Check if another tab refreshed while we waited for the lock
          const exp = getCookieExpiryTimestamp()
          if (exp && exp > Date.now() + 60_000) {
            return { ok: true, skipped: true }
          }
          return await performRefreshApi()
        })
      } else {
        return await performRefreshApi()
      }
    } finally {
      activeRefreshPromise = null
    }
  })()

  return activeRefreshPromise
}

// BroadcastChannel for cross-tab auth state (e.g. logout)
export const authChannel =
  typeof window !== "undefined" && "BroadcastChannel" in window
    ? new BroadcastChannel("docintel-auth")
    : null

