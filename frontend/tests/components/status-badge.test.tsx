import React from "react"
import { describe, it, expect } from "vitest"
import { render, screen } from "@testing-library/react"
import { StatusBadge } from "@/components/status-badge"

describe("StatusBadge component", () => {
  it("renders null when status is empty", () => {
    const { container } = render(<StatusBadge status={null} />)
    expect(container.firstChild).toBeNull()
  })

  it("renders blue styling for RUNNING", () => {
    render(<StatusBadge status="RUNNING" />)
    const badge = screen.getByText("Running")
    expect(badge).toBeInTheDocument()
    expect(badge.className).toContain("text-blue-700")
  })

  it("renders green styling for APPROVED", () => {
    render(<StatusBadge status="APPROVED" />)
    const badge = screen.getByText("Approved")
    expect(badge).toBeInTheDocument()
    expect(badge.className).toContain("text-emerald-700")
  })

  it("renders red styling for FAILED", () => {
    render(<StatusBadge status="FAILED" />)
    const badge = screen.getByText("Failed")
    expect(badge).toBeInTheDocument()
    expect(badge.className).toContain("text-rose-700")
  })

  it("formats snake_case into Title Case words", () => {
    render(<StatusBadge status="REQUIRES_REVIEW" />)
    expect(screen.getByText("Requires Review")).toBeInTheDocument()
  })
})
