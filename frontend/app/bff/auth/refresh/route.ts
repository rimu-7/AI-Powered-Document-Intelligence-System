import { NextRequest, NextResponse } from "next/server"
import { env } from "@/lib/env"
import { COOKIE_ACCESS_EXPIRY, COOKIE_ACCESS_TOKEN, COOKIE_REFRESH_TOKEN } from "@/lib/auth/cookies"

export async function POST(req: NextRequest) {
  try {
    const refreshToken = req.cookies.get(COOKIE_REFRESH_TOKEN)?.value
    if (!refreshToken) {
      return NextResponse.json(
        { error: { code: "NO_REFRESH_TOKEN", message: "No refresh token cookie found" } },
        { status: 401 }
      )
    }

    const res = await fetch(`${env.API_INTERNAL_URL}/api/v1/auth/refresh`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Request-ID": req.headers.get("x-request-id") || crypto.randomUUID(),
      },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })

    const data = await res.json()
    if (!res.ok) {
      const errResponse = NextResponse.json(data, { status: res.status })
      errResponse.cookies.delete(COOKIE_ACCESS_TOKEN)
      errResponse.cookies.delete(COOKIE_REFRESH_TOKEN)
      errResponse.cookies.delete(COOKIE_ACCESS_EXPIRY)
      return errResponse
    }

    const { access_token, refresh_token, expires_in = 900 } = data
    const expiresAt = Date.now() + expires_in * 1000

    const response = NextResponse.json({ ok: true, expires_at: expiresAt })

    response.cookies.set(COOKIE_ACCESS_TOKEN, access_token, {
      httpOnly: true,
      secure: env.COOKIE_SECURE,
      sameSite: "lax",
      path: "/",
      maxAge: expires_in,
    })

    response.cookies.set(COOKIE_REFRESH_TOKEN, refresh_token, {
      httpOnly: true,
      secure: env.COOKIE_SECURE,
      sameSite: "lax",
      path: "/bff/auth",
      maxAge: 14 * 24 * 3600,
    })

    response.cookies.set(COOKIE_ACCESS_EXPIRY, expiresAt.toString(), {
      httpOnly: false,
      secure: env.COOKIE_SECURE,
      sameSite: "lax",
      path: "/",
      maxAge: expires_in,
    })

    return response
  } catch (error) {
    return NextResponse.json(
      { error: { code: "BFF_REFRESH_FAILED", message: String(error) } },
      { status: 500 }
    )
  }
}

