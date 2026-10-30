import { apiClient } from "@/lib/api/client"
import type { Res } from "@/lib/api/typed"
import type { components, paths } from "@/lib/api/schema"
import axios from "axios"

export type UserOut = components["schemas"]["UserOut"]
export type PublicConfig = components["schemas"]["PublicConfig"]
export type LoginRequest =
  paths["/api/v1/auth/login"]["post"]["requestBody"]["content"]["application/json"]
export type RegisterRequest =
  paths["/api/v1/auth/register"]["post"]["requestBody"]["content"]["application/json"]

export const authApi = {
  async login(payload: LoginRequest) {
    const res = await axios.post("/bff/auth/login", payload, {
      headers: { "X-Requested-With": "docintel" },
    })
    return res.data
  },

  async register(payload: RegisterRequest) {
    const res = await axios.post("/bff/auth/register", payload, {
      headers: { "X-Requested-With": "docintel" },
    })
    return res.data
  },

  async logout(allSessions = false) {
    const res = await axios.post(
      `/bff/auth/logout${allSessions ? "?all_sessions=true" : ""}`,
      {},
      {
        headers: { "X-Requested-With": "docintel" },
      }
    )
    return res.data
  },

  async getMe(): Promise<UserOut> {
    const res = await apiClient.get<Res<"GET /auth/me">>("/auth/me")
    return res.data?.user ?? res.data
  },

  async getPublicConfig(): Promise<PublicConfig> {
    const res = await apiClient.get<Res<"GET /config/public">>("/config/public")
    return res.data
  },
}
