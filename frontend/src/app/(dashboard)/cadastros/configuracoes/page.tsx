"use client"

import { useState } from "react"
import { Save, Clock, Globe, Bell, AlertTriangle } from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Input } from "@/components/ui/input"
import { Separator } from "@/components/ui/separator"
import { useSettings } from "@/hooks/use-settings"

type SelectOption = { value: string; label: string; description?: string }

function SettingsSelect({
  label,
  description,
  options,
  value,
  onChange,
}: {
  label: string
  description?: string
  options: SelectOption[]
  value: string
  onChange: (v: string) => void
}) {
  return (
    <div className="space-y-1.5">
      <Label className="text-sm font-medium">{label}</Label>
      {description && <p className="text-xs text-muted-foreground">{description}</p>}
      <div className="grid gap-1.5">
        {options.map((opt) => (
          <label
            key={opt.value}
            className={`flex items-center gap-3 rounded-lg border px-3 py-2 cursor-pointer transition-colors ${
              value === opt.value
                ? "border-primary bg-primary/5"
                : "border-border hover:border-muted-foreground/30"
            }`}
          >
            <input
              type="radio"
              name={label}
              value={opt.value}
              checked={value === opt.value}
              onChange={() => onChange(opt.value)}
              className="shrink-0"
            />
            <div>
              <span className="text-sm font-medium">{opt.label}</span>
              {opt.description && (
                <p className="text-xs text-muted-foreground mt-0.5">{opt.description}</p>
              )}
            </div>
          </label>
        ))}
      </div>
    </div>
  )
}

export default function ConfiguracoesPage() {
  const { settings, updateSettings } = useSettings()
  const [saved, setSaved] = useState(false)

  const handleSave = () => {
    // Settings already persisted via useSettings — this would call the API
    setSaved(true)
    setTimeout(() => setSaved(false), 3000)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Configurações</h1>
          <p className="text-sm text-muted-foreground">
            Gerencie as configurações de captura e integração.
          </p>
        </div>
        <Button onClick={handleSave} className="gap-2" size="sm">
          <Save className="size-4" />
          {saved ? "Salvo!" : "Salvar alterações"}
        </Button>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {/* Modo de Operação (unifica captura + manifestação) */}
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center gap-2">
              <Clock className="size-5 text-primary" />
              <CardTitle className="text-base">Modo de Operação</CardTitle>
            </div>
            <CardDescription>
              Define como o DFeAxis captura documentos e responde à SEFAZ.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 pt-0">
            <SettingsSelect
              label="Modo"
              options={[
                {
                  value: "auto",
                  label: "Automático",
                  description:
                    "Captura documentos a cada 15 min e envia Ciência da Operação automaticamente. Recomendado para produção.",
                },
                {
                  value: "manual",
                  label: "Manual",
                  description:
                    "Você dispara a captura quando desejar e decide quais notas aceitar. Ideal para testes.",
                },
              ]}
              value={settings.operationMode}
              onChange={(v) => updateSettings({ operationMode: v as "auto" | "manual" })}
            />

            {settings.operationMode === "auto" && (
              <div className="space-y-1.5">
                <Label className="text-sm font-medium">Intervalo de captura</Label>
                <div className="flex items-center gap-2">
                  <Input
                    type="number"
                    min="15"
                    max="60"
                    value={settings.capturaInterval}
                    onChange={(e) => updateSettings({ capturaInterval: e.target.value })}
                    className="w-20"
                  />
                  <span className="text-sm text-muted-foreground">minutos (mín. 15)</span>
                </div>
              </div>
            )}

            {settings.operationMode === "manual" && (
              <div className="rounded-lg border border-blue-200 bg-blue-50 p-3">
                <p className="text-xs text-blue-800">
                  Use o menu <strong>Captura Manual</strong> na barra lateral para disparar a captura por CNPJ ou para todos de uma vez.
                </p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Ambiente SEFAZ */}
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center gap-2">
              <Globe className="size-5 text-primary" />
              <CardTitle className="text-base">Ambiente SEFAZ</CardTitle>
            </div>
            <CardDescription>
              Selecione o ambiente de comunicação com a SEFAZ e o ADN de NFS-e.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 pt-0">
            <SettingsSelect
              label="Ambiente"
              options={[
                {
                  value: "2",
                  label: "Homologação (testes)",
                  description: "Ambiente de testes. Não processa documentos reais.",
                },
                {
                  value: "1",
                  label: "Produção",
                  description: "Ambiente real. Documentos de fornecedores serão capturados.",
                },
              ]}
              value={settings.sefazAmbiente}
              onChange={(v) => updateSettings({ sefazAmbiente: v as "1" | "2" })}
            />

            {settings.sefazAmbiente === "1" && (
              <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-2.5">
                <AlertTriangle className="size-4 text-amber-600 mt-0.5 shrink-0" />
                <p className="text-xs text-amber-800">
                  <strong>Atenção:</strong> Produção captura documentos fiscais reais.
                </p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Notificações */}
        <Card className="md:col-span-2">
          <CardHeader className="pb-2">
            <div className="flex items-center gap-2">
              <Bell className="size-5 text-primary" />
              <CardTitle className="text-base">Notificações</CardTitle>
            </div>
            <CardDescription>Configure alertas por e-mail.</CardDescription>
          </CardHeader>
          <CardContent className="pt-0">
            <div className="flex flex-wrap items-end gap-4">
              <div className="space-y-1.5 flex-1 min-w-[200px]">
                <Label className="text-sm font-medium">E-mail</Label>
                <Input
                  type="email"
                  placeholder="admin@suaempresa.com.br"
                  value={settings.notifyEmail}
                  onChange={(e) => updateSettings({ notifyEmail: e.target.value })}
                />
              </div>
              <Separator orientation="vertical" className="h-8 hidden md:block" />
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={settings.notifyCertExpiry}
                  onChange={(e) => updateSettings({ notifyCertExpiry: e.target.checked })}
                  className="size-4"
                />
                <span className="text-sm">Vencimento de certificado</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={settings.notifyNoCredits}
                  onChange={(e) => updateSettings({ notifyNoCredits: e.target.checked })}
                  className="size-4"
                />
                <span className="text-sm">Créditos insuficientes</span>
              </label>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
