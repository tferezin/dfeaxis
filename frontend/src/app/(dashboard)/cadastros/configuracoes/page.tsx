"use client"

import { useState } from "react"
import { Save, Clock, Globe, Bell, AlertTriangle, Eye, FileCheck, Loader2 } from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Input } from "@/components/ui/input"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { useSettings } from "@/hooks/use-settings"
import { supabase } from "@/lib/supabase"
import { apiFetch } from "@/lib/api"

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

  // Modal de confirmação obrigatório ao mudar de Homologação → Produção:
  // pede senha + checkbox de ciência da cobrança antes de chamar a API.
  const [prodModalOpen, setProdModalOpen] = useState(false)
  const [prodPassword, setProdPassword] = useState("")
  const [prodAcknowledged, setProdAcknowledged] = useState(false)
  const [prodSubmitting, setProdSubmitting] = useState(false)
  const [prodError, setProdError] = useState<string | null>(null)

  const persistAmbiente = async (next: "1" | "2") => {
    updateSettings({ sefazAmbiente: next })
    try {
      await apiFetch("/tenants/settings", {
        method: "PATCH",
        body: JSON.stringify({ sefaz_ambiente: parseInt(next, 10) }),
      })
    } catch (e) {
      console.error("[DFeAxis] Falha ao persistir ambiente no backend:", e)
      throw e
    }
  }

  const handleAmbienteChange = (next: string) => {
    const value = next as "1" | "2"
    if (value === settings.sefazAmbiente) return

    if (value === "1") {
      // Mudança pra Produção exige confirmação por senha + ciência da cobrança
      setProdPassword("")
      setProdAcknowledged(false)
      setProdError(null)
      setProdModalOpen(true)
      return
    }

    // Mudança pra Homologação é caminho seguro — direto
    persistAmbiente("2").catch(() => {
      // updateSettings já refletiu o estado local; o erro é só log
    })
  }

  const confirmProdSwitch = async () => {
    setProdError(null)

    if (!prodAcknowledged) {
      setProdError("Confirme o aviso de cobrança pra prosseguir.")
      return
    }
    if (!prodPassword) {
      setProdError("Informe sua senha pra confirmar.")
      return
    }
    if (!supabase) {
      setProdError("Sistema indisponível. Tente novamente em instantes.")
      return
    }

    setProdSubmitting(true)
    try {
      const { data: userData } = await supabase.auth.getUser()
      const email = userData.user?.email
      if (!email) {
        setProdError("Sessão expirada. Faça login novamente.")
        return
      }

      const { error: signInError } = await supabase.auth.signInWithPassword({
        email,
        password: prodPassword,
      })
      if (signInError) {
        setProdError("Senha incorreta.")
        return
      }

      await persistAmbiente("1")
      setProdModalOpen(false)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (err: unknown) {
      // Backend devolve mensagens explicativas (sem certificado, sem captura
      // em homolog, prod_access não aprovada, etc.) no campo `detail`. O
      // apiFetch encapsula como `Error("API error {status}: {body}")` —
      // extraimos o detail pra mostrar pro usuário.
      let message = "Não foi possível ativar Produção. Tente novamente."
      if (err instanceof Error) {
        const match = err.message.match(/^API error \d+:\s*(.+)$/)
        if (match) {
          try {
            const parsed = JSON.parse(match[1])
            if (typeof parsed?.detail === "string" && parsed.detail.length > 0) {
              message = parsed.detail
            }
          } catch {
            // body não era JSON — usa fallback
          }
        }
      }
      setProdError(message)
    } finally {
      setProdSubmitting(false)
    }
  }

  const handleSave = () => {
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
              <span className="font-medium text-foreground shrink-0">Ciência automática:</span>
              <span>DFeAxis envia a Ciência da Operação (evento 210210) automaticamente em cada captura de NF-e. É obrigatório pela SEFAZ pra liberar o XML completo — você não precisa configurar nada.</span>
            </div>
            <div className="flex gap-2">
              <span className="font-medium text-foreground shrink-0">Polling adaptativo:</span>
              <span>DFeAxis consulta a SEFAZ automaticamente a cada ~15 min respeitando a NT 2014.002 (backoff após cStat 137/656). Requer ativação por tenant — fale com nosso time se quiser ligar pro seu CNPJ.</span>
            </div>
            <div className="flex gap-2">
              <span className="font-medium text-foreground shrink-0">On-demand via API:</span>
              <span>Seu ERP também pode disparar captura extra a qualquer momento via <code className="text-[11px] bg-muted px-1 py-0.5 rounded">POST /api/v1/polling/trigger</code>. Útil pra rodadas sob demanda ou em janelas específicas.</span>
            </div>
            <div className="rounded-lg border border-blue-200 bg-blue-50 p-3 mt-3">
              <p className="text-xs text-blue-800">
                Pra testar manualmente agora, use <strong>Captura Manual</strong> no menu lateral. Em produção, o polling adaptativo + on-demand via ERP cobrem os dois modos.
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
              onChange={handleAmbienteChange}
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

        {/* Alertas via API — substitui o antigo card de Notificações por email */}
        <Card className="md:col-span-2">
          <CardHeader className="pb-2">
            <div className="flex items-center gap-2">
              <Bell className="size-5 text-primary" />
              <CardTitle className="text-base">Alertas via API</CardTitle>
            </div>
            <CardDescription>
              Consulte alertas operacionais em tempo real — sem configurar e-mail, SMTP ou template.
            </CardDescription>
          </CardHeader>
          <CardContent className="pt-0 space-y-3 text-sm text-muted-foreground">
            <p>
              O DFeAxis expõe alertas via <code className="text-[11px] bg-muted px-1 py-0.5 rounded">GET /api/v1/alerts</code>.
              Seu ERP consulta quando quiser e reage conforme a lógica dele. Cada alerta tem um{" "}
              <code className="text-[11px] bg-muted px-1 py-0.5 rounded">id</code> determinístico — se a condição
              não mudou, o id não muda. Use isso pra deduplicar no seu lado.
            </p>
            <div>
              <p className="font-medium text-foreground mb-1.5">Tipos de alerta disponíveis:</p>
              <ul className="list-disc pl-5 space-y-0.5">
                <li><code className="text-[11px] bg-muted px-1 py-0.5 rounded">cert_expiring</code> — certificado A1 expirando (warning: 8-30 dias · critical: 0-7 dias)</li>
                <li><code className="text-[11px] bg-muted px-1 py-0.5 rounded">cert_expired</code> — certificado A1 já vencido</li>
                <li><code className="text-[11px] bg-muted px-1 py-0.5 rounded">trial_ending</code> — trial próximo do limite de tempo ou documentos</li>
                <li><code className="text-[11px] bg-muted px-1 py-0.5 rounded">high_usage</code> — consumo ≥ 90% do plano mensal</li>
                <li><code className="text-[11px] bg-muted px-1 py-0.5 rounded">usage_exceeded</code> — consumo acima de 100% do plano (overage)</li>
                <li><code className="text-[11px] bg-muted px-1 py-0.5 rounded">payment_overdue</code> — falha de pagamento · 5 dias de tolerância até bloqueio</li>
              </ul>
            </div>
          </CardContent>
        </Card>
      </div>

      <Dialog open={prodModalOpen} onOpenChange={setProdModalOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Ativar Ambiente de Produção</DialogTitle>
            <DialogDescription>
              Esta mudança afeta o serviço real e gera cobrança por documento capturado.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3">
              <AlertTriangle className="size-4 text-amber-600 mt-0.5 shrink-0" />
              <div className="text-xs text-amber-900 space-y-1">
                <p><strong>Ao ativar Produção:</strong></p>
                <ul className="list-disc pl-4 space-y-0.5">
                  <li>O DFeAxis passará a capturar documentos fiscais reais da SEFAZ</li>
                  <li>Cada documento capturado será contabilizado e cobrado conforme seu plano</li>
                  <li>Documentos acima do limite mensal geram overage</li>
                </ul>
              </div>
            </div>

            <label className="flex items-start gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={prodAcknowledged}
                onChange={(e) => setProdAcknowledged(e.target.checked)}
                className="mt-0.5 shrink-0"
              />
              <span className="text-sm">
                Entendo que documentos capturados em Produção serão cobrados conforme meu plano contratado.
              </span>
            </label>

            <div className="space-y-1.5">
              <Label htmlFor="prod-password" className="text-sm font-medium">
                Confirme sua senha
              </Label>
              <Input
                id="prod-password"
                type="password"
                placeholder="Sua senha de acesso"
                value={prodPassword}
                onChange={(e) => setProdPassword(e.target.value)}
                autoComplete="current-password"
              />
              <p className="text-xs text-muted-foreground">
                Pedimos a senha pra ter certeza de que é você quem está autorizando a mudança.
              </p>
            </div>

            {prodError && (
              <p className="text-sm text-destructive">{prodError}</p>
            )}
          </div>
          <DialogFooter className="gap-2 sm:gap-2">
            <Button
              variant="outline"
              onClick={() => setProdModalOpen(false)}
              disabled={prodSubmitting}
            >
              Cancelar
            </Button>
            <Button
              onClick={confirmProdSwitch}
              disabled={prodSubmitting || !prodAcknowledged || !prodPassword}
            >
              {prodSubmitting && <Loader2 className="mr-2 size-4 animate-spin" />}
              Ativar Produção
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
