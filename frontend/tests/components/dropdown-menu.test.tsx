import React from "react"
import { describe, it, expect } from "vitest"
import { render, screen } from "@testing-library/react"
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuGroup,
  DropdownMenuItem,
} from "@/components/ui/dropdown-menu"

describe("DropdownMenu and DropdownMenuLabel", () => {
  it("renders standalone DropdownMenuLabel without throwing MenuGroupContext error", () => {
    expect(() => {
      render(
        <DropdownMenu defaultOpen>
          <DropdownMenuTrigger>Open Menu</DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuLabel>My Account</DropdownMenuLabel>
            <DropdownMenuItem>Settings</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )
    }).not.toThrow()

    expect(screen.getByText("My Account")).toBeInTheDocument()
    expect(screen.getByText("Settings")).toBeInTheDocument()
  })

  it("renders DropdownMenuLabel inside DropdownMenuGroup without errors", () => {
    expect(() => {
      render(
        <DropdownMenu defaultOpen>
          <DropdownMenuTrigger>Open Grouped Menu</DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuGroup>
              <DropdownMenuLabel>Group Header</DropdownMenuLabel>
              <DropdownMenuItem>Group Item 1</DropdownMenuItem>
            </DropdownMenuGroup>
          </DropdownMenuContent>
        </DropdownMenu>
      )
    }).not.toThrow()

    expect(screen.getByText("Group Header")).toBeInTheDocument()
    expect(screen.getByText("Group Item 1")).toBeInTheDocument()
  })
})
