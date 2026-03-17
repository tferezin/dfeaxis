"use client"

import Image from "next/image"
import Link from "next/link"
import { ArrowRight, ShieldCheck, Zap, FileText, Truck, Receipt, BarChart3 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"

const features = [
  {
    icon: Zap,
    title: "Captura Automática",
    description: "Busca documentos na SEFAZ a cada 15 minutos, sem intervenção manual.",
  },
  {
    icon: ShieldCheck,
    title: "Certificado A1 Seguro",
    description: "Cifragem AES-256-GCM com PBKDF2 600k iterações. Seus certificados nunca ficam em texto claro.",
  },
  {
    icon: FileText,
    title: "NF-e, CT-e, MDF-e, NFS-e",
    description: "Captura todos os tipos de documentos fiscais recebidos de fornecedores.",
  },
  {
    icon: BarChart3,
    title: "Integração SAP DRC",
    description: "API compatível com SAP Document and Reporting Compliance para entrega automática.",
  },
]

export default function LandingPage() {
  return (
    <div className="min-h-svh bg-background">
      {/* Header */}
      <header className="border-b">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
          <Image src="/logo-dfeaxis.png" alt="DFeAxis" width={140} height={40} className="object-contain" unoptimized />
          <Link href="/login">
            <Button>Entrar</Button>
          </Link>
        </div>
      </header>

      {/* Hero */}
      <section className="mx-auto max-w-6xl px-6 py-20 text-center">
        <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">
          Seus fornecedores emitem.
          <br />
          <span className="text-primary">O DFeAxis entrega no SAP.</span>
        </h1>
        <p className="mx-auto mt-4 max-w-2xl text-lg text-muted-foreground">
          Captura automática de documentos fiscais recebidos da SEFAZ para SAP DRC.
          Sem ninguém precisar buscar.
        </p>
        <div className="mt-8 flex items-center justify-center gap-4">
          <Link href="/login">
            <Button size="lg" className="gap-2">
              Acessar o painel
              <ArrowRight className="size-4" />
            </Button>
          </Link>
        </div>
      </section>

      {/* Features */}
      <section className="border-t bg-muted/30 py-16">
        <div className="mx-auto max-w-6xl px-6">
          <h2 className="text-center text-2xl font-semibold tracking-tight">
            Tudo que você precisa para capturar documentos fiscais
          </h2>
          <div className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {features.map((f) => {
              const Icon = f.icon
              return (
                <Card key={f.title}>
                  <CardContent className="pt-6">
                    <div className="size-10 rounded-lg bg-primary/10 flex items-center justify-center mb-3">
                      <Icon className="size-5 text-primary" />
                    </div>
                    <h3 className="font-semibold">{f.title}</h3>
                    <p className="mt-1 text-sm text-muted-foreground">{f.description}</p>
                  </CardContent>
                </Card>
              )
            })}
          </div>
        </div>
      </section>

      {/* Document types */}
      <section className="py-16">
        <div className="mx-auto max-w-6xl px-6 text-center">
          <h2 className="text-2xl font-semibold tracking-tight">Documentos suportados</h2>
          <p className="mt-2 text-sm text-muted-foreground">Captura todos os tipos de documentos fiscais eletrônicos recebidos</p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-6">
            {[
              { label: "NF-e", icon: FileText, badge: "SAP DRC", color: "text-blue-600 bg-blue-50" },
              { label: "CT-e", icon: Truck, badge: "SAP DRC", color: "text-violet-600 bg-violet-50" },
              { label: "MDF-e", icon: FileText, color: "text-emerald-600 bg-emerald-50" },
              { label: "NFS-e", icon: Receipt, badge: "ADN", color: "text-amber-600 bg-amber-50" },
            ].map((doc) => {
              const Icon = doc.icon
              return (
                <div key={doc.label} className={`flex items-center gap-3 rounded-xl border px-6 py-4 ${doc.color}`}>
                  <Icon className="size-6" />
                  <span className="text-lg font-semibold">{doc.label}</span>
                  {doc.badge && (
                    <span className="rounded-full bg-background border px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                      {doc.badge}
                    </span>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t py-6">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 text-xs text-muted-foreground">
          <span>Developed by <strong>FerezaAI</strong></span>
          <span>&copy; {new Date().getFullYear()} DFeAxis. Todos os direitos reservados.</span>
        </div>
      </footer>
    </div>
  )
}
