"use client"

import { Button } from "@/components/ui/button"
import { Building2, Bell } from "lucide-react"

export default function HistoricoNfsePage() {
  return (
    <div className="flex min-h-[calc(100vh-4rem)] flex-col items-center justify-center gap-6 p-6">
      <div className="flex flex-col items-center gap-4 text-center">
        <div className="flex size-20 items-center justify-center rounded-2xl bg-muted">
          <Building2 className="size-10 text-muted-foreground" />
        </div>
        <div className="flex flex-col gap-2">
          <h1 className="text-2xl font-semibold tracking-tight">
            NFS-e — Em Breve
          </h1>
          <p className="max-w-md text-sm text-muted-foreground">
            Estamos trabalhando na integracao com o Ambiente Nacional e as principais
            prefeituras. Em breve voce podera consultar e gerenciar suas Notas Fiscais
            de Servico diretamente por aqui.
          </p>
        </div>
        <Button variant="outline" disabled className="mt-2 gap-2">
          <Bell className="size-4" />
          Notificar-me
        </Button>
      </div>
    </div>
  )
}
