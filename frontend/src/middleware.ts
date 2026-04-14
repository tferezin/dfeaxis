import { NextResponse, type NextRequest } from "next/server"
import { createServerClient } from "@supabase/ssr"

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl

  // Skip auth check if Supabase is not configured (dev mode)
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL
  const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
  if (!supabaseUrl || !supabaseKey) {
    return NextResponse.next()
  }

  // Create a response we can modify
  let response = NextResponse.next({
    request: { headers: request.headers },
  })

  const supabase = createServerClient(
    supabaseUrl,
    supabaseKey,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll()
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value, options }) => {
            request.cookies.set(name, value)
            response = NextResponse.next({
              request: { headers: request.headers },
            })
            response.cookies.set(name, value, options)
          })
        },
      },
    }
  )

  // Refresh session (important for keeping auth alive)
  const {
    data: { user },
  } = await supabase.auth.getUser()

  // Auth pages — públicas (não exigem auth) E redirecionam pra dashboard
  // se o usuário já estiver logado.
  const isAuthPage =
    pathname.startsWith("/login") ||
    pathname.startsWith("/signup") ||
    pathname.startsWith("/forgot-password")

  // /reset-password é público MAS não redireciona mesmo quando autenticado —
  // o magic link de recovery pode chegar pra alguém logado (ex: mesmo browser
  // com sessão antiga ainda ativa) e precisamos permitir o flow de troca
  // de senha mesmo assim.
  const isResetPasswordPage = pathname.startsWith("/reset-password")

  const isPublicPage =
    pathname === "/" ||
    pathname.startsWith("/landing") ||
    pathname.startsWith("/api/") ||
    pathname.startsWith("/termos") ||
    pathname.startsWith("/privacidade")

  if (!user && !isAuthPage && !isResetPasswordPage && !isPublicPage) {
    const loginUrl = new URL("/login", request.url)
    return NextResponse.redirect(loginUrl)
  }

  // Redirect authenticated users away from login/signup/forgot pages
  // (mas NÃO de /reset-password — veja comentário acima)
  if (user && isAuthPage) {
    const dashboardUrl = new URL("/dashboard", request.url)
    return NextResponse.redirect(dashboardUrl)
  }

  return response
}

export const config = {
  matcher: [
    /*
     * Match all request paths except:
     * - _next/static, _next/image (Next.js internals)
     * - /api routes
     * - landing-v3.html (static landing served at /)
     * - Qualquer arquivo com extensão conhecida de asset estático
     *   (imagens, fonts, scripts, css, json, xml, txt, html, maps)
     */
    "/((?!_next/static|_next/image|api/|landing-v3\\.html|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico|js|mjs|css|txt|xml|json|html|woff|woff2|ttf|otf|eot|map)$).*)",
  ],
}
