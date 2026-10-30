import { NextResponse } from "next/server"
import type { NextRequest } from "next/server"
import { COOKIE_ACCESS_TOKEN, COOKIE_REFRESH_TOKEN } from "@/lib/auth/cookies"

const PUBLIC_PATHS = [
  "/login",
  "/register",
  "/bff",
  "/_next",
  "/favicon.ico",
  "/images",
]

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl

  const isPublic = PUBLIC_PATHS.some((p) => pathname.startsWith(p))
  const hasSession =
    request.cookies.has(COOKIE_ACCESS_TOKEN) ||
    request.cookies.has(COOKIE_REFRESH_TOKEN)

  if (!isPublic && !hasSession) {
    const nextUrl = encodeURIComponent(`${pathname}${search}`)
    return NextResponse.redirect(new URL(`/login?next=${nextUrl}`, request.url))
  }

  // If user is logged in and visits login or register, redirect to dashboard
  if (hasSession && (pathname === "/login" || pathname === "/register")) {
    return NextResponse.redirect(new URL("/", request.url))
  }

  const response = NextResponse.next()

  // Security Headers
  response.headers.set("X-Content-Type-Options", "nosniff")
  response.headers.set("X-Frame-Options", "DENY")
  response.headers.set("Referrer-Policy", "strict-origin-when-cross-origin")
  response.headers.set(
    "Permissions-Policy",
    "camera=(), microphone=(), geolocation=()"
  )
  response.headers.set(
    "Content-Security-Policy",
    "default-src 'self'; script-src 'self' 'unsafe-eval' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data: https://*.uploadthing.com; font-src 'self' data:; connect-src 'self' https://*.uploadthing.com https://uploadthing.com; frame-ancestors 'none';"
  )

  return response
}

export const config = {
  matcher: [
    /*
     * Match all request paths except for:
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico, sitemap.xml, robots.txt
     */
    "/((?!_next/static|_next/image|favicon.ico|sitemap.xml|robots.txt).*)",
  ],
}
