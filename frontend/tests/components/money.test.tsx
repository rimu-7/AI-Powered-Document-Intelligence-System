import React from "react"
import { describe, it, expect } from "vitest"
import { screen } from "@testing-library/react"
import { renderWithProviders } from "../utils"
import { Money } from "@/components/money"

describe("Money component", () => {
  it("renders amount with unconfirmed badge when currency is null", () => {
    renderWithProviders(<Money value="15724.91" currency={null} raw="$" />)

    expect(screen.getByText("$15,724.91")).toBeInTheDocument()
    expect(screen.getByText("unconfirmed")).toBeInTheDocument()
  })

  it("renders confirmed currency without unconfirmed badge", () => {
    renderWithProviders(<Money value="15724.91" currency="USD" />)

    expect(screen.getByText("$15,724.91")).toBeInTheDocument()
    expect(screen.queryByText("unconfirmed")).not.toBeInTheDocument()
  })

  it("handles null value gracefully", () => {
    renderWithProviders(<Money value={null} currency={null} />)

    expect(screen.getByText("—")).toBeInTheDocument()
    expect(screen.queryByText("unconfirmed")).not.toBeInTheDocument()
  })
})
