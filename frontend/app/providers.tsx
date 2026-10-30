"use client"

import React, { useState, useEffect } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { ThemeProvider } from "@/components/theme-provider"
import { UploadProvider } from "@/features/upload/upload-context"
import { NuqsAdapter } from "nuqs/adapters/next/app"
import { Toaster } from "sonner"
import { initProactiveRefresh } from "@/lib/api/client"
import { authChannel } from "@/lib/auth/refresh-lock"
import { ApiError } from "@/lib/api/errors"

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            gcTime: 5 * 60 * 1000,
            refetchOnWindowFocus: false,
            retry: (failureCount, error) => {
              if (failureCount >= 2) return false
              if (error instanceof ApiError) {
                // Never retry client 4xx errors
                if (
                  error.status >= 400 &&
                  error.status < 500 &&
                  error.status !== 429
                ) {
                  return false
                }
              }
              return true
            },
          },
        },
      })
  )

  useEffect(() => {
    initProactiveRefresh()

    // Listen for cross-tab logout events
    const channel = authChannel
    if (channel) {
      const handleMessage = (e: MessageEvent) => {
        if (e.data?.type === "LOGOUT") {
          queryClient.clear()
          // eslint-disable-next-line @next/next/no-location-assign-relative-destination
          window.location.href = "/login"
        }
      }
      channel.addEventListener("message", handleMessage)
      return () => {
        channel.removeEventListener("message", handleMessage)
      }
    }
  }, [queryClient])

  return (
    <ThemeProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
    >
      <QueryClientProvider client={queryClient}>
        <NuqsAdapter>
          <UploadProvider>
            {children}
            <Toaster richColors closeButton position="top-right" />
          </UploadProvider>
        </NuqsAdapter>
      </QueryClientProvider>
    </ThemeProvider>
  )
}
