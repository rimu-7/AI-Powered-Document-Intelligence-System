"use client"

import * as React from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  LayoutDashboard,
  FileText,
  FileCheck,
  Briefcase,
  GitCompare,
  Search,
  Users,
  AlertTriangle,
  History,
  Activity,
  Layers,
  Coins,
} from "lucide-react"

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@/components/ui/sidebar"
import { useCurrentUser } from "@/features/auth/hooks"
import { canAdmin } from "@/lib/permissions"
import { Badge } from "@/components/ui/badge"

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const pathname = usePathname()
  const { data: user } = useCurrentUser()
  const isAdmin = canAdmin(user?.role)

  const navMain = [
    {
      title: "Dashboard",
      url: "/",
      icon: LayoutDashboard,
      isActive: pathname === "/",
    },
    {
      title: "Documents",
      url: "/documents",
      icon: FileText,
      isActive: pathname.startsWith("/documents"),
    },
    {
      title: "Review Queue",
      url: "/reviews",
      icon: FileCheck,
      isActive:
        pathname.startsWith("/reviews") || pathname.startsWith("/invoices"),
    },
    {
      title: "Processing Jobs",
      url: "/jobs",
      icon: Briefcase,
      isActive: pathname.startsWith("/jobs"),
    },
    {
      title: "Compare & Reconcile",
      url: "/compare",
      icon: GitCompare,
      isActive: pathname.startsWith("/compare"),
    },
    {
      title: "Search",
      url: "/search",
      icon: Search,
      isActive: pathname.startsWith("/search"),
    },
  ]

  const adminNav = [
    {
      title: "User Management",
      url: "/admin/users",
      icon: Users,
      isActive: pathname.startsWith("/admin/users"),
    },
    {
      title: "Currency Rules",
      url: "/admin/currency",
      icon: Coins,
      isActive: pathname.startsWith("/admin/currency"),
    },
    {
      title: "Failed Jobs (DLQ)",
      url: "/admin/failed-jobs",
      icon: AlertTriangle,
      isActive: pathname.startsWith("/admin/failed-jobs"),
    },
    {
      title: "Audit Log",
      url: "/admin/audit",
      icon: History,
      isActive: pathname.startsWith("/admin/audit"),
    },
    {
      title: "System Readiness",
      url: "/admin/system",
      icon: Activity,
      isActive: pathname.startsWith("/admin/system"),
    },
  ]

  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader className="border-b px-4 py-2.5">
        <Link href="/" className="flex items-center gap-2 font-semibold">
          <div className="flex h-8 w-8 items-center justify-center text-sm font-bold text-primary-foreground shadow-sm">
            <Layers className="h-6 w-6" />
          </div>
          <div className="flex flex-col group-data-[collapsible=icon]:hidden">
            <span className="text-sm font-semibold tracking-tight">
              DocIntel AI
            </span>
            <span className="font-mono text-[10px] text-muted-foreground">
              Financial Intel
            </span>
          </div>
        </Link>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Workspace</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {navMain.map((item) => (
                <SidebarMenuItem key={item.title}>
                  <SidebarMenuButton
                    render={<Link href={item.url} />}
                    isActive={item.isActive}
                    tooltip={item.title}
                  >
                    <item.icon className="h-4 w-4" />
                    <span>{item.title}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        {isAdmin && (
          <SidebarGroup>
            <SidebarGroupLabel>Administration</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {adminNav.map((item) => (
                  <SidebarMenuItem key={item.title}>
                    <SidebarMenuButton
                      render={<Link href={item.url} />}
                      isActive={item.isActive}
                      tooltip={item.title}
                    >
                      <item.icon className="h-4 w-4" />
                      <span>{item.title}</span>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        )}
      </SidebarContent>

      <SidebarFooter className="border-t p-3">
        {user && (
          <div className="flex items-center gap-2 group-data-[collapsible=icon]:hidden">
            <div className="flex h-7 w-7 items-center justify-center rounded-full bg-muted text-xs font-medium uppercase">
              {user.email?.[0]?.toUpperCase() ?? "U"}
            </div>
            <div className="flex min-w-0 flex-1 flex-col">
              <span className="truncate text-xs font-medium">
                {user.full_name || user.email || "User"}
              </span>
              <div className="flex items-center gap-1.5">
                <Badge
                  variant="outline"
                  className="h-3.5 px-1 py-0 text-[9px] tracking-wide uppercase"
                >
                  {user.role}
                </Badge>
              </div>
            </div>
          </div>
        )}
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
