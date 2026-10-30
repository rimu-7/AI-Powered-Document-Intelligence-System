import React from "react"
import { describe, it, expect, vi } from "vitest"
import { screen, fireEvent } from "@testing-library/react"
import { renderWithProviders } from "../utils"
import { CurrencySelect } from "@/components/currency-select"
import type { CurrencyCode } from "@/lib/api/types"

describe("CurrencySelect component", () => {
  it("renders trigger with placeholder when value is null", () => {
    renderWithProviders(<CurrencySelect value={null} onChange={vi.fn()} />)

    expect(screen.getByRole("combobox")).toHaveTextContent("Select currency...")
  })

  it("renders trigger with formatted code and display name when value is provided", () => {
    renderWithProviders(<CurrencySelect value="USD" onChange={vi.fn()} />)

    expect(screen.getByRole("combobox")).toHaveTextContent("USD – US Dollar")
  })

  it("shows suggested candidates first when candidates prop is provided", () => {
    const candidates: CurrencyCode[] = ["USD", "CAD", "AUD"]
    renderWithProviders(
      <CurrencySelect value={null} onChange={vi.fn()} candidates={candidates} />
    )

    // Open popover
    fireEvent.click(screen.getByRole("combobox"))

    // Expect Suggested group
    expect(screen.getByText("Suggested")).toBeInTheDocument()
    expect(screen.getByText("All Currencies")).toBeInTheDocument()
  })

  it("calls onChange with null when Not set is selected", () => {
    const handleChange = vi.fn()
    renderWithProviders(<CurrencySelect value="USD" onChange={handleChange} />)

    // Open popover
    fireEvent.click(screen.getByRole("combobox"))

    // Click 'Not set'
    const notSetItem = screen.getByText("Not set")
    fireEvent.click(notSetItem)

    expect(handleChange).toHaveBeenCalledWith(null)
  })
})
