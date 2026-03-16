import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar"
import { AppSidebar } from "@/components/app-sidebar"
import { AppFooter } from "@/components/app-footer"
import { Separator } from "@/components/ui/separator"

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <SidebarProvider>
      <AppSidebar />
      <main className="flex flex-1 flex-col overflow-auto">
        <header className="flex h-14 shrink-0 items-center gap-4 border-b bg-background px-6">
          <SidebarTrigger />
          <Separator orientation="vertical" className="h-5" />
          <div className="flex-1" />
          <div className="flex items-center gap-2 rounded-md bg-amber-50 border border-amber-200 text-amber-700 text-xs font-medium px-2.5 py-1">
            <span className="h-2 w-2 rounded-full bg-amber-500 animate-pulse" />
            Homologação
          </div>
        </header>
        <div className="flex-1 p-6">{children}</div>
        <AppFooter />
      </main>
    </SidebarProvider>
  )
}
