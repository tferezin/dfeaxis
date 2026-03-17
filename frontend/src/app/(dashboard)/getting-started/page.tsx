"use client"

import Link from "next/link"
import { Settings, ShieldCheck, Play, FileText, CheckCircle2, ArrowRight } from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"

const steps = [
  {
    number: 1,
    title: "Verifique as Configurações",
    description: "Confirme que o ambiente está em Homologação e o modo de operação em Manual. Isso garante que você teste com segurança antes de ir para produção.",
    icon: Settings,
    href: "/cadastros/configuracoes",
    color: "text-blue-600 bg-blue-100 border-blue-200",
  },
  {
    number: 2,
    title: "Cadastre um Certificado A1",
    description: "Faça o upload do arquivo .pfx do certificado digital da empresa. O DFeAxis usará ele para se conectar à SEFAZ via mTLS.",
    icon: ShieldCheck,
    href: "/cadastros/certificados",
    color: "text-emerald-600 bg-emerald-100 border-emerald-200",
  },
  {
    number: 3,
    title: "Execute uma Captura Manual",
    description: "Acesse a captura manual, selecione o CNPJ e clique em Capturar. O DFeAxis vai consultar a SEFAZ e trazer os documentos recebidos.",
    icon: Play,
    href: "/execucao/captura",
    color: "text-amber-600 bg-amber-100 border-amber-200",
  },
  {
    number: 4,
    title: "Confira os Resultados",
    description: "Vá em NF-e Recebidas para ver os documentos capturados. Se estiver em homologação e não houver documentos, é normal — a base de testes pode estar vazia.",
    icon: FileText,
    href: "/historico/nfe",
    color: "text-purple-600 bg-purple-100 border-purple-200",
  },
]

export default function GettingStartedPage() {
  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2">
          <CheckCircle2 className="size-6 text-primary" />
          <h1 className="text-2xl font-semibold tracking-tight">Primeiros Passos</h1>
        </div>
        <p className="text-sm text-muted-foreground mt-1">
          Siga os passos abaixo para configurar e testar a captura de documentos fiscais recebidos.
        </p>
      </div>

      <div className="grid gap-4">
        {steps.map((step, index) => {
          const Icon = step.icon
          return (
            <Link key={step.number} href={step.href}>
              <Card className="transition-all hover:border-primary/50 hover:shadow-md cursor-pointer">
                <CardContent className="flex items-center gap-5 py-5">
                  <div className={`shrink-0 size-14 rounded-xl flex items-center justify-center border ${step.color}`}>
                    <Icon className="size-7" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Passo {step.number}</span>
                    </div>
                    <p className="text-base font-semibold mt-0.5">{step.title}</p>
                    <p className="text-sm text-muted-foreground mt-1 leading-relaxed">
                      {step.description}
                    </p>
                  </div>
                  <ArrowRight className="size-5 text-muted-foreground shrink-0" />
                </CardContent>
              </Card>
            </Link>
          )
        })}
      </div>

      <Card className="bg-muted/30">
        <CardContent className="py-4">
          <p className="text-sm text-muted-foreground">
            <strong>Dica:</strong> Em ambiente de homologação, a SEFAZ pode não ter documentos para o CNPJ consultado. Isso é normal. O importante é validar que a conexão (mTLS) funciona corretamente (status 137 = conectou com sucesso, sem documentos novos).
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
