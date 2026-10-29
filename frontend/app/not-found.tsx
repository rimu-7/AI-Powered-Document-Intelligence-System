import React from "react"
import { Button } from "@/components/ui/button"
import { FileQuestion, Home } from "lucide-react"
import Link from "next/link"

export default function NotFound() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-6 text-center bg-background">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted text-muted-foreground mb-4">
        <FileQuestion className="h-6 w-6 stroke-[1.5]" />
      </div>
      <h2 className="text-xl font-bold tracking-tight">Page Not Found</h2>
      <p className="mt-2 text-sm text-muted-foreground max-w-md">
        The requested resource, invoice, or document does not exist or may have been deleted.
      </p>

      <div className="mt-6">
        <Link href="/">
          <Button variant="default" size="sm" className="gap-2">
            <Home className="h-4 w-4" /> Return to Dashboard
          </Button>
        </Link>
      </div>
    </div>
  )
}

