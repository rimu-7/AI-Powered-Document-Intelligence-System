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
      <SidebarInset className="flex flex-col min-h-screen">
        <AppHeader />
        <main className="flex-1 p-6 md:p-8 overflow-y-auto">
          {isLoading ? (
            <div className="space-y-4">
              <div className="h-8 w-48 bg-muted animate-pulse rounded" />
              <div className="h-32 bg-muted animate-pulse rounded-lg" />
              <div className="h-64 bg-muted animate-pulse rounded-lg" />
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

