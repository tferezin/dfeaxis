"use client"

import { usePathname } from "next/navigation"
import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar"
import { AppSidebar } from "@/components/app-sidebar"
import { AppFooter } from "@/components/app-footer"
import { Separator } from "@/components/ui/separator"
import { TrialBanner } from "@/components/trial-banner"
import { TrialExpiredOverlay } from "@/components/trial-expired-overlay"
import { useTrial } from "@/hooks/use-trial"

/** Paths that remain accessible even after the trial expires. */
const TRIAL_EXEMPT_PATHS = [
  "/cadastros/configuracoes",
  "/financeiro/creditos",
]

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const pathname = usePathname()
  const { subscriptionStatus, trialActive, loading } = useTrial()

  const isExpired =
    subscriptionStatus === "expired" ||
    (!trialActive && subscriptionStatus === "trial")

  const isExemptPage = TRIAL_EXEMPT_PATHS.some((p) => pathname?.startsWith(p))
  const showOverlay = !loading && isExpired && !isExemptPage

  return (
    <SidebarProvider>
      <AppSidebar />
      <main className="flex flex-1 flex-col overflow-auto">
        <TrialBanner />
        <header className="flex h-14 shrink-0 items-center gap-4 border-b bg-background px-6">
          <SidebarTrigger />
          <Separator orientation="vertical" className="h-5" />
          <div className="flex-1" />
          <div className="flex items-center gap-2 rounded-md bg-amber-50 border border-amber-200 text-amber-700 text-xs font-medium px-2.5 py-1">
            <span className="h-2 w-2 rounded-full bg-amber-500 animate-pulse" />
            Homologacao
          </div>
        </header>
        <div className="flex-1 p-6">{children}</div>
        <AppFooter />
        {showOverlay && <TrialExpiredOverlay />}
      </main>
    </SidebarProvider>
  )
}
