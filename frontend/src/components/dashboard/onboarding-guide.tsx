"use client"

import Link from "next/link"
import { Settings, ShieldCheck, Play, FileText, CheckCircle2 } from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"

const steps = [
  {
    number: 1,
    title: "Configurações",
    description: "Verifique o ambiente (Homologação) e o modo de operação (Manual para testes).",
    icon: Settings,
    href: "/cadastros/configuracoes",
    color: "text-blue-600 bg-blue-100",
  },
  {
    number: 2,
    title: "Certificado A1",
    description: "Cadastre o certificado digital (.pfx) da empresa para conectar à SEFAZ.",
    icon: ShieldCheck,
    href: "/cadastros/certificados",
    color: "text-emerald-600 bg-emerald-100",
  },
  {
    number: 3,
    title: "Captura Manual",
    description: "Dispare a primeira captura para buscar documentos na SEFAZ.",
    icon: Play,
    href: "/execucao/captura",
    color: "text-amber-600 bg-amber-100",
  },
  {
    number: 4,
    title: "Ver Resultados",
    description: "Confira os documentos capturados em NF-e Recebidas, CT-e e outros.",
    icon: FileText,
    href: "/historico/nfe",
    color: "text-purple-600 bg-purple-100",
  },
]

export function OnboardingGuide() {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <CheckCircle2 className="size-5 text-primary" />
        <h2 className="text-lg font-semibold">Primeiros passos</h2>
      </div>
      <p className="text-sm text-muted-foreground">
        Siga os passos abaixo para configurar e testar a captura de documentos.
      </p>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {steps.map((step) => {
          const Icon = step.icon
          return (
            <Link key={step.number} href={step.href}>
              <Card className="h-full transition-colors hover:border-primary/50 hover:shadow-sm cursor-pointer">
                <CardContent className="pt-5 pb-4 px-4">
                  <div className="flex items-start gap-3">
                    <div className={`shrink-0 size-10 rounded-lg flex items-center justify-center ${step.color}`}>
                      <Icon className="size-5" />
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold text-muted-foreground">PASSO {step.number}</span>
                      </div>
                      <p className="text-sm font-semibold mt-0.5">{step.title}</p>
                      <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                        {step.description}
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </Link>
          )
        })}
      </div>
    </div>
  )
}
