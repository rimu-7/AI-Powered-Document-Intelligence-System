export type Role = "VIEWER" | "ANALYST" | "REVIEWER" | "ADMIN"

export const Permissions = {
  DOCUMENT_READ: ["VIEWER", "ANALYST", "REVIEWER", "ADMIN"],
  DOCUMENT_UPLOAD: ["ANALYST", "REVIEWER", "ADMIN"],
  DOCUMENT_DELETE: ["ADMIN"],
  JOB_MANAGE: ["ANALYST", "REVIEWER", "ADMIN"],
  INVOICE_CORRECT: ["REVIEWER", "ADMIN"],
  INVOICE_APPROVE: ["REVIEWER", "ADMIN"],
  INVOICE_REJECT: ["REVIEWER", "ADMIN"],
  REVIEW_CLAIM: ["REVIEWER", "ADMIN"],
  COMPARE_RUN: ["ANALYST", "REVIEWER", "ADMIN"],
  USER_MANAGE: ["ADMIN"],
  AUDIT_READ: ["ADMIN"],
  OPS_READ: ["ADMIN"],
} as const

export type PermissionKey = keyof typeof Permissions

export function hasPermission(
  role: Role | string | undefined | null,
  permission: PermissionKey
): boolean {
  if (!role) return false
  const allowed = Permissions[permission] as readonly string[]
  return allowed.includes(role)
}

export function canUpload(role?: string | null): boolean {
  return hasPermission(role, "DOCUMENT_UPLOAD")
}

export function canReview(role?: string | null): boolean {
  return hasPermission(role, "INVOICE_APPROVE")
}

export function canAdmin(role?: string | null): boolean {
  return role === "ADMIN"
}
