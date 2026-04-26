"use client"

import { useEffect, useState } from "react"
import { useRouter, usePathname } from "next/navigation"
import Link from "next/link"
import {
  LayoutDashboard,
  Users,
  Shield,
  LogOut,
  ChevronLeft,
} from "lucide-react"
import { getSupabase } from "@/lib/supabase"
import { apiFetch } from "@/lib/api"

// A14: ADMIN_EMAILS removido do bundle. Gate server-side via /me/is-admin.
// Mesmo que o atacante driblasse o redirect aqui, todos os endpoints
// /admin/* exigem _verify_admin no backend (defesa em profundidade).

const adminNav = [
  { title: "Dashboard", href: "/admin", icon: LayoutDashboard },
  { title: "Tenants", href: "/admin/tenants", icon: Users },
]

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const router = useRouter()
  const pathname = usePathname()
  const [checking, setChecking] = useState(true)
  const [authorized, setAuthorized] = useState(false)

  useEffect(() => {
    async function checkAdmin() {
      try {
        const sb = getSupabase()
        const {
          data: { user },
        } = await sb.auth.getUser()
        if (!user) {
          router.replace("/dashboard")
          return
        }
        const res = await apiFetch<{ is_admin: boolean }>("/me/is-admin")
        if (res?.is_admin) {
          setAuthorized(true)
        } else {
          router.replace("/dashboard")
          return
        }
      } catch {
        router.replace("/dashboard")
        return
      } finally {
        setChecking(false)
      }
    }
    checkAdmin()
  }, [router])

  if (checking) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-950">
        <div className="flex flex-col items-center gap-3">
          <Shield className="size-8 animate-pulse text-slate-400" />
          <p className="text-sm text-slate-400">Verificando acesso...</p>
        </div>
      </div>
    )
  }

  if (!authorized) {
    return null
  }

  return (
    <div className="flex h-screen bg-slate-950 text-slate-100">
      {/* Sidebar */}
      <aside className="flex w-56 flex-col border-r border-slate-800 bg-slate-900">
        <div className="flex h-14 items-center gap-2 border-b border-slate-800 px-4">
          <Shield className="size-5 text-emerald-400" />
          <span className="text-sm font-semibold tracking-tight">
            DFeAxis Admin
          </span>
        </div>

        <nav className="flex-1 space-y-1 px-2 py-3">
          {adminNav.map((item) => {
            const isActive =
              item.href === "/admin"
                ? pathname === "/admin"
                : pathname?.startsWith(item.href)
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-slate-800 text-white"
                    : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"
                }`}
              >
                <item.icon className="size-4" />
                {item.title}
              </Link>
            )
          })}
        </nav>

        <div className="border-t border-slate-800 p-2">
          <Link
            href="/dashboard"
            className="flex items-center gap-2 rounded-md px-3 py-2 text-sm text-slate-400 transition-colors hover:bg-slate-800/60 hover:text-slate-200"
          >
            <ChevronLeft className="size-4" />
            Voltar ao Dashboard
          </Link>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <div className="mx-auto max-w-7xl p-6">{children}</div>
      </main>
    </div>
  )
}
