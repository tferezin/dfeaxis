"use client"

import * as React from "react"
import Image from "next/image"
import Link from "next/link"
import { supabase } from "@/lib/supabase"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

export default function ForgotPasswordPage() {
  const [email, setEmail] = React.useState("")
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [sent, setSent] = React.useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)

    if (!supabase) {
      setError("Sistema não configurado. Verifique as variáveis de ambiente.")
      setLoading(false)
      return
    }

    if (!email.trim()) {
      setError("Informe o e-mail da conta.")
      setLoading(false)
      return
    }

    try {
      // Supabase dispara um e-mail com magic link. O `redirectTo` tem que
      // estar na allowlist do painel do Supabase (Authentication → URL
      // configuration → Redirect URLs).
      const redirectTo =
        typeof window !== "undefined"
          ? `${window.location.origin}/reset-password`
          : undefined

      const { error: resetError } = await supabase.auth.resetPasswordForEmail(
        email.trim(),
        { redirectTo }
      )

      if (resetError) {
        setError(resetError.message)
        return
      }

      // Por segurança, sempre mostramos sucesso mesmo se o e-mail não existir
      // (evita user enumeration). A mensagem é genérica.
      setSent(true)
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
          <Image
            src="/logo-dfeaxis.png"
            alt="DFeAxis"
            width={200}
            height={56}
            className="mx-auto mb-4"
          />
          <p className="text-sm text-muted-foreground mt-1">
            Recuperação de senha
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Esqueci minha senha</CardTitle>
            <CardDescription>
              Informe o e-mail da sua conta. Se houver cadastro, enviaremos um
              link para criar uma nova senha.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {sent ? (
              <div className="flex flex-col gap-4 text-center">
                <p className="text-sm text-green-600 font-medium">
                  Se o e-mail estiver cadastrado, você receberá um link em
                  instantes. Verifique sua caixa de entrada e a pasta de spam.
                </p>
                <Link href="/login">
                  <Button variant="outline" className="w-full">
                    Voltar para o login
                  </Button>
                </Link>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="flex flex-col gap-4">
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
                    autoFocus
                  />
                </div>

                {error && (
                  <p className="text-sm text-destructive">{error}</p>
                )}

                <Button
                  type="submit"
                  className="w-full"
                  disabled={loading || !email.trim()}
                >
                  {loading ? "Enviando..." : "Enviar link de recuperação"}
                </Button>

                <p className="text-center text-sm text-muted-foreground">
                  Lembrou a senha?{" "}
                  <Link
                    href="/login"
                    className="text-primary underline-offset-4 hover:underline"
                  >
                    Voltar para o login
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
