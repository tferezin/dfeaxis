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

  // Public pages that don't require auth
  const isAuthPage = pathname.startsWith("/login")
  const isPublicPage = pathname === "/" || pathname.startsWith("/landing") || pathname.startsWith("/api/")

  if (!user && !isAuthPage && !isPublicPage) {
    const loginUrl = new URL("/login", request.url)
    return NextResponse.redirect(loginUrl)
  }

  // Redirect authenticated users away from /login
  if (user && isAuthPage) {
    const dashboardUrl = new URL("/", request.url)
    return NextResponse.redirect(dashboardUrl)
  }

  return response
}

export const config = {
  matcher: [
    /*
     * Match all request paths except:
     * - _next/static (static files)
     * - _next/image (image optimization)
     * - favicon.ico (browser icon)
     * - public assets
     */
    "/((?!_next/static|_next/image|favicon.ico|landing\\.html|hero-bg\\.jpg|logo-dfeaxis\\.png|apple-icon\\.png|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)",
  ],
}
