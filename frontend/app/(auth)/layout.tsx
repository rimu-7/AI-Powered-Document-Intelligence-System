import React from "react"
import { Layers } from "lucide-react"

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-muted/40 p-4">
      <div className="w-full max-w-md space-y-6">
        <div className="flex flex-col items-center space-y-2 text-center">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-md">
            <Layers className="h-5 w-5" />
          </div>
          <h1 className="text-xl font-bold tracking-tight">DocIntel AI</h1>
          <p className="text-xs text-muted-foreground">
            Document Intelligence & Financial Verification
          </p>
        </div>
        {children}
      </div>
    </div>
  )
}
