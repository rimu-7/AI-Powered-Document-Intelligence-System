import { format, parseISO } from "date-fns"

/**
 * Format decimal string as currency using Intl.NumberFormat without converting to float arithmetic.
 */
export function formatMoney(
  value: string | number | null | undefined,
  currency: string = "EUR",
  locale: string = "en-US"
): string {
  if (value === null || value === undefined || value === "") {
    return "—"
  }

  const str = String(value).trim()
  const num = parseFloat(str)
  if (Number.isNaN(num)) {
    return str
  }

  try {
    return new Intl.NumberFormat(locale, {
      style: "currency",
      currency: currency || "EUR",
      minimumFractionDigits: 2,
      maximumFractionDigits: 4,
    }).format(num)
  } catch {
    return `${currency} ${str}`
  }
}

/**
 * Format bytes into human-readable B, KB, MB, GB
 */
export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || isNaN(bytes)) return "0 B"
  if (bytes === 0) return "0 B"

  const k = 1024
  const sizes = ["B", "KB", "MB", "GB", "TB"]
  const i = Math.floor(Math.log(bytes) / Math.log(k))

  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`
}

/**
 * Format ISO date string into readable string
 */
export function formatDate(isoString: string | null | undefined, pattern: string = "MMM d, yyyy HH:mm"): string {
  if (!isoString) return "—"
  try {
    const d = typeof isoString === "string" ? parseISO(isoString) : new Date(isoString)
    return format(d, pattern)
  } catch {
    return String(isoString)
  }
}

export function formatTimeAgo(isoString: string | null | undefined): string {
  if (!isoString) return "—"
  try {
    const date = new Date(isoString)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffSec = Math.floor(diffMs / 1000)

    if (diffSec < 60) return `${diffSec}s ago`
    const diffMin = Math.floor(diffSec / 60)
    if (diffMin < 60) return `${diffMin}m ago`
    const diffHour = Math.floor(diffMin / 60)
    if (diffHour < 24) return `${diffHour}h ago`
    const diffDays = Math.floor(diffHour / 24)
    return `${diffDays}d ago`
  } catch {
    return formatDate(isoString)
  }
}

