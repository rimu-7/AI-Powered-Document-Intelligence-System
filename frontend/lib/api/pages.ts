/** One page of a paginated API response (`Page[T]` on the backend). */
export interface PageOf<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

/** The backend's largest allowed page size. */
export const MAX_PAGE_SIZE = 200

/**
 * Reads every page of a paginated endpoint and returns all items.
 * `cap` stops runaway loops on very large collections.
 */
export async function fetchAllPages<T>(
  fetchPage: (offset: number, limit: number) => Promise<PageOf<T>>,
  { cap = 5000 }: { cap?: number } = {}
): Promise<T[]> {
  const items: T[] = []
  let offset = 0
  for (;;) {
    const page = await fetchPage(offset, MAX_PAGE_SIZE)
    items.push(...page.items)
    offset += page.items.length
    if (page.items.length === 0 || offset >= page.total || items.length >= cap)
      return items
  }
}
