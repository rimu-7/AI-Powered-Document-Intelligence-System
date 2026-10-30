import { NextRequest, NextResponse } from "next/server"
import { env } from "@/lib/env"
import {
  COOKIE_ACCESS_EXPIRY,
  COOKIE_ACCESS_TOKEN,
  COOKIE_REFRESH_TOKEN,
} from "@/lib/auth/cookies"

export async function POST(req: NextRequest) {
  const token = req.cookies.get(COOKIE_ACCESS_TOKEN)?.value
  const allSessions = req.nextUrl.searchParams.get("all_sessions") === "true"

  if (token) {
    try {
      await fetch(
        `${env.API_INTERNAL_URL}/api/v1/auth/logout${allSessions ? "?all_sessions=true" : ""}`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "X-Request-ID":
              req.headers.get("x-request-id") || crypto.randomUUID(),
          },
        }
      )
    } catch {
      // Ignore network errors on logout call to upstream
    }
  }

  const response = NextResponse.json({ ok: true })
  response.cookies.delete(COOKIE_ACCESS_TOKEN)
  response.cookies.delete(COOKIE_REFRESH_TOKEN)
  response.cookies.delete(COOKIE_ACCESS_EXPIRY)

  return response
}
