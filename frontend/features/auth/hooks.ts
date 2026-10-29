import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { authApi, LoginRequest, RegisterRequest } from "./api"
import { qk } from "@/lib/api/keys"
import { useRouter } from "next/navigation"
import { authChannel } from "@/lib/auth/refresh-lock"
import { toast } from "sonner"

export function useCurrentUser() {
  return useQuery({
    queryKey: qk.auth.me(),
    queryFn: authApi.getMe,
    staleTime: 5 * 60 * 1000,
    retry: false,
  })
}

export function usePublicConfig() {
  return useQuery({
    queryKey: qk.auth.config(),
    queryFn: authApi.getPublicConfig,
    staleTime: 60 * 60 * 1000,
  })
}

export function useLogin() {
  const queryClient = useQueryClient()
  const router = useRouter()

  return useMutation({
    mutationFn: (data: LoginRequest) => authApi.login(data),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: qk.auth.me() })
      toast.success("Signed in successfully")
      router.push("/")
    },
    onError: (err: any) => {
      toast.error(err.message || "Failed to sign in")
    },
  })
}

export function useRegister() {
  const queryClient = useQueryClient()
  const router = useRouter()

  return useMutation({
    mutationFn: (data: RegisterRequest) => authApi.register(data),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: qk.auth.me() })
      toast.success("Organization registered successfully")
      router.push("/")
    },
    onError: (err: any) => {
      toast.error(err.message || "Registration failed")
    },
  })
}

export function useLogout() {
  const queryClient = useQueryClient()
  const router = useRouter()

  return useMutation({
    mutationFn: (allSessions?: boolean) => authApi.logout(allSessions),
    onSuccess: () => {
      authChannel?.postMessage({ type: "LOGOUT" })
      queryClient.clear()
      router.push("/login")
      toast.success("Signed out")
    },
    onError: (err: any) => {
      toast.error(err.message || "Logout failed")
    },
  })
}

