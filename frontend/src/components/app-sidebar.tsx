"use client"

import * as React from "react"
import Image from "next/image"
import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import {
  LayoutDashboard,
  FileText,
  Truck,
  Building2,
  FileStack,
  FileCheck,
  Building,
  ShieldCheck,
  Key,
  Settings,
  Receipt,
  ChevronDown,
  LogOut,
  Play,
  ScrollText,
  Rocket,
  Shield,
} from "lucide-react"

import { supabase } from "@/lib/supabase"
import { cn } from "@/lib/utils"
import { useSettings } from "@/hooks/use-settings"
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
        href: "/dashboard",
        icon: LayoutDashboard,
      },
    ],
  },
  {
    label: "Documentos Recebidos",
    items: [
      { title: "NF-e Recebidas", href: "/historico/nfe", icon: FileText, badge: "SAP" },
      { title: "CT-e Recebidos", href: "/historico/cte", icon: Truck, badge: "SAP" },
      { title: "NFS-e Recebidas", href: "/historico/nfse", icon: Building2, badge: "ADN" },
      { title: "MDF-e Recebidos", href: "/historico/mdfe", icon: FileStack },
    ],
  },
  {
    label: "Cadastros",
    items: [
      { title: "Certificados A1", href: "/cadastros/certificados", icon: ShieldCheck },
      { title: "Empresas / CNPJs", href: "/cadastros/empresas", icon: Building },
      { title: "Chave da API", href: "/cadastros/api-keys", icon: Key },
      { title: "Configurações", href: "/cadastros/configuracoes", icon: Settings },
    ],
  },
  {
    label: "Monitoramento",
    items: [
      { title: "Logs de Captura", href: "/logs", icon: ScrollText },
    ],
  },
  {
    label: "Financeiro",
    items: [
      { title: "Assinatura", href: "/financeiro/creditos", icon: Receipt },
    ],
  },
  {
    label: "Ajuda",
    items: [
      { title: "Primeiros Passos", href: "/getting-started", icon: Rocket },
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
        render={<Link href={item.href} />}
      >
        <Icon className="size-4" />
        <span>{item.title}</span>
        {item.badge && (
          <Badge
            variant="secondary"
            className={cn(
              "ml-auto text-[10px] px-1.5 py-0",
              item.badge === "SAP" && "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
              item.badge === "ADN" && "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400"
            )}
            title={
              item.badge === "SAP"
                ? "Integração nativa com SAP DRC disponível"
                : item.badge === "ADN"
                  ? "Captura via Ambiente Nacional de NFS-e"
                  : undefined
            }
          >
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
  const [mounted, setMounted] = React.useState(false)

  React.useEffect(() => {
    setMounted(true)
    if (supabase) {
      supabase.auth.getUser().then(({ data }) => {
        setEmail(data.user?.email ?? null)
      })
    } else {
      setEmail("demo@dfeaxis.com.br")
    }
  }, [])

  const handleLogout = async () => {
    if (supabase) {
      await supabase.auth.signOut()
    }
    router.push("/login")
  }

  const initials = email
    ? email.slice(0, 2).toUpperCase()
    : "U"

  if (!mounted) {
    return (
      <SidebarFooter>
        <SidebarSeparator />
        <div className="flex items-center gap-3 px-2 py-2 text-sm">
          <div className="size-8 rounded-full bg-muted animate-pulse" />
          <div className="flex-1 h-4 bg-muted rounded animate-pulse" />
        </div>
      </SidebarFooter>
    )
  }

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

const ADMIN_EMAILS = ["ferezinth@hotmail.com", "ferezaeai@gmail.com"]

export function AppSidebar() {
  const pathname = usePathname()
  const { settings } = useSettings()
  const [isAdmin, setIsAdmin] = React.useState(false)

  React.useEffect(() => {
    if (supabase) {
      supabase.auth.getUser().then(({ data }) => {
        if (data.user && ADMIN_EMAILS.includes(data.user.email ?? "")) {
          setIsAdmin(true)
        }
      })
    }
  }, [])

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="p-4">
        <Link href="/" className="flex items-center gap-2">
          <Image src="/logo-dfeaxis.png" alt="DFeAxis" width={140} height={40} className="object-contain" unoptimized />
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

        {/* Captura — sempre sob demanda */}
        <SidebarGroup>
          <SidebarGroupLabel>Execução</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton
                  isActive={pathname === "/execucao/captura"}
                  render={<Link href="/execucao/captura" />}
                >
                  <Play className="size-4" />
                  <span>Captura Manual</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton
                  isActive={pathname === "/historico/manifestacao"}
                  render={<Link href="/historico/manifestacao" />}
                >
                  <FileCheck className="size-4" />
                  <span>Manifestação</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        {/* Admin — only visible for admin users */}
        {isAdmin && (
          <SidebarGroup>
            <SidebarGroupLabel>Administração</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                <SidebarMenuItem>
                  <SidebarMenuButton
                    isActive={pathname?.startsWith("/admin")}
                    render={<Link href="/admin" />}
                  >
                    <Shield className="size-4" />
                    <span>Admin</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        )}
      </SidebarContent>

      <UserFooter />
    </Sidebar>
  )
}
