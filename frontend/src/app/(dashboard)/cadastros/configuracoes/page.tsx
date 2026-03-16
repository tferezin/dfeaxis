"use client"

import { useState } from "react"
import { Save, Shield, Bell, Clock, Globe, AlertTriangle, Play } from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Label } from "@/components/ui/label"
import { Input } from "@/components/ui/input"
import { Separator } from "@/components/ui/separator"

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
    <div className="space-y-2">
      <Label className="text-sm font-medium">{label}</Label>
      {description && <p className="text-xs text-muted-foreground">{description}</p>}
      <div className="grid gap-2">
        {options.map((opt) => (
          <label
            key={opt.value}
            className={`flex items-center gap-3 rounded-lg border p-3 cursor-pointer transition-colors ${
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
  const [saved, setSaved] = useState(false)

  // Settings state
  const [capturaMode, setCapturaMode] = useState("auto")
  const [manifestacaoMode, setManifestacaoMode] = useState("manual")
  const [sefazAmbiente, setSefazAmbiente] = useState("2")
  const [capturaInterval, setCapturaInterval] = useState("15")
  const [notifyEmail, setNotifyEmail] = useState("")
  const [notifyCertExpiry, setNotifyCertExpiry] = useState(true)
  const [notifyNoCredits, setNotifyNoCredits] = useState(true)

  const handleSave = () => {
    // TODO: call PATCH /api/v1/tenants/settings
    setSaved(true)
    setTimeout(() => setSaved(false), 3000)
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Configurações</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Gerencie as configurações de captura e integração do seu tenant.
          </p>
        </div>
        <Button onClick={handleSave} className="gap-2">
          <Save className="size-4" />
          {saved ? "Salvo!" : "Salvar alterações"}
        </Button>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        {/* Captura Automática */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Clock className="size-5 text-primary" />
              <CardTitle className="text-lg">Captura Automática</CardTitle>
            </div>
            <CardDescription>
              Configure como o DFeAxis busca documentos recebidos na SEFAZ.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <SettingsSelect
              label="Modo de captura"
              options={[
                {
                  value: "auto",
                  label: "Automático",
                  description:
                    "O DFeAxis consulta a SEFAZ automaticamente no intervalo definido. Recomendado para produção.",
                },
                {
                  value: "manual",
                  label: "Manual",
                  description:
                    "Captura apenas quando você dispara manualmente pelo painel ou API. Ideal para testes.",
                },
              ]}
              value={capturaMode}
              onChange={setCapturaMode}
            />

            {capturaMode === "auto" && (
              <div className="space-y-2">
                <Label className="text-sm font-medium">Intervalo de captura</Label>
                <div className="flex items-center gap-2">
                  <Input
                    type="number"
                    min="15"
                    max="60"
                    value={capturaInterval}
                    onChange={(e) => setCapturaInterval(e.target.value)}
                    className="w-20"
                  />
                  <span className="text-sm text-muted-foreground">minutos (mín. 15)</span>
                </div>
              </div>
            )}

            {capturaMode === "manual" && (
              <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 space-y-3">
                <p className="text-sm text-blue-800">
                  No modo manual, use o botão abaixo ou acesse <strong>Documentos Recebidos</strong> no menu para disparar a captura quando desejar.
                </p>
                <Button variant="outline" className="gap-2 border-blue-300 text-blue-700 hover:bg-blue-100">
                  <Play className="size-4" />
                  Capturar agora
                </Button>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Manifestação do Destinatário */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Shield className="size-5 text-primary" />
              <CardTitle className="text-lg">Manifestação do Destinatário</CardTitle>
            </div>
            <CardDescription>
              Define como o DFeAxis responde à SEFAZ ao detectar notas de fornecedores.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <SettingsSelect
              label="Modo de manifestação (NF-e)"
              description="A manifestação é obrigatória para obter o XML completo das NF-e recebidas."
              options={[
                {
                  value: "auto_ciencia",
                  label: "Ciência Automática",
                  description:
                    "Envia Ciência da Operação (210210) automaticamente ao detectar novas notas. O XML completo fica disponível mais rápido para o SAP.",
                },
                {
                  value: "manual",
                  label: "Manual",
                  description:
                    "Mostra os resumos das notas e aguarda sua decisão. Você escolhe quais aceitar antes de baixar o XML completo.",
                },
              ]}
              value={manifestacaoMode}
              onChange={setManifestacaoMode}
            />
          </CardContent>
        </Card>

        {/* Ambiente SEFAZ */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Globe className="size-5 text-primary" />
              <CardTitle className="text-lg">Ambiente SEFAZ</CardTitle>
            </div>
            <CardDescription>
              Selecione o ambiente de comunicação com a SEFAZ e o Ambiente Nacional de NFS-e.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <SettingsSelect
              label="Ambiente"
              options={[
                {
                  value: "2",
                  label: "Homologação (testes)",
                  description:
                    "Ambiente de testes da SEFAZ. Não processa documentos reais. Use para validar a integração.",
                },
                {
                  value: "1",
                  label: "Produção",
                  description:
                    "Ambiente real da SEFAZ. Documentos reais de fornecedores serão capturados.",
                },
              ]}
              value={sefazAmbiente}
              onChange={setSefazAmbiente}
            />

            {sefazAmbiente === "1" && (
              <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3">
                <AlertTriangle className="size-4 text-amber-600 mt-0.5 shrink-0" />
                <p className="text-xs text-amber-800">
                  <strong>Atenção:</strong> O ambiente de produção captura documentos fiscais reais.
                  Certifique-se de que seu certificado A1 e configurações estão corretos antes de ativar.
                </p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Notificações */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Bell className="size-5 text-primary" />
              <CardTitle className="text-lg">Notificações</CardTitle>
            </div>
            <CardDescription>Configure alertas por e-mail.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label className="text-sm font-medium">E-mail para notificações</Label>
              <Input
                type="email"
                placeholder="admin@suaempresa.com.br"
                value={notifyEmail}
                onChange={(e) => setNotifyEmail(e.target.value)}
              />
            </div>

            <Separator />

            <div className="space-y-3">
              <Label className="text-sm font-medium">Alertas ativos</Label>

              <label className="flex items-center justify-between gap-3 cursor-pointer">
                <div>
                  <p className="text-sm">Certificado próximo do vencimento</p>
                  <p className="text-xs text-muted-foreground">Avisa 30 e 7 dias antes</p>
                </div>
                <input
                  type="checkbox"
                  checked={notifyCertExpiry}
                  onChange={(e) => setNotifyCertExpiry(e.target.checked)}
                  className="size-4"
                />
              </label>

              <label className="flex items-center justify-between gap-3 cursor-pointer">
                <div>
                  <p className="text-sm">Créditos insuficientes</p>
                  <p className="text-xs text-muted-foreground">Avisa quando o saldo atingir 10% do consumo mensal</p>
                </div>
                <input
                  type="checkbox"
                  checked={notifyNoCredits}
                  onChange={(e) => setNotifyNoCredits(e.target.checked)}
                  className="size-4"
                />
              </label>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Info Section */}
      <Card className="bg-muted/30">
        <CardContent className="pt-6">
          <div className="grid gap-4 md:grid-cols-3 text-sm">
            <div>
              <p className="font-medium">Ambiente atual</p>
              <Badge variant={sefazAmbiente === "1" ? "default" : "secondary"} className="mt-1">
                {sefazAmbiente === "1" ? "Produção" : "Homologação"}
              </Badge>
            </div>
            <div>
              <p className="font-medium">Captura</p>
              <p className="text-muted-foreground mt-1">
                {capturaMode === "auto" ? `Automática a cada ${capturaInterval} min` : "Manual"}
              </p>
            </div>
            <div>
              <p className="font-medium">Manifestação NF-e</p>
              <p className="text-muted-foreground mt-1">
                {manifestacaoMode === "auto_ciencia" ? "Ciência Automática" : "Manual"}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
