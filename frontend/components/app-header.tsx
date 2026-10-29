"use client"

import React from "react"
import { SidebarTrigger } from "@/components/ui/sidebar"
import { Separator } from "@/components/ui/separator"
import { Button } from "@/components/ui/button"
import { ThemeToggle } from "@/components/theme-toggle"
import {
  DropdownMenu,
  DropdownMenuContent,
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
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: true }))
  }

  return (
    <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center justify-between gap-2 border-b bg-background/95 backdrop-blur px-4">
      <div className="flex items-center gap-2">
        <SidebarTrigger className="-ml-1" />
        <Separator orientation="vertical" className="mr-2 h-4" />
        <Button
          variant="outline"
          size="sm"
          onClick={openCommand}
          className="h-8 gap-2 px-3 text-xs text-muted-foreground w-48 sm:w-64 justify-between font-normal"
        >
          <span className="flex items-center gap-1.5">
            <Search className="h-3.5 w-3.5" />
            <span>Search or jump to...</span>
          </span>
          <kbd className="pointer-events-none hidden sm:inline-flex h-5 select-none items-center gap-1 rounded border bg-muted px-1.5 font-mono text-[10px] font-medium text-muted-foreground">
            ⌘K
          </kbd>
        </Button>
      </div>

      <div className="flex items-center gap-2.5">
        {/* Global upload indicator (§6.1 #5) */}
        {activeCount > 0 && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => setUploadOpen(true)}
            className="h-8 gap-1.5 text-xs border-primary/40 bg-primary/5 text-primary hover:bg-primary/10"
          >
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            <span>{activeCount} upload{activeCount > 1 ? "s" : ""} active</span>
          </Button>
        )}

        {canUpload(user?.role) && (
          <Button size="sm" onClick={() => setUploadOpen(true)} className="h-8 gap-1.5 text-xs">
            <Upload className="h-3.5 w-3.5" />
            <span>Upload</span>
          </Button>
        )}

        <ThemeToggle />

        {/* User Account Menu */}
        <DropdownMenu>
          <DropdownMenuTrigger className="h-8 w-8 rounded-full border inline-flex items-center justify-center text-xs font-semibold hover:bg-muted transition-colors">
            {user?.email?.[0]?.toUpperCase() || "U"}
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel className="font-normal">
              <div className="flex flex-col space-y-1">
                <p className="text-xs font-medium leading-none">{user?.full_name || "User"}</p>
                <p className="text-[11px] leading-none text-muted-foreground">{user?.email}</p>
                <p className="text-[10px] font-mono text-muted-foreground uppercase pt-1">
                  Role: {user?.role}
                </p>
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => logout(false)} disabled={isLoggingOut} className="text-xs">
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
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  )
}
