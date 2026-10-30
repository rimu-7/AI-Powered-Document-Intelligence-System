import { apiClient } from "@/lib/api/client"
import type { Res } from "@/lib/api/typed"
import type { components } from "@/lib/api/schema"

export type CurrencySettings = components["schemas"]["CurrencySettingsOut"]
export type CurrencySettingsUpdate =
  components["schemas"]["CurrencySettingsUpdate"]
export type CurrencySettingsUpdated =
  components["schemas"]["CurrencySettingsUpdated"]
export type AmbiguousSymbol = components["schemas"]["AmbiguousSymbol"]

export const organizationApi = {
  async getCurrencySettings(): Promise<CurrencySettings> {
    const res = await apiClient.get<Res<"GET /organization/currency-settings">>(
      "/organization/currency-settings"
    )
    return res.data
  },

  async updateCurrencySettings(
    payload: CurrencySettingsUpdate
  ): Promise<CurrencySettingsUpdated> {
    const res = await apiClient.put<Res<"PUT /organization/currency-settings">>(
      "/organization/currency-settings",
      payload
    )
    return res.data
  },
}
