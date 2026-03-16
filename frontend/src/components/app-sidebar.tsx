"use client"

import * as React from "react"
import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import {
  LayoutDashboard,
  FileText,
  Truck,
  Building2,
  FileStack,
  Building,
  ShieldCheck,
  Key,
  Settings,
  CreditCard,
  ChevronDown,
  LogOut,
} from "lucide-react"

import { supabase } from "@/lib/supabase"
import { cn } from "@/lib/utils"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  SidebarSeparator,
} from "@/components/ui/sidebar"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

type NavSubItem = {
  title: string
  href: string
  icon: React.ElementType
  badge?: string
}

type NavItem = {
  title: string
  href?: string
  icon: React.ElementType
  badge?: string
  items?: NavSubItem[]
}

type NavSection = {
  label: string
  items: NavItem[]
}

const navigation: NavSection[] = [
  {
    label: "Menu",
    items: [
      {
        title: "Dashboard",
        href: "/",
        icon: LayoutDashboard,
      },
    ],
  },
  {
    label: "Histórico",
    items: [
      { title: "NF-e", href: "/historico/nfe", icon: FileText },
      { title: "CT-e", href: "/historico/cte", icon: Truck },
      { title: "NFS-e", href: "/historico/nfse", icon: Building2, badge: "Em breve" },
      { title: "MDF-e", href: "/historico/mdfe", icon: FileStack },
    ],
  },
  {
    label: "Cadastros",
    items: [
      { title: "Empresas / CNPJs", href: "/cadastros/empresas", icon: Building },
      { title: "Certificados A1", href: "/cadastros/certificados", icon: ShieldCheck },
      { title: "API Keys", href: "/cadastros/api-keys", icon: Key },
      { title: "Configurações", href: "/cadastros/configuracoes", icon: Settings },
    ],
  },
  {
    label: "Financeiro",
    items: [
      { title: "Créditos", href: "/financeiro/creditos", icon: CreditCard },
    ],
  },
]

function NavItemLink({
  item,
  isActive,
}: {
  item: NavSubItem & { href: string }
  isActive: boolean
}) {
  const Icon = item.icon
  return (
    <SidebarMenuItem>
      <SidebarMenuButton
        isActive={isActive}
        tooltip={item.title}
        render={<Link href={item.href} />}
      >
        <Icon className="size-4" />
        <span>{item.title}</span>
        {item.badge && (
          <Badge variant="secondary" className="ml-auto text-[10px] px-1.5 py-0">
            {item.badge}
          </Badge>
        )}
      </SidebarMenuButton>
    </SidebarMenuItem>
  )
}

function UserFooter() {
  const router = useRouter()
  const [email, setEmail] = React.useState<string | null>(null)

  React.useEffect(() => {
    supabase.auth.getUser().then(({ data }) => {
      setEmail(data.user?.email ?? null)
    })
  }, [])

  const handleLogout = async () => {
    await supabase.auth.signOut()
    router.push("/login")
  }

  const initials = email
    ? email.slice(0, 2).toUpperCase()
    : "U"

  return (
    <SidebarFooter>
      <SidebarSeparator />
      <DropdownMenu>
        <DropdownMenuTrigger
          className="flex w-full items-center gap-3 rounded-md px-2 py-2 text-sm hover:bg-sidebar-accent transition-colors outline-none"
        >
          <Avatar size="sm">
            <AvatarFallback className="text-xs">{initials}</AvatarFallback>
          </Avatar>
          <div className="flex-1 text-left truncate">
            <p className="text-sm font-medium truncate">
              {email ?? "Carregando..."}
            </p>
          </div>
          <ChevronDown className="size-4 text-muted-foreground" />
        </DropdownMenuTrigger>
        <DropdownMenuContent side="top" align="start" sideOffset={8}>
          <DropdownMenuItem disabled>
            <span className="text-xs text-muted-foreground truncate">
              {email}
            </span>
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={handleLogout}>
            <LogOut className="size-4 mr-2" />
            Sair
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </SidebarFooter>
  )
}

export function AppSidebar() {
  const pathname = usePathname()

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="p-4">
        <Link href="/" className="flex items-center gap-2">
          <div className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground font-bold text-sm">
            Df
          </div>
          <span className="text-lg font-bold tracking-tight group-data-[collapsible=icon]:hidden">
            DFeAxis
          </span>
        </Link>
      </SidebarHeader>

      <SidebarSeparator />

      <SidebarContent>
        {navigation.map((section) => (
          <SidebarGroup key={section.label}>
            <SidebarGroupLabel>{section.label}</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {section.items.map((item) => {
                  const href = item.href ?? "#"
                  const isActive = pathname === href
                  return (
                    <NavItemLink
                      key={item.title}
                      item={{ ...item, href, icon: item.icon, title: item.title, badge: (item as NavSubItem).badge }}
                      isActive={isActive}
                    />
                  )
                })}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        ))}
      </SidebarContent>

      <UserFooter />
    </Sidebar>
  )
}
