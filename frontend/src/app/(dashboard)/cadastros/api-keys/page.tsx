"use client"

import { useState } from "react"
import { useSettings } from "@/hooks/use-settings"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet"
import {
  Plus,
  Copy,
  Trash2,
  Check,
  Key,
} from "lucide-react"

interface ApiKey {
  id: number
  prefix: string
  descricao: string
  ultimoUso: string | null
  status: "Ativa" | "Revogada"
  criacao: string
}

const mockKeys: ApiKey[] = [
  {
    id: 1,
    prefix: "dfe_live_7kX3...m9Pq",
    descricao: "Produção - ERP Principal",
    ultimoUso: "16/03/2026 08:45",
    status: "Ativa",
    criacao: "01/01/2026",
  },
  {
    id: 2,
    prefix: "dfe_live_2bR8...n4Wz",
    descricao: "Produção - Integração Contábil",
    ultimoUso: "15/03/2026 22:10",
    status: "Ativa",
    criacao: "15/01/2026",
  },
  {
    id: 3,
    prefix: "dfe_test_9mK1...j5Yt",
    descricao: "Homologação - Testes QA",
    ultimoUso: "14/03/2026 16:30",
    status: "Ativa",
    criacao: "01/02/2026",
  },
  {
    id: 4,
    prefix: "dfe_live_4hN6...s8Lp",
    descricao: "Produção - App Mobile",
    ultimoUso: "10/03/2026 09:15",
    status: "Ativa",
    criacao: "20/02/2026",
  },
  {
    id: 5,
    prefix: "dfe_test_1cF3...w7Rx",
    descricao: "Homologação - Sprint 12",
    ultimoUso: "05/03/2026 11:00",
    status: "Revogada",
    criacao: "01/03/2026",
  },
  {
    id: 6,
    prefix: "dfe_live_6qD9...v2Hn",
    descricao: "Produção - Webhook Server",
    ultimoUso: null,
    status: "Revogada",
    criacao: "10/12/2025",
  },
]

