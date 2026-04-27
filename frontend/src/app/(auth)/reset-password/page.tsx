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
 * Fluxo PKCE (atual, com @supabase/ssr):
 *   1. Usuário clica no link → Supabase /verify redireciona pra
 *      /reset-password?code=xxx
 *   2. Trocamos explicitamente o code por uma sessão de recovery via
 *      `exchangeCodeForSession(code)`. Isso SUBSTITUI qualquer sessão
 *      antiga que o usuário tivesse no mesmo browser.
 *   3. Sessão de recovery ativa → libera o form → `updateUser({ password })`
 *      atualiza a senha no auth.users.
 *   4. signOut + redirect pra /login pra forçar autenticação explícita
 *      com a nova credencial.
 *
 * Fallback p/ flow implicit (#access_token=...&type=recovery): mantemos o
 * listener PASSWORD_RECOVERY caso o backend volte a usar implicit no futuro.
 */
export default function ResetPasswordPage() {
  const router = useRouter()
  const [password, setPassword] = React.useState("")
  const [confirmPassword, setConfirmPassword] = React.useState("")
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [success, setSuccess] = React.useState(false)
  const [recoveryReady, setRecoveryReady] = React.useState(false)
  const [exchanging, setExchanging] = React.useState(true)

  React.useEffect(() => {
    const client = supabase
    if (!client) {
      setExchanging(false)
      return
    }

    let cancelled = false

    const { data: sub } = client.auth.onAuthStateChange((event) => {
      if (event === "PASSWORD_RECOVERY") {
        setRecoveryReady(true)
      }
    })

    const setup = async () => {
      const url = new URL(window.location.href)
      const code = url.searchParams.get("code")

      if (code) {
        // PKCE: troca explícita do code pela sessão de recovery. Sem isso,
        // `getSession()` retornaria uma sessão antiga (ex: login regular
        // ainda ativo no mesmo browser) e `updateUser` operaria no JWT
        // errado — atualizando NADA na conta correta.
        const { error: exchangeError } = await client.auth.exchangeCodeForSession(code)
        if (cancelled) return
        if (exchangeError) {
          setExchanging(false)
          return
        }
        // Limpa o ?code= da URL (boa higiene, evita reuse acidental).
        window.history.replaceState({}, "", "/reset-password")
        setRecoveryReady(true)
        setExchanging(false)
        return
      }

      // Sem ?code= — pode ser flow implicit (#access_token=...) ou usuário
      // entrou direto. Se houver sessão (ex: PASSWORD_RECOVERY já parseado
      // do fragment), libera o form.
      const { data } = await client.auth.getSession()
      if (cancelled) return
      if (data.session) {
        setRecoveryReady(true)
      }
      setExchanging(false)
    }

    setup()

    return () => {
      cancelled = true
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
            ) : exchanging ? (
              <div className="flex flex-col gap-4 text-center">
                <p className="text-sm text-muted-foreground">
                  Validando link de recuperação...
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
