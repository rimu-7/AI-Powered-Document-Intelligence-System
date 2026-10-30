import { z } from "zod"

const envSchema = z.object({
  API_INTERNAL_URL: z.string().default("http://127.0.0.1:8000"),
  APP_ORIGIN: z.string().default("http://localhost:3000"),
  COOKIE_SECURE: z.preprocess(
    (val) => val === "true" || val === true,
    z.boolean().default(false)
  ),
  NEXT_PUBLIC_APP_NAME: z.string().default("DocIntel AI"),
})

export const env = envSchema.parse({
  API_INTERNAL_URL: process.env.API_INTERNAL_URL || "http://127.0.0.1:8000",
  APP_ORIGIN: process.env.APP_ORIGIN || "http://localhost:3000",
  COOKIE_SECURE:
    process.env.COOKIE_SECURE === "true" ||
    process.env.NODE_ENV === "production",
  NEXT_PUBLIC_APP_NAME: process.env.NEXT_PUBLIC_APP_NAME || "DocIntel AI",
})
