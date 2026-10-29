import { NextRequest, NextResponse } from "next/server"
import { env } from "@/lib/env"
import { COOKIE_ACCESS_EXPIRY, COOKIE_ACCESS_TOKEN, COOKIE_REFRESH_TOKEN } from "@/lib/auth/cookies"

export async function POST(req: NextRequest) {
  try {
    const body = await req.json()
    const res = await fetch(`${env.API_INTERNAL_URL}/api/v1/auth/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Request-ID": req.headers.get("x-request-id") || crypto.randomUUID(),
      },
      body: JSON.stringify(body),
    })

    const data = await res.json()
    if (!res.ok) {
      return NextResponse.json(data, { status: res.status })
    }

    const { access_token, refresh_token, expires_in = 900 } = data
    const expiresAt = Date.now() + expires_in * 1000

    const response = NextResponse.json({ ok: true, expires_at: expiresAt })

    // Set di_at cookie (access token, 15m)
    response.cookies.set(COOKIE_ACCESS_TOKEN, access_token, {
      httpOnly: true,
      secure: env.COOKIE_SECURE,
      sameSite: "lax",
      path: "/",
      maxAge: expires_in,
    })

    // Set di_rt cookie (refresh token, path restricted to /bff/auth)
    response.cookies.set(COOKIE_REFRESH_TOKEN, refresh_token, {
      httpOnly: true,
      secure: env.COOKIE_SECURE,
      sameSite: "lax",
      path: "/bff/auth",
      maxAge: 14 * 24 * 3600,
    })

    // Set di_at_exp (expiry timestamp, readable by client JS for single flight lock)
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
      { error: { code: "BFF_LOGIN_FAILED", message: String(error) } },
      { status: 500 }
    )
  }
}

