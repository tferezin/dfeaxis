"use client"

import { usePathname } from "next/navigation"
import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar"
import { AppSidebar } from "@/components/app-sidebar"
import { AppFooter } from "@/components/app-footer"
import { Separator } from "@/components/ui/separator"
import { TrialBanner } from "@/components/trial-banner"
import { TrialExpiredOverlay } from "@/components/trial-expired-overlay"
import { ChatWidget } from "@/components/chat-widget"
import { ReadOnlyProvider, useReadOnly } from "@/contexts/read-only-context"
import { useSettings } from "@/hooks/use-settings"

/** Paths that remain fully accessible even when the account is read-only. */
const TRIAL_EXEMPT_PATHS = [
  "/cadastros/configuracoes",
  "/financeiro/creditos",
]

function DashboardShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const { isReadOnly } = useReadOnly()
  const { settings } = useSettings()

  const isExemptPage = TRIAL_EXEMPT_PATHS.some((p) =>
    pathname?.startsWith(p)
  )
  const showOverlay = isReadOnly && !isExemptPage
  const isHomologacao = settings.sefazAmbiente === "2"

  return (
    <SidebarProvider>
      <AppSidebar />
      <main className="relative flex flex-1 flex-col overflow-auto">
        <TrialBanner />
        <header className="flex h-14 shrink-0 items-center gap-4 border-b bg-background px-6">
          <SidebarTrigger />
          <Separator orientation="vertical" className="h-5" />
          <div className="flex-1" />
          {isHomologacao ? (
            <div className="flex items-center gap-2 rounded-md bg-amber-50 border border-amber-200 text-amber-700 text-xs font-medium px-2.5 py-1">
              <span className="h-2 w-2 rounded-full bg-amber-500 animate-pulse" />
              Homologação
            </div>
          ) : (
            <div className="flex items-center gap-2 rounded-md bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs font-medium px-2.5 py-1">
              <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
              Produção
            </div>
          )}
        </header>
        <div className="relative flex-1">
          <div
            className={
              showOverlay
                ? "pointer-events-none select-none p-6 blur-[2px]"
                : "p-6"
            }
            aria-hidden={showOverlay || undefined}
          >
            {children}
          </div>
          {showOverlay && <TrialExpiredOverlay />}
        </div>
        <AppFooter />
        <ChatWidget context="dashboard" currentPage={pathname || undefined} />
      </main>
    </SidebarProvider>
  )
}

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <ReadOnlyProvider>
      <DashboardShell>{children}</DashboardShell>
    </ReadOnlyProvider>
  )
}
