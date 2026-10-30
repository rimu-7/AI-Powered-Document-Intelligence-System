import React from "react"
import { Button } from "@/components/ui/button"
import { FileQuestion, Home } from "lucide-react"
import Link from "next/link"

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background p-6 text-center">
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
        <FileQuestion className="h-6 w-6 stroke-[1.5]" />
      </div>
      <h2 className="text-xl font-bold tracking-tight">Page Not Found</h2>
      <p className="mt-2 max-w-md text-sm text-muted-foreground">
        The requested resource, invoice, or document does not exist or may have
        been deleted.
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
