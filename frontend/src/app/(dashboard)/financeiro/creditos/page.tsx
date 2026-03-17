"use client"

import { Construction, CreditCard } from "lucide-react"

export default function CreditosPage() {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <div className="size-16 rounded-2xl bg-amber-100 flex items-center justify-center mb-4">
        <Construction className="size-8 text-amber-600" />
      </div>
      <h1 className="text-xl font-semibold tracking-tight">Créditos — Em desenvolvimento</h1>
      <p className="text-sm text-muted-foreground mt-2 max-w-md">
        O módulo de créditos e faturamento está sendo construído. Em breve você poderá gerenciar seu saldo, comprar créditos e acompanhar o consumo.
      </p>
      <div className="flex items-center gap-2 mt-6 rounded-lg border bg-muted/30 px-4 py-2.5 text-sm text-muted-foreground">
        <CreditCard className="size-4" />
        <span>Pagamentos via cartão de crédito e faturamento recorrente</span>
      </div>
    </div>
  )
}
