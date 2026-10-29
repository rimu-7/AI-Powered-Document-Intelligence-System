import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { reviewsApi, ReviewQueueParams } from "./api"
import { qk } from "@/lib/api/keys"
import { invalidateForMutation } from "@/lib/api/invalidation"
import { toast } from "sonner"

export function useReviewQueue(params?: ReviewQueueParams) {
  return useQuery({
    queryKey: qk.reviews.queue(params as Record<string, unknown>),
    queryFn: () => reviewsApi.queue(params),
    placeholderData: (previousData) => previousData,
    staleTime: 15_000,
  })
}

export function useReviewDetail(id: string) {
  return useQuery({
    queryKey: qk.reviews.detail(id),
    queryFn: () => reviewsApi.get(id),
    enabled: !!id,
  })
}

export function useClaimReview() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, force }: { id: string; force?: boolean }) =>
      reviewsApi.claim(id, force),
    onSuccess: async (_, { id }) => {
      await invalidateForMutation(queryClient, "claim_review", { reviewId: id })
      toast.success("Review task claimed")
    },
    onError: (err: any) => {
      toast.error(err.message || "Failed to claim review")
    },
  })
}

