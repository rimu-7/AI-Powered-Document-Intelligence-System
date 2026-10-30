import type { paths } from "./schema"

/**
 * Response types read straight from the backend's OpenAPI schema.
 *
 *   apiClient.get<Res<"GET /documents/{document_id}/jobs">>(`/documents/${id}/jobs`)
 *
 * If the backend changes a response (for example a list becomes a page of
 * results), every call that assumed the old shape stops compiling instead of
 * crashing in the browser.
 */
type Method = "get" | "post" | "put" | "patch" | "delete"
type Route = keyof paths extends infer K
  ? K extends `/api/v1${infer R}`
    ? R
    : never
  : never

type SuccessCode = 200 | 201 | 202 | 204

type Body<Op> = Op extends { responses: infer R }
  ? {
      [C in Extract<keyof R, SuccessCode>]: R[C] extends {
        content: { "application/json": infer B }
      }
        ? B
        : void
    }[Extract<keyof R, SuccessCode>]
  : never

type Endpoint = {
  [R in Route]: {
    [M in Method]: paths[`/api/v1${R}`] extends Record<M, infer Op>
      ? Op extends undefined | never
        ? never
        : `${Uppercase<M>} ${R}`
      : never
  }[Method]
}[Route]

export type ApiEndpoint = Exclude<Endpoint, never>

/** The success body of `"<METHOD> <route>"`, e.g. `Res<"GET /jobs/active">`. */
export type Res<E extends ApiEndpoint> = E extends `${infer M} ${infer R}`
  ? R extends Route
    ? Lowercase<M> extends Method
      ? Body<NonNullable<paths[`/api/v1${R}`][Lowercase<M>]>>
      : never
    : never
  : never

/** The JSON request body of `"<METHOD> <route>"`. */
export type Req<E extends ApiEndpoint> = E extends `${infer M} ${infer R}`
  ? R extends Route
    ? Lowercase<M> extends Method
      ? NonNullable<paths[`/api/v1${R}`][Lowercase<M>]> extends {
          requestBody?: { content: { "application/json": infer B } }
        }
        ? B
        : never
      : never
    : never
  : never
