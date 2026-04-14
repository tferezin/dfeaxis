"use client"

import * as React from "react"
import Image from "next/image"
import Link from "next/link"
import { useRouter } from "next/navigation"
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

/**
 * Página de redefinição de senha — callback do magic link enviado por
 * `supabase.auth.resetPasswordForEmail()`.
 *
 * Fluxo:
 *   1. Usuário clica no link no e-mail → chega aqui com `#access_token=...&type=recovery`
 *      no URL fragment.
 *   2. O cliente JS do Supabase detecta o fragment automaticamente
 *      (`detectSessionInUrl: true`, default) e dispara o evento
 *      `PASSWORD_RECOVERY` via `onAuthStateChange`.
 *   3. Nesse momento o usuário está em uma "recovery session" — pode
 *      chamar `updateUser({ password })` para definir nova senha.
 *   4. Após sucesso, redireciona para /login (a sessão é limpa pelo logout).
 *
 * Se o usuário chegar aqui SEM o token de recovery (ex: digitou direto na
 * URL), mostramos uma mensagem pedindo pra voltar e iniciar o fluxo
 * novamente.
 */
export default function ResetPasswordPage() {
  const router = useRouter()
  const [password, setPassword] = React.useState("")
  const [confirmPassword, setConfirmPassword] = React.useState("")
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [success, setSuccess] = React.useState(false)
  // Começa assumindo ausente — o evento PASSWORD_RECOVERY vai marcar como
  // presente se o token for válido.
  const [recoveryReady, setRecoveryReady] = React.useState(false)

  React.useEffect(() => {
    if (!supabase) return

    // Supabase parse automaticamente o fragment da URL e dispara
    // onAuthStateChange com event='PASSWORD_RECOVERY' quando o token
    // é válido.
    const { data: sub } = supabase.auth.onAuthStateChange((event) => {
      if (event === "PASSWORD_RECOVERY") {
        setRecoveryReady(true)
      }
    })

    // Também checamos o hash imediatamente — se já tiver sessão ativa
    // de recovery (usuário já autenticado via fragment), libera o form.
    supabase.auth.getSession().then(({ data }) => {
      if (data.session) {
        setRecoveryReady(true)
      }
    })

    return () => {
      sub.subscription.unsubscribe()
    }
  }, [])

  const formValid =
    password.length >= 8 &&
    password === confirmPassword

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)

    if (!supabase) {
      setError("Sistema não configurado. Verifique as variáveis de ambiente.")
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

    try {
      const { error: updateError } = await supabase.auth.updateUser({
        password,
      })

      if (updateError) {
        setError(updateError.message)
        return
      }

      setSuccess(true)
      // Desloga a sessão de recovery pra forçar login explícito com a nova senha.
      await supabase.auth.signOut()
      setTimeout(() => router.push("/login"), 2500)
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
          <p className="text-sm text-muted-foreground mt-1">Nova senha</p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Redefinir senha</CardTitle>
            <CardDescription>
              Escolha uma nova senha para sua conta.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {success ? (
              <div className="flex flex-col gap-4 text-center">
                <p className="text-sm text-green-600 font-medium">
                  Senha redefinida com sucesso! Redirecionando para o login...
                </p>
              </div>
            ) : !recoveryReady ? (
              <div className="flex flex-col gap-4 text-center">
                <p className="text-sm text-muted-foreground">
                  Este link de recuperação expirou ou é inválido. Solicite um
                  novo link de redefinição.
                </p>
                <Link href="/forgot-password">
                  <Button variant="outline" className="w-full">
                    Solicitar novo link
                  </Button>
                </Link>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="flex flex-col gap-4">
                <div className="flex flex-col gap-2">
                  <Label htmlFor="password">Nova senha</Label>
                  <Input
                    id="password"
                    type="password"
                    placeholder="Mínimo 8 caracteres"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    minLength={8}
                    autoComplete="new-password"
                    autoFocus
                  />
                </div>

                <div className="flex flex-col gap-2">
                  <Label htmlFor="confirmPassword">Confirmar nova senha</Label>
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

                {error && <p className="text-sm text-destructive">{error}</p>}

                <Button
                  type="submit"
                  className="w-full"
                  disabled={loading || !formValid}
                >
                  {loading ? "Salvando..." : "Redefinir senha"}
                </Button>
              </form>
            )}
          </CardContent>
        </Card>

        <p className="mt-6 text-center text-xs text-muted-foreground">
          &copy; {new Date().getFullYear()} DFeAxis. Todos os direitos
          reservados.
        </p>
      </div>
    </div>
  )
}
