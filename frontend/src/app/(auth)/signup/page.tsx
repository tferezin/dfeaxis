"use client"

import * as React from "react"
import Image from "next/image"
import Link from "next/link"
import { supabase } from "@/lib/supabase"
import { apiFetch } from "@/lib/api"
import { getGaClientId } from "@/lib/ga-cookie"
import { formatPhone, unmaskPhone } from "@/lib/masks"
import { isValidBrazilianPhone } from "@/lib/validators"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export default function SignupPage() {
  const [name, setName] = React.useState("")
  const [phone, setPhone] = React.useState("")
  const [email, setEmail] = React.useState("")
  const [password, setPassword] = React.useState("")
  const [confirmPassword, setConfirmPassword] = React.useState("")
  const [error, setError] = React.useState<string | null>(null)
  const [phoneError, setPhoneError] = React.useState<string | null>(null)
  const [success, setSuccess] = React.useState(false)
  const [loading, setLoading] = React.useState(false)

  const handlePhoneChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const masked = formatPhone(e.target.value)
    setPhone(masked)
    if (phoneError) setPhoneError(null)
  }

  const phoneValid = isValidBrazilianPhone(phone)
  const formValid =
    name.trim().length > 0 &&
    phoneValid &&
    email.trim().length > 0 &&
    password.length >= 8 &&
    password === confirmPassword

  const handleSignup = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)

    if (!supabase) {
      setError("Sistema não configurado. Verifique as variáveis de ambiente.")
      console.error("Supabase client is null — NEXT_PUBLIC_SUPABASE_URL may be missing")
      setLoading(false)
      return
    }

    if (!isValidBrazilianPhone(phone)) {
      setPhoneError("Informe um telefone válido com DDD.")
      setError("Informe um telefone válido com DDD.")
      setLoading(false)
      return
    }

    if (password.length < 8) {
      setError("A senha deve ter no mínimo 8 caracteres.")
      setLoading(false)
      return
    }

    if (password !== confirmPassword) {
      setError("As senhas não coincidem.")
      setLoading(false)
      return
    }

    const phoneDigits = unmaskPhone(phone)
    // Captura o client_id do cookie _ga (setado pelo gtag no layout.tsx) para
    // que o backend possa atribuir a conversão de venda ao clique original no
    // anúncio Google quando o Stripe confirmar o pagamento.
    const gaClientId = getGaClientId()

    try {
      const { data, error: authError } = await supabase.auth.signUp({
        email,
        password,
        options: {
          // ga_client_id também vai para user_metadata para cobrir o fluxo
          // de confirmação de e-mail (quando o tenant é criado só no primeiro
          // login, o backend pode ler do user_metadata como fallback).
          data: { name, phone: phoneDigits, ga_client_id: gaClientId },
        },
      })

      if (authError) {
        if (authError.message === "User already registered") {
          setError("Este e-mail já está cadastrado.")
        } else {
          setError(authError.message)
        }
        return
      }

      // Conversão — Supabase aceitou a criação do usuário (tanto com sessão
      // imediata quanto aguardando confirmação de e-mail já contam como lead).
      if (typeof window !== "undefined") {
        const w = window as unknown as {
          gtag?: (...args: unknown[]) => void
          fbq?: (...args: unknown[]) => void
        }
        w.gtag?.("event", "sign_up", { method: "email" })
        w.fbq?.("track", "CompleteRegistration")
      }

      // Register tenant on backend (CNPJ will be collected later via cert upload).
      // Only attempt if we already have a session — otherwise email confirmation
      // is pending and the backend call will happen on first login.
      if (data.session) {
        try {
          await apiFetch("/tenants/register", {
            method: "POST",
            body: JSON.stringify({
              // Backend TenantRegisterRequest exige `company_name` (não `name`).
              // Historicamente enviávamos `name` mas esse branch quase nunca é
              // executado (email confirmation ativo no Supabase faz o fluxo
              // cair no else), por isso o 422 nunca foi notado em produção.
              company_name: name,
              email,
              phone: phoneDigits,
              ga_client_id: gaClientId,
            }),
          })
        } catch (registerErr) {
          console.error("Tenant registration failed:", registerErr)
          setError(
            "Conta criada, mas houve um erro ao configurar seu workspace. Tente fazer login novamente."
          )
          return
        }
        window.location.href = "/dashboard"
      } else {
        setSuccess(true)
      }
    } catch {
      setError("Erro inesperado. Tente novamente.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-svh items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <Image src="/logo-dfeaxis.png" alt="DFeAxis" width={200} height={56} className="mx-auto mb-4" />
          <p className="text-sm text-muted-foreground mt-1">
            Captura automática de documentos fiscais recebidos
          </p>
          <p className="text-xs text-muted-foreground mt-2 max-w-[300px] mx-auto leading-relaxed">
            Seus fornecedores emitem. A SEFAZ guarda. O DFeAxis entrega no seu ERP.
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Criar conta</CardTitle>
            <CardDescription>
              Preencha os dados abaixo para criar sua conta.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {success ? (
              <div className="flex flex-col gap-4 text-center">
                <p className="text-sm text-green-600 font-medium">
                  Conta criada! Verifique seu e-mail para confirmar.
                </p>
                <Link href="/login">
                  <Button variant="outline" className="w-full">
                    Voltar para o login
                  </Button>
                </Link>
              </div>
            ) : (
              <form onSubmit={handleSignup} className="flex flex-col gap-4">
                <div className="flex flex-col gap-2">
                  <Label htmlFor="name">Nome completo</Label>
                  <Input
                    id="name"
                    type="text"
                    placeholder="Seu nome"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    required
                    autoComplete="name"
                  />
                </div>

                <div className="flex flex-col gap-2">
                  <Label htmlFor="phone">Telefone celular</Label>
                  <Input
                    id="phone"
                    type="tel"
                    placeholder="(11) 99999-9999"
                    value={phone}
                    onChange={handlePhoneChange}
                    onBlur={() => {
                      if (phone && !isValidBrazilianPhone(phone)) {
                        setPhoneError("Informe um telefone válido com DDD.")
                      }
                    }}
                    required
                    autoComplete="tel"
                    inputMode="numeric"
                    maxLength={16}
                    aria-invalid={phoneError ? true : undefined}
                  />
                  {phoneError && (
                    <p className="text-xs text-destructive">{phoneError}</p>
                  )}
                </div>

                <div className="flex flex-col gap-2">
                  <Label htmlFor="email">E-mail</Label>
                  <Input
                    id="email"
                    type="email"
                    placeholder="seu@email.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    autoComplete="email"
                  />
                </div>

                <div className="flex flex-col gap-2">
                  <Label htmlFor="password">Senha</Label>
                  <Input
                    id="password"
                    type="password"
                    placeholder="Mínimo 8 caracteres"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    minLength={8}
                    autoComplete="new-password"
                  />
                </div>

                <div className="flex flex-col gap-2">
                  <Label htmlFor="confirmPassword">Confirmar senha</Label>
                  <Input
                    id="confirmPassword"
                    type="password"
                    placeholder="Repita a senha"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    required
                    minLength={8}
                    autoComplete="new-password"
                  />
                </div>

                {error && (
                  <p className="text-sm text-destructive">{error}</p>
                )}

                <Button type="submit" className="w-full" disabled={loading || !formValid}>
                  {loading ? "Criando conta..." : "Criar conta"}
                </Button>

                <p className="text-center text-sm text-muted-foreground">
                  Já tem conta?{" "}
                  <Link href="/login" className="text-primary underline-offset-4 hover:underline">
                    Entrar
                  </Link>
                </p>
              </form>
            )}
          </CardContent>
        </Card>

        <p className="mt-6 text-center text-xs text-muted-foreground">
          &copy; {new Date().getFullYear()} DFeAxis. Todos os direitos reservados.
        </p>
      </div>
    </div>
  )
}
