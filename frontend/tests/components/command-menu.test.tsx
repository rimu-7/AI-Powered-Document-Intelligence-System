import React from "react"
import { describe, expect, it, vi } from "vitest"
import { fireEvent, screen } from "@testing-library/react"
import { renderWithProviders } from "../utils"
import { CommandMenu } from "@/components/command-menu"
import { UploadProvider } from "@/features/upload/upload-context"

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/",
}))

describe("CommandMenu", () => {
  it("opens with Ctrl/Cmd+K and lists navigation commands", async () => {
    renderWithProviders(
      <UploadProvider>
        <CommandMenu />
      </UploadProvider>
    )
    fireEvent.keyDown(document, { key: "k", ctrlKey: true })

    expect(
      await screen.findByPlaceholderText(/Type a command or search/i)
    ).toBeInTheDocument()
    expect(screen.getByText("Documents")).toBeInTheDocument()
  })
})
