import React from "react"

export interface SnippetPart {
  text: string
  isMatch: boolean
}

export function parseSnippet(text: string): SnippetPart[] {
  if (!text) return []
  const parts = text.split(/(«[^»]+»)/g)
  return parts.filter(Boolean).map((part) => {
    if (part.startsWith("«") && part.endsWith("»")) {
      return {
        text: part.slice(1, -1),
        isMatch: true,
      }
    }
    return {
      text: part,
      isMatch: false,
    }
  })
}

export function RenderSnippet({ text }: { text: string }) {
  if (!text) return null

  const parts = parseSnippet(text)

  return (
    <p className="font-mono text-xs leading-relaxed text-foreground/80">
      {parts.map((part, idx) => {
        if (part.isMatch) {
          return (
            <mark
              key={idx}
              className="rounded bg-amber-200 px-0.5 font-semibold text-foreground dark:bg-amber-900/60"
            >
              {part.text}
            </mark>
          )
        }
        return <span key={idx}>{part.text}</span>
      })}
    </p>
  )
}
