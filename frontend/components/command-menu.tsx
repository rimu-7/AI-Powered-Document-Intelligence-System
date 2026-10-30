"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import {
  Coins,
  FileText,
  FileCheck,
  GitCompare,
  Search,
  Upload,
  Moon,
  Sun,
  Laptop,
  Users,
  AlertTriangle,
  History,
  Activity,
  LogOut,
  LayoutDashboard,
} from "lucide-react"
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command"
import { useTheme } from "next-themes"
import { useUpload } from "@/features/upload/upload-context"
import { useLogout, useCurrentUser } from "@/features/auth/hooks"
import { canAdmin } from "@/lib/permissions"

export function CommandMenu() {
  const [open, setOpen] = React.useState(false)
  const router = useRouter()
  const { setTheme } = useTheme()
  const { setIsOpen: setUploadOpen } = useUpload()
  const { mutate: logout } = useLogout()
  const { data: user } = useCurrentUser()

  React.useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault()
        setOpen((o) => !o)
      }
    }
    document.addEventListener("keydown", down)
    return () => document.removeEventListener("keydown", down)
  }, [])

  const runCommand = React.useCallback((command: () => void) => {
    setOpen(false)
    command()
  }, [])

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      {/* CommandDialog is only the dialog shell; cmdk parts need a <Command> root. */}
      <Command>
        <CommandInput placeholder="Type a command or search..." />
        <CommandList>
          <CommandEmpty>No results found.</CommandEmpty>
          <CommandGroup heading="Navigation">
            <CommandItem onSelect={() => runCommand(() => router.push("/"))}>
              <LayoutDashboard className="mr-2 h-4 w-4" />
              <span>Dashboard</span>
            </CommandItem>
            <CommandItem
              onSelect={() => runCommand(() => router.push("/documents"))}
            >
              <FileText className="mr-2 h-4 w-4" />
              <span>Documents</span>
            </CommandItem>
            <CommandItem
              onSelect={() => runCommand(() => router.push("/reviews"))}
            >
              <FileCheck className="mr-2 h-4 w-4" />
              <span>Review Queue</span>
            </CommandItem>
            <CommandItem
              onSelect={() => runCommand(() => router.push("/compare"))}
            >
              <GitCompare className="mr-2 h-4 w-4" />
              <span>Comparisons & Reconciliations</span>
            </CommandItem>
            <CommandItem
              onSelect={() => runCommand(() => router.push("/search"))}
            >
              <Search className="mr-2 h-4 w-4" />
              <span>Search</span>
            </CommandItem>
          </CommandGroup>

          <CommandSeparator />
          <CommandGroup heading="Actions">
            <CommandItem onSelect={() => runCommand(() => setUploadOpen(true))}>
              <Upload className="mr-2 h-4 w-4" />
              <span>Upload Documents...</span>
            </CommandItem>
          </CommandGroup>

          {canAdmin(user?.role) && (
            <>
              <CommandSeparator />
              <CommandGroup heading="Administration">
                <CommandItem
                  onSelect={() => runCommand(() => router.push("/admin/users"))}
                >
                  <Users className="mr-2 h-4 w-4" />
                  <span>Users & Permissions</span>
                </CommandItem>
                <CommandItem
                  onSelect={() =>
                    runCommand(() => router.push("/admin/currency"))
                  }
                >
                  <Coins className="mr-2 h-4 w-4" />
                  <span>Currency Rules</span>
                </CommandItem>
                <CommandItem
                  onSelect={() =>
                    runCommand(() => router.push("/admin/failed-jobs"))
                  }
                >
                  <AlertTriangle className="mr-2 h-4 w-4" />
                  <span>Dead Letter / Failed Jobs</span>
                </CommandItem>
                <CommandItem
                  onSelect={() => runCommand(() => router.push("/admin/audit"))}
                >
                  <History className="mr-2 h-4 w-4" />
                  <span>Audit Log</span>
                </CommandItem>
                <CommandItem
                  onSelect={() =>
                    runCommand(() => router.push("/admin/system"))
                  }
                >
                  <Activity className="mr-2 h-4 w-4" />
                  <span>System Readiness</span>
                </CommandItem>
              </CommandGroup>
            </>
          )}

          <CommandSeparator />
          <CommandGroup heading="Theme">
            <CommandItem onSelect={() => runCommand(() => setTheme("light"))}>
              <Sun className="mr-2 h-4 w-4" />
              <span>Light</span>
            </CommandItem>
            <CommandItem onSelect={() => runCommand(() => setTheme("dark"))}>
              <Moon className="mr-2 h-4 w-4" />
              <span>Dark</span>
            </CommandItem>
            <CommandItem onSelect={() => runCommand(() => setTheme("system"))}>
              <Laptop className="mr-2 h-4 w-4" />
              <span>System Default</span>
            </CommandItem>
          </CommandGroup>

          <CommandSeparator />
          <CommandGroup heading="Account">
            <CommandItem onSelect={() => runCommand(() => logout(false))}>
              <LogOut className="mr-2 h-4 w-4" />
              <span>Sign Out</span>
            </CommandItem>
          </CommandGroup>
        </CommandList>
      </Command>
    </CommandDialog>
  )
}
