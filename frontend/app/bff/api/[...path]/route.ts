import { NextRequest, NextResponse } from "next/server"
import { env } from "@/lib/env"
import { isTrustedOrigin } from "@/lib/auth/origin"
import { COOKIE_ACCESS_TOKEN } from "@/lib/auth/cookies"

export const dynamic = "force-dynamic"

const FORWARDED_HEADERS = [
  "content-type",
  "idempotency-key",
  "if-match",
  "if-none-match",
  "x-request-id",
  "accept",
]

const STRIPPED_RESPONSE_HEADERS = [
  "content-encoding",
  "content-length",
  "transfer-encoding",
  "connection",
  "keep-alive",
]

async function handleProxy(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params
  const joinedPath = path.join("/")

  // Enforce valid upstream destination
  if (!joinedPath.startsWith("v1/") && !joinedPath.startsWith("health")) {
    return NextResponse.json(
      {
        error: {
          code: "FORBIDDEN_PROXY_PATH",
          message: "Disallowed upstream proxy route",
        },
      },
      { status: 403 }
    )
  }

  // CSRF validation for state-changing requests
  const method = req.method.toUpperCase()
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    const origin = req.headers.get("origin")
    const requestedWith = req.headers.get("x-requested-with")
    if (requestedWith !== "docintel") {
      if (!isTrustedOrigin(origin)) {
        return NextResponse.json(
          {
            error: { code: "CSRF_BLOCKED", message: "CSRF validation failed" },
          },
          { status: 403 }
        )
      }
    }
  }

  const token = req.cookies.get(COOKIE_ACCESS_TOKEN)?.value
  // /bff/api/v1/* → /api/v1/*; /bff/api/health/* → /health/* (health lives outside /api)
  const upstreamPath = joinedPath.startsWith("health")
    ? `/${joinedPath}`
    : `/api/${joinedPath}`
  const upstreamUrl = new URL(
    `${upstreamPath}${req.nextUrl.search}`,
    env.API_INTERNAL_URL
  )

  const headers = new Headers()
  if (token) {
    headers.set("Authorization", `Bearer ${token}`)
  }

  for (const name of FORWARDED_HEADERS) {
    const val = req.headers.get(name)
    if (val) headers.set(name, val)
  }

  if (!headers.get("x-request-id")) {
    headers.set("x-request-id", crypto.randomUUID())
  }

  const hasBody = !["GET", "HEAD"].includes(method)
  const body = hasBody ? req.body : undefined

  try {
    const upstreamRes = await fetch(upstreamUrl.toString(), {
      method,
      headers,
      body,
      // @ts-expect-error Node fetch duplex option for streaming bodies
      duplex: hasBody ? "half" : undefined,
      cache: "no-store",
    })

    const responseHeaders = new Headers()
    upstreamRes.headers.forEach((val, key) => {
      const lower = key.toLowerCase()
      if (!STRIPPED_RESPONSE_HEADERS.includes(lower)) {
        responseHeaders.set(key, val)
      }
    })

    return new Response(upstreamRes.body, {
      status: upstreamRes.status,
      statusText: upstreamRes.statusText,
      headers: responseHeaders,
    })
  } catch (error) {
    return NextResponse.json(
      {
        error: {
          code: "UPSTREAM_UNAVAILABLE",
          message: `Failed to contact backend API: ${String(error)}`,
        },
      },
      { status: 502 }
    )
  }
}

export {
  handleProxy as GET,
  handleProxy as POST,
  handleProxy as PUT,
  handleProxy as PATCH,
  handleProxy as DELETE,
  handleProxy as HEAD,
}
