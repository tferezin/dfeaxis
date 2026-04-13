"use client"

import { useState } from "react"
import { Save, Clock, Globe, Bell, AlertTriangle, Eye, FileCheck } from "lucide-react"
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
        {/* Modelo operacional (informativo — captura é sempre on-demand) */}
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center gap-2">
              <Clock className="size-5 text-primary" />
              <CardTitle className="text-base">Modelo de Captura</CardTitle>
            </div>
            <CardDescription>
              Como o DFeAxis consulta a SEFAZ e entrega documentos.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 pt-0 text-sm text-muted-foreground">
            <div className="flex gap-2">
              <span className="font-medium text-foreground shrink-0">On-demand:</span>
              <span>Toda captura é iniciada pelo seu ERP via <code className="text-[11px] bg-muted px-1 py-0.5 rounded">POST /api/v1/polling/trigger</code>. Você controla a frequência — não fazemos polling automático na SEFAZ.</span>
            </div>
            <div className="flex gap-2">
              <span className="font-medium text-foreground shrink-0">Ciência automática:</span>
              <span>Durante cada captura acionada pelo cliente, o DFeAxis envia a Ciência da Operação (evento 210210) automaticamente. É obrigatório pela SEFAZ pra liberar o XML completo.</span>
            </div>
            <div className="flex gap-2">
              <span className="font-medium text-foreground shrink-0">Frequência recomendada:</span>
              <span>Agende um job no seu SAP/TOTVS/ERP pra chamar a captura a cada 30 min, 1h, ou conforme o volume da sua operação. Evita consumo indevido SEFAZ e otimiza custo.</span>
            </div>
            <div className="rounded-lg border border-blue-200 bg-blue-50 p-3 mt-3">
              <p className="text-xs text-blue-800">
                Pra testar manualmente a captura agora, use <strong>Captura Manual</strong> no menu lateral. Em produção, deixe seu ERP disparar via API.
              </p>
            </div>
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

        {/* Dados de demonstração */}
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center gap-2">
              <Eye className="size-5 text-primary" />
              <CardTitle className="text-base">Dados de demonstração</CardTitle>
            </div>
            <CardDescription>
              Controle a exibição de dados fictícios nas telas de histórico.
            </CardDescription>
          </CardHeader>
          <CardContent className="pt-0">
            <label className="flex items-start gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={settings.showMockData}
                onChange={(e) => updateSettings({ showMockData: e.target.checked })}
                className="size-4 mt-0.5 shrink-0"
              />
              <div>
                <span className="text-sm font-medium">Exibir dados de demonstração</span>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Desative para testar com dados da SEFAZ (homologação ou produção). Quando desativado, apenas documentos capturados do ambiente configurado serão exibidos.
                </p>
              </div>
            </label>
          </CardContent>
        </Card>

        {/* Manifestação do Destinatário — informativo */}
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center gap-2">
              <FileCheck className="size-5 text-primary" />
              <CardTitle className="text-base">Manifestação do Destinatário</CardTitle>
            </div>
            <CardDescription>
              Como o DFeAxis trata os eventos de manifestação de NF-e.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 pt-0 text-sm text-muted-foreground">
            <div className="flex gap-2">
              <span className="font-medium text-foreground shrink-0">Ciência (210210):</span>
              <span>Enviada <strong>automaticamente</strong> durante cada captura. É obrigatória pela SEFAZ para liberar o XML completo.</span>
            </div>
            <div className="flex gap-2">
              <span className="font-medium text-foreground shrink-0">Manifesto definitivo:</span>
              <span>Confirmar, Desconhecer ou Operação não Realizada. Pode ser feito <strong>manualmente pelo painel</strong> ou <strong>automaticamente via API</strong> (SAP após MIRO).</span>
            </div>
            <div className="flex gap-2">
              <span className="font-medium text-foreground shrink-0">Prazo SEFAZ:</span>
              <span>180 dias após a ciência. Você receberá alertas por e-mail quando algum documento estiver próximo do vencimento.</span>
            </div>
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
