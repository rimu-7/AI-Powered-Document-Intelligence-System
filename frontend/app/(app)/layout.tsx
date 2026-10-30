"use client"

import React from "react"
import { SidebarProvider, SidebarInset } from "@/components/ui/sidebar"
import { AppSidebar } from "@/components/app-sidebar"
import { AppHeader } from "@/components/app-header"
import { CommandMenu } from "@/components/command-menu"
import { UploadSheet } from "@/features/upload/upload-sheet"
import { useCurrentUser } from "@/features/auth/hooks"

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { isLoading } = useCurrentUser()

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset className="flex min-h-screen flex-col">
        <AppHeader />
        <main className="flex-1 overflow-y-auto p-3.5 sm:p-5 md:p-6 lg:p-8">
          {isLoading ? (
            <div className="space-y-4">
              <div className="h-8 w-48 animate-pulse rounded bg-muted" />
              <div className="h-32 animate-pulse rounded-lg bg-muted" />
              <div className="h-64 animate-pulse rounded-lg bg-muted" />
            </div>
          ) : (
            children
          )}
        </main>
        <CommandMenu />
        <UploadSheet />
      </SidebarInset>
    </SidebarProvider>
  )
}