export default function ApiKeysPage() {
  const { settings } = useSettings()
  const [sheetOpen, setSheetOpen] = useState(false)
  const [newKeyCreated, setNewKeyCreated] = useState<string | null>(null)
  const [copiedId, setCopiedId] = useState<number | null>(null)
  const [confirmRevokeId, setConfirmRevokeId] = useState<number | null>(null)

  const handleCreateKey = () => {
    setNewKeyCreated("dfe_live_8xT5mNqR2vBcYwK7jL9pA3dFgH0sU6iE1oW4zXnJkM")
  }

  const handleCopy = (id: number, text: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  const handleRevoke = (id: number) => {
    if (confirmRevokeId === id) {
      setConfirmRevokeId(null)
      // Would call API here
    } else {
      setConfirmRevokeId(id)
      setTimeout(() => setConfirmRevokeId(null), 3000)
    }
  }

  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">API Keys</h1>
          <p className="text-sm text-muted-foreground">
            Gerencie as chaves de acesso para integração com a API do DFeAxis
          </p>
        </div>
        <Sheet open={sheetOpen} onOpenChange={(open) => { setSheetOpen(open); if (!open) setNewKeyCreated(null) }}>
          <SheetTrigger
            render={
              <Button>
                <Plus className="size-4" />
                Nova Key
              </Button>
            }
          />
          <SheetContent side="right">
            <SheetHeader>
              <SheetTitle>Criar API Key</SheetTitle>
              <SheetDescription>
                Gere uma nova chave de acesso para integrar com a API.
              </SheetDescription>
            </SheetHeader>
            <div className="flex flex-col gap-4 px-4">
              {!newKeyCreated ? (
                <>
                  <div className="flex flex-col gap-2">
                    <Label htmlFor="key-desc">Descrição</Label>
                    <Input
                      id="key-desc"
                      placeholder="Ex: Produção - ERP Principal"
                    />
                  </div>
                  <p className="text-xs text-muted-foreground">
                    A chave será exibida apenas uma vez após a criação. Certifique-se de
                    copiar e armazenar em local seguro.
                  </p>
                </>
              ) : (
                <div className="flex flex-col gap-3">
                  <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 dark:border-emerald-800 dark:bg-emerald-950/30">
                    <p className="mb-2 text-xs font-medium text-emerald-700 dark:text-emerald-300">
                      Chave criada com sucesso! Copie-a agora - ela não será exibida novamente.
                    </p>
                    <div className="flex items-center gap-2">
                      <code className="flex-1 break-all rounded bg-white px-2 py-1.5 font-mono text-xs dark:bg-black">
                        {newKeyCreated}
                      </code>
                      <Button
                        variant="outline"
                        size="icon-sm"
                        onClick={() => handleCopy(-1, newKeyCreated)}
                      >
                        {copiedId === -1 ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
                      </Button>
                    </div>
                  </div>
                </div>
              )}
            </div>
            <SheetFooter>
              {!newKeyCreated ? (
                <Button className="w-full gap-2" onClick={handleCreateKey}>
                  <Key className="size-4" />
                  Gerar Key
                </Button>
              ) : (
                <Button variant="outline" className="w-full" onClick={() => { setSheetOpen(false); setNewKeyCreated(null) }}>
                  Fechar
                </Button>
              )}
            </SheetFooter>
          </SheetContent>
        </Sheet>
      </div>

      {/* Table */}
      {!settings.showMockData ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <Key className="size-12 text-muted-foreground/30 mb-4" />
          <p className="text-sm text-muted-foreground">Nenhuma API Key cadastrada. Clique em &quot;Nova Key&quot; para criar.</p>
        </div>
      ) : (
      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Prefixo</TableHead>
              <TableHead>Descrição</TableHead>
              <TableHead>Último uso</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Criação</TableHead>
              <TableHead>Ações</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {mockKeys.map((apiKey) => (
              <TableRow key={apiKey.id}>
                <TableCell>
                  <div className="flex items-center gap-2">
                    <Key className="size-3.5 text-muted-foreground" />
                    <code className="font-mono text-xs">{apiKey.prefix}</code>
                  </div>
                </TableCell>
                <TableCell className="font-medium">{apiKey.descricao}</TableCell>
                <TableCell className="text-muted-foreground">
                  {apiKey.ultimoUso ?? "Nunca utilizada"}
                </TableCell>
                <TableCell>
                  <Badge variant={apiKey.status === "Ativa" ? "default" : "destructive"}>
                    {apiKey.status}
                  </Badge>
                </TableCell>
                <TableCell>{apiKey.criacao}</TableCell>
                <TableCell>
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="icon-xs"
                      title="Copiar prefixo"
                      onClick={() => handleCopy(apiKey.id, apiKey.prefix)}
                    >
                      {copiedId === apiKey.id ? (
                        <Check className="size-3.5 text-emerald-600" />
                      ) : (
                        <Copy className="size-3.5" />
                      )}
                    </Button>
                    {apiKey.status === "Ativa" && (
                      <Button
                        variant={confirmRevokeId === apiKey.id ? "destructive" : "ghost"}
                        size={confirmRevokeId === apiKey.id ? "sm" : "icon-xs"}
                        title="Revogar"
                        onClick={() => handleRevoke(apiKey.id)}
                      >
                        {confirmRevokeId === apiKey.id ? (
                          <span className="text-xs">Confirmar?</span>
                        ) : (
                          <Trash2 className="size-3.5" />
                        )}
                      </Button>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      )}

      {/* Info text */}
      <p className="text-xs text-muted-foreground">
        As API Keys concedem acesso a todos os endpoints da API do DFeAxis vinculados
        à sua conta. Revogue imediatamente qualquer chave comprometida.
      </p>
    </div>
  )
}
