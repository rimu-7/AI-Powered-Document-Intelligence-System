import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { qk } from "@/lib/api/keys"
import { invalidateForMutation } from "@/lib/api/invalidation"
import { organizationApi, type CurrencySettingsUpdate } from "./api"

export function useCurrencySettings(enabled = true) {
  return useQuery({
    queryKey: qk.organization.currencySettings(),
    queryFn: organizationApi.getCurrencySettings,
    staleTime: 30_000,
    enabled,
  })
}

export function useUpdateCurrencySettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: CurrencySettingsUpdate) =>
      organizationApi.updateCurrencySettings(payload),
    onSuccess: async (data, variables) => {
      await invalidateForMutation(queryClient, "update_currency_settings")
      const n = data.resolved_invoices
      if (n > 0) {
        toast.success(
          `Currency rules saved. ${n} waiting ${n === 1 ? "invoice" : "invoices"} resolved.`
        )
      } else if (variables.apply_to_pending && data.pending_invoices > 0) {
        toast.success(
          "Currency rules saved. No waiting invoice matches them yet."
        )
      } else {
        toast.success("Currency rules saved.")
      }
    },
    onError: (err: any) => {
      toast.error(err.message || "Failed to save currency rules")
    },
  })
}
