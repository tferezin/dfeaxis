"use client"

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import { Inbox } from "lucide-react"

type DocumentStatus = "Disponivel" | "Entregue" | "Pendente" | "Cancelada"

interface RecentDocument {
  emitente: string
  cnpj: string
  emissao: string
  tipo: string
  nota: string
  chave: string
  valor: string
  status: DocumentStatus
}

const statusStyles: Record<DocumentStatus, string> = {
  Disponivel: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  Entregue: "bg-blue-50 text-blue-700 ring-blue-600/20",
  Pendente: "bg-amber-50 text-amber-700 ring-amber-600/20",
  Cancelada: "bg-red-50 text-red-700 ring-red-600/20",
}

const mockDocuments: RecentDocument[] = [
  {
    emitente: "Distribuidora Alimentos Paulista Ltda",
    cnpj: "12.345.678/0001-90",
    emissao: "15/03/2026",
    tipo: "NF-e",
    nota: "001.234",
    chave: "3526...8901",
    valor: "R$ 12.450,00",
    status: "Disponivel",
  },
  {
    emitente: "Transportadora Rodoviaria Sul S/A",
    cnpj: "98.765.432/0001-10",
    emissao: "15/03/2026",
    tipo: "CT-e",
    nota: "005.678",
    chave: "3526...4532",
    valor: "R$ 3.280,50",
    status: "Entregue",
  },
  {
    emitente: "Industria Metalurgica Nacional Ltda",
    cnpj: "11.222.333/0001-44",
    emissao: "14/03/2026",
    tipo: "NF-e",
    nota: "089.012",
    chave: "3526...7654",
    valor: "R$ 87.320,00",
    status: "Disponivel",
  },
  {
    emitente: "Comercial de Bebidas Nordeste",
    cnpj: "55.444.333/0001-22",
    emissao: "14/03/2026",
    tipo: "NF-e",
    nota: "034.567",
    chave: "3526...1234",
    valor: "R$ 5.670,80",
    status: "Pendente",
  },
  {
    emitente: "Agropecuaria Campo Verde Ltda",
    cnpj: "77.888.999/0001-55",
    emissao: "14/03/2026",
    tipo: "NF-e",
    nota: "012.890",
    chave: "3526...9876",
    valor: "R$ 234.100,00",
    status: "Cancelada",
  },
  {
    emitente: "Express Log Transportes Eireli",
    cnpj: "33.222.111/0001-88",
    emissao: "13/03/2026",
    tipo: "CT-e",
    nota: "007.321",
    chave: "3526...5643",
    valor: "R$ 1.890,00",
    status: "Entregue",
  },
  {
    emitente: "Supermercados Economia S/A",
    cnpj: "44.555.666/0001-77",
    emissao: "13/03/2026",
    tipo: "NF-e",
    nota: "056.789",
    chave: "3526...3210",
    valor: "R$ 15.430,25",
    status: "Disponivel",
  },
  {
    emitente: "Construtora Horizonte Ltda",
    cnpj: "66.777.888/0001-33",
    emissao: "12/03/2026",
    tipo: "NF-e",
    nota: "023.456",
    chave: "3526...6789",
    valor: "R$ 45.000,00",
    status: "Disponivel",
  },
  {
    emitente: "Farmaceutica Vida & Saude",
    cnpj: "22.111.000/0001-66",
    emissao: "12/03/2026",
    tipo: "NF-e",
    nota: "078.234",
    chave: "3526...2345",
    valor: "R$ 8.920,60",
    status: "Pendente",
  },
  {
    emitente: "TechParts Componentes Eletronicos",
    cnpj: "88.999.000/0001-11",
    emissao: "11/03/2026",
    tipo: "NF-e",
    nota: "045.678",
    chave: "3526...8765",
    valor: "R$ 67.540,00",
    status: "Entregue",
  },
]

export function RecentDocuments({ empty = false }: { empty?: boolean }) {
  return (
    <Card className="transition-shadow hover:shadow-md">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-base font-semibold">
              Documentos Recentes
            </CardTitle>
            <CardDescription>
              Ultimos documentos fiscais recebidos
            </CardDescription>
          </div>
          <button className="text-sm font-medium text-primary hover:underline">
            Ver todos
          </button>
        </div>
      </CardHeader>
      <CardContent className="px-0">
        {empty ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <Inbox className="size-12 text-muted-foreground/30 mb-4" />
            <p className="text-sm text-muted-foreground">Nenhum documento recente.</p>
          </div>
        ) : (
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="pl-4">Emitente</TableHead>
              <TableHead>Emissao</TableHead>
              <TableHead>Tipo</TableHead>
              <TableHead>Nota</TableHead>
              <TableHead>Chave</TableHead>
              <TableHead className="text-right">Valor</TableHead>
              <TableHead className="pr-4 text-right">Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {mockDocuments.map((doc, i) => (
              <TableRow key={i} className="group cursor-pointer">
                <TableCell className="pl-4">
                  <div>
                    <p className="font-medium text-foreground">{doc.emitente}</p>
                    <p className="text-xs text-muted-foreground">{doc.cnpj}</p>
                  </div>
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {doc.emissao}
                </TableCell>
                <TableCell>
                  <span
                    className={cn(
                      "inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold",
                      doc.tipo === "NF-e"
                        ? "bg-blue-50 text-blue-700"
                        : "bg-violet-50 text-violet-700"
                    )}
                  >
                    {doc.tipo}
                  </span>
                </TableCell>
                <TableCell className="font-mono text-sm text-muted-foreground">
                  {doc.nota}
                </TableCell>
                <TableCell className="font-mono text-xs text-muted-foreground">
                  {doc.chave}
                </TableCell>
                <TableCell className="text-right font-semibold tabular-nums">
                  {doc.valor}
                </TableCell>
                <TableCell className="pr-4 text-right">
                  <span
                    className={cn(
                      "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset",
                      statusStyles[doc.status]
                    )}
                  >
                    {doc.status}
                  </span>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        )}
      </CardContent>
    </Card>
  )
}
