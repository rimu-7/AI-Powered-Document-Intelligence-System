"use client"

import React from "react"
import { SidebarTrigger } from "@/components/ui/sidebar"
import { Separator } from "@/components/ui/separator"
import { Button } from "@/components/ui/button"
import { ThemeToggle } from "@/components/theme-toggle"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useCurrentUser, useLogout } from "@/features/auth/hooks"
import { useUpload } from "@/features/upload/upload-context"
import { canUpload } from "@/lib/permissions"
import { Upload, Search, LogOut, ShieldAlert, Loader2 } from "lucide-react"

export function AppHeader() {
  const { data: user } = useCurrentUser()
  const { activeCount, setIsOpen: setUploadOpen } = useUpload()
  const { mutate: logout, isPending: isLoggingOut } = useLogout()

  const openCommand = () => {
    document.dispatchEvent(
      new KeyboardEvent("keydown", { key: "k", metaKey: true })
    )
  }

  return (
    <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center justify-between gap-2 border-b bg-background/95 px-4 backdrop-blur">
      <div className="flex items-center gap-2">
        <SidebarTrigger className="-ml-1" />
        <Separator orientation="vertical" className="mr-2 h-4" />
        <Button
          variant="outline"
          size="sm"
          onClick={openCommand}
          className="h-8 w-auto shrink-0 justify-between gap-2 px-2.5 text-xs font-normal text-muted-foreground sm:w-64 sm:px-3"
        >
          <span className="flex items-center gap-1.5">
            <Search className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Search or jump to...</span>
            <span className="inline sm:hidden">Search</span>
          </span>
          <kbd className="pointer-events-none hidden h-5 items-center gap-1 rounded border bg-muted px-1.5 font-mono text-[10px] font-medium text-muted-foreground select-none sm:inline-flex">
            ⌘K
          </kbd>
        </Button>
      </div>

      <div className="flex items-center gap-2">
        {/* Global upload indicator (§6.1 #5) */}
        {activeCount > 0 && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => setUploadOpen(true)}
            className="h-8 gap-1.5 border-primary/40 bg-primary/5 px-2 text-xs text-primary hover:bg-primary/10 sm:px-3"
          >
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            <span className="hidden sm:inline">
              {activeCount} upload{activeCount > 1 ? "s" : ""} active
            </span>
            <span className="inline sm:hidden">{activeCount}</span>
          </Button>
        )}

        {canUpload(user?.role) && (
          <Button
            size="sm"
            onClick={() => setUploadOpen(true)}
            className="h-8 gap-1.5 px-2.5 text-xs sm:px-3"
          >
            <Upload className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Upload</span>
          </Button>
        )}

        <ThemeToggle />

        {/* User Account Menu */}
        <DropdownMenu>
          <DropdownMenuTrigger className="inline-flex h-8 w-8 items-center justify-center rounded-full border text-xs font-semibold transition-colors hover:bg-muted">
            {user?.email?.[0]?.toUpperCase() || "U"}
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuGroup>
              <DropdownMenuLabel className="font-normal">
                <div className="flex flex-col space-y-1">
                  <p className="text-xs leading-none font-medium">
                    {user?.full_name || "User"}
                  </p>
                  <p className="text-[11px] leading-none text-muted-foreground">
                    {user?.email}
                  </p>
                  <p className="pt-1 font-mono text-[10px] text-muted-foreground uppercase">
                    Role: {user?.role}
                  </p>
                </div>
              </DropdownMenuLabel>
            </DropdownMenuGroup>
            <DropdownMenuSeparator />
            <DropdownMenuGroup>
              <DropdownMenuItem
                onClick={() => logout(false)}
                disabled={isLoggingOut}
                className="text-xs"
              >
                <LogOut className="mr-2 h-3.5 w-3.5" />
                <span>Sign out</span>
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={() => logout(true)}
                disabled={isLoggingOut}
                className="text-xs text-rose-600 focus:text-rose-600"
              >
                <ShieldAlert className="mr-2 h-3.5 w-3.5" />
                <span>Sign out everywhere</span>
              </DropdownMenuItem>
            </DropdownMenuGroup>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  )
}
