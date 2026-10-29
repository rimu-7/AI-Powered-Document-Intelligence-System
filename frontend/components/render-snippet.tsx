import React from "react"

export interface SnippetPart {
  text: string
  isMatch: boolean
}

export function parseSnippet(text: string): SnippetPart[] {
  if (!text) return []
  const parts = text.split(/(«[^»]+»)/g)
  return parts
    .filter(Boolean)
    .map((part) => {
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
    <p className="text-xs text-foreground/80 leading-relaxed font-mono">
      {parts.map((part, idx) => {
        if (part.isMatch) {
          return (
            <mark
              key={idx}
              className="bg-amber-200 dark:bg-amber-900/60 text-foreground font-semibold px-0.5 rounded"
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

