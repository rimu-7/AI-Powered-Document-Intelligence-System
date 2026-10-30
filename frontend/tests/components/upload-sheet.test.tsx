import React from "react"
import { describe, it, expect } from "vitest"
import { screen } from "@testing-library/react"
import { renderWithProviders } from "../utils"
import { UploadProvider, useUpload } from "@/features/upload/upload-context"
import { UploadSheet } from "@/features/upload/upload-sheet"

function TestUploadWrapper() {
  const { setIsOpen } = useUpload()

  React.useEffect(() => {
    setIsOpen(true)
  }, [setIsOpen])

  return <UploadSheet />
}

describe("UploadSheet component", () => {
  it("renders upload sheet dialog when open", async () => {
    renderWithProviders(
      <UploadProvider>
        <TestUploadWrapper />
      </UploadProvider>
    )

    expect(await screen.findByText("Upload Documents")).toBeInTheDocument()
    expect(
      screen.getByText(/Click to select or drag and drop/i)
    ).toBeInTheDocument()
    expect(
      screen.getByText("PDF, PNG, JPG, TIFF, XLSX, XLS, CSV")
    ).toBeInTheDocument()
    expect(screen.getByText("0 files in batch")).toBeInTheDocument()
  })
})
