"use client"

import React from "react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { useRegister, usePublicConfig } from "@/features/auth/hooks"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Loader2 } from "lucide-react"
import Link from "next/link"

const registerSchema = z.object({
  organization_name: z.string().min(2, "Organization name must be at least 2 characters"),
  full_name: z.string().min(2, "Full name must be at least 2 characters"),
  email: z.string().email("Please enter a valid email address"),
  password: z.string().min(12, "Password must be at least 12 characters"),
})

type RegisterFormValues = z.infer<typeof registerSchema>

export default function RegisterPage() {
  const { mutate: registerOrg, isPending, error } = useRegister()
  const { data: config } = usePublicConfig()

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<RegisterFormValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: {
      organization_name: "",
      full_name: "",
      email: "",
      password: "",
    },
  })

  const onSubmit = (data: RegisterFormValues) => {
    registerOrg(data)
  }

  if (config && config.registration_mode === "disabled") {
    return (
      <Card className="shadow-lg">
        <CardHeader>
          <CardTitle>Registration Closed</CardTitle>
          <CardDescription>
            Public organization registration is currently disabled by administrator policy.
          </CardDescription>
        </CardHeader>
        <CardFooter>
          <Link href="/login" className="w-full">
            <Button variant="outline" className="w-full">
              Back to Sign in
            </Button>
          </Link>
        </CardFooter>
      </Card>
    )
  }

  return (
    <Card className="shadow-lg border-border/80">
      <CardHeader className="space-y-1">
        <CardTitle className="text-xl">Create Organization</CardTitle>
        <CardDescription>Set up a new organization and administrator account</CardDescription>
      </CardHeader>
      <form onSubmit={handleSubmit(onSubmit)}>
        <CardContent className="space-y-4">
          {error && (
            <div className="p-3 text-xs rounded-md bg-destructive/15 text-destructive font-medium border border-destructive/20">
              {(error as any)?.message || "Registration failed. Please check the provided details."}
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="organization_name">Organization Name</Label>
            <Input
              id="organization_name"
              placeholder="Acme Financial Corp"
              disabled={isPending}
              {...register("organization_name")}
            />
            {errors.organization_name && (
              <p className="text-xs text-destructive">{errors.organization_name.message}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="full_name">Administrator Name</Label>
            <Input
              id="full_name"
              placeholder="Jane Doe"
              autoComplete="name"
              disabled={isPending}
              {...register("full_name")}
            />
            {errors.full_name && (
              <p className="text-xs text-destructive">{errors.full_name.message}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="email">Work Email</Label>
            <Input
              id="email"
              type="email"
              placeholder="jane@acme.com"
              autoComplete="email"
              disabled={isPending}
              {...register("email")}
            />
            {errors.email && (
              <p className="text-xs text-destructive">{errors.email.message}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="password">Master Password (min 12 characters)</Label>
            <Input
              id="password"
              type="password"
              placeholder="••••••••••••"
              autoComplete="new-password"
              disabled={isPending}
              {...register("password")}
            />
            {errors.password && (
              <p className="text-xs text-destructive">{errors.password.message}</p>
            )}
          </div>
        </CardContent>
        <CardFooter className="flex flex-col space-y-4">
          <Button type="submit" className="w-full" disabled={isPending}>
            {isPending ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Creating organization...
              </>
            ) : (
              "Create Organization"
            )}
          </Button>

          <p className="text-center text-xs text-muted-foreground">
            Already have an account?{" "}
            <Link href="/login" className="font-medium text-primary underline underline-offset-4">
              Sign in
            </Link>
          </p>
        </CardFooter>
      </form>
    </Card>
  )
}

