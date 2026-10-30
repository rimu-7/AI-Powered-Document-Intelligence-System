export const qk = {
  auth: {
    me: () => ["auth", "me"] as const,
    config: () => ["config", "public"] as const,
  },
  documents: {
    all: () => ["documents"] as const,
    list: (params?: Record<string, unknown>) =>
      ["documents", "list", params ?? {}] as const,
    detail: (id: string) => ["documents", "detail", id] as const,
    pages: (id: string, params?: Record<string, unknown>) =>
      ["documents", id, "pages", params ?? {}] as const,
    text: (id: string, params?: Record<string, unknown>) =>
      ["documents", id, "text", params ?? {}] as const,
    tables: (id: string, params?: Record<string, unknown>) =>
      ["documents", id, "tables", params ?? {}] as const,
    tableRows: (
      docId: string,
      tableId: string,
      params?: Record<string, unknown>
    ) => ["documents", docId, "tables", tableId, "rows", params ?? {}] as const,
    mappingSuggestions: (id: string) =>
      ["documents", id, "mapping-suggestions"] as const,
    jobs: (id: string) => ["documents", id, "jobs"] as const,
    invoices: (id: string) => ["documents", id, "invoices"] as const,
    validations: (id: string, params?: Record<string, unknown>) =>
      ["documents", id, "validations", params ?? {}] as const,
  },
  invoices: {
    all: () => ["invoices"] as const,
    detail: (id: string) => ["invoices", "detail", id] as const,
    lineItems: (id: string) => ["invoices", id, "line-items"] as const,
    history: (id: string) => ["invoices", id, "history"] as const,
    validations: (id: string, params?: Record<string, unknown>) =>
      ["invoices", id, "validations", params ?? {}] as const,
  },
  jobs: {
    all: () => ["jobs"] as const,
    list: (params?: Record<string, unknown>) =>
      ["jobs", "list", params ?? {}] as const,
    detail: (id: string) => ["jobs", "detail", id] as const,
  },
  reviews: {
    all: () => ["reviews"] as const,
    queue: (params?: Record<string, unknown>) =>
      ["reviews", "queue", params ?? {}] as const,
    detail: (id: string) => ["reviews", "detail", id] as const,
  },
  comparisons: {
    all: () => ["comparisons"] as const,
    list: (params?: Record<string, unknown>) =>
      ["comparisons", "list", params ?? {}] as const,
    detail: (id: string) => ["comparisons", "detail", id] as const,
    findings: (id: string, params?: Record<string, unknown>) =>
      ["comparisons", id, "findings", params ?? {}] as const,
  },
  reconciliations: {
    detail: (id: string) => ["reconciliations", "detail", id] as const,
    findings: (id: string, params?: Record<string, unknown>) =>
      ["reconciliations", id, "findings", params ?? {}] as const,
  },
  search: {
    keyword: (params: Record<string, unknown>) =>
      ["search", "keyword", params] as const,
    semantic: (body: Record<string, unknown>) =>
      ["search", "semantic", body] as const,
    hybrid: (body: Record<string, unknown>) =>
      ["search", "hybrid", body] as const,
  },
  admin: {
    stats: () => ["admin", "stats"] as const,
    users: (params?: Record<string, unknown>) =>
      ["admin", "users", params ?? {}] as const,
    deadLetter: (params?: Record<string, unknown>) =>
      ["admin", "dead-letter", params ?? {}] as const,
    auditEvents: (params?: Record<string, unknown>) =>
      ["admin", "audit-events", params ?? {}] as const,
    health: () => ["admin", "health"] as const,
  },
} as const
