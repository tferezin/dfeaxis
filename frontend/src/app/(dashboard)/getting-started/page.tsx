"use client"

import { useState } from "react"
import Link from "next/link"
import {
  Settings, ShieldCheck, Play, FileText, CheckCircle2, ArrowRight,
  Code2, Copy, Check, Server, Key, FileCode, ChevronDown, ChevronUp,
} from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"

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

const apiEndpoints = [
  {
    method: "GET",
    path: "/api/v1/documentos",
    description: "Lista documentos disponíveis para consumo",
    params: "cnpj (obrigatório), tipo (nfe|cte|mdfe), desde (NSU opcional)",
    response: "Lista de documentos com XML em base64",
  },
  {
    method: "POST",
    path: "/api/v1/documentos/{chave}/confirmar",
    description: "Confirma recebimento — XML é removido do banco",
    params: "chave (chave de acesso de 44 dígitos na URL)",
    response: '{ "status": "discarded" }',
  },
  {
    method: "GET",
    path: "/api/v1/sefaz/status",
    description: "Health check dos endpoints SEFAZ",
    params: "Nenhum",
    response: "Status de conexão por tipo de documento",
  },
]

const abapCode = `*&---------------------------------------------------------------------*
*& Report ZDFEAXIS_CONSUMER
*& Programa modelo para consumir documentos fiscais via DFeAxis API
*& Configurar RFC Destination HTTP apontando para a URL do DFeAxis
*&---------------------------------------------------------------------*
REPORT zdfeaxis_consumer.

*----------------------------------------------------------------------*
* Constantes
*----------------------------------------------------------------------*
CONSTANTS:
  gc_rfc_dest  TYPE rfcdest VALUE 'ZDFEAXIS_API',  " RFC Destination HTTP
  gc_api_key   TYPE string  VALUE '<SUA_API_KEY>',  " Gerada no painel DFeAxis
  gc_cnpj      TYPE string  VALUE '<CNPJ_EMPRESA>'. " CNPJ cadastrado no DFeAxis

*----------------------------------------------------------------------*
* Tipos
*----------------------------------------------------------------------*
TYPES:
  BEGIN OF ty_documento,
    chave              TYPE string,
    tipo               TYPE string,
    nsu                TYPE string,
    xml_b64            TYPE string,
    fetched_at         TYPE string,
    manifestacao_status TYPE string,
    is_resumo          TYPE abap_bool,
  END OF ty_documento,

  BEGIN OF ty_response,
    cnpj       TYPE string,
    ult_nsu    TYPE string,
    total      TYPE i,
    documentos TYPE STANDARD TABLE OF ty_documento WITH DEFAULT KEY,
  END OF ty_response.

*----------------------------------------------------------------------*
* Variáveis
*----------------------------------------------------------------------*
DATA:
  lo_http_client TYPE REF TO if_http_client,
  lo_rest_client TYPE REF TO cl_rest_http_client,
  lv_url         TYPE string,
  lv_response    TYPE string,
  lv_status      TYPE i,
  ls_response    TYPE ty_response,
  lv_xml_raw     TYPE xstring,
  lv_xml_string  TYPE string.

*----------------------------------------------------------------------*
* 1. CRIAR CONEXÃO HTTP
*----------------------------------------------------------------------*
WRITE: / '=== DFeAxis Consumer ==='.
WRITE: / 'Buscando documentos para CNPJ:', gc_cnpj.
SKIP.

cl_http_client=>create_by_destination(
  EXPORTING  destination = gc_rfc_dest
  IMPORTING  client      = lo_http_client
  EXCEPTIONS OTHERS      = 1 ).

IF sy-subrc <> 0.
  WRITE: / 'Erro ao criar conexao HTTP. Verifique a RFC Destination:', gc_rfc_dest.
  RETURN.
ENDIF.

*----------------------------------------------------------------------*
* 2. CONFIGURAR REQUEST - Buscar NF-e
*----------------------------------------------------------------------*
" Endpoint: GET /api/v1/documentos?cnpj=XXXXX&tipo=nfe
lv_url = |/api/v1/documentos?cnpj={ gc_cnpj }&tipo=nfe|.

lo_http_client->request->set_header_field(
  name = '~request_uri'  value = lv_url ).
lo_http_client->request->set_header_field(
  name = 'X-API-Key'     value = gc_api_key ).
lo_http_client->request->set_header_field(
  name = 'Accept'        value = 'application/json' ).
lo_http_client->request->set_method( 'GET' ).

*----------------------------------------------------------------------*
* 3. ENVIAR REQUEST
*----------------------------------------------------------------------*
lo_http_client->send(
  EXCEPTIONS OTHERS = 1 ).

IF sy-subrc <> 0.
  WRITE: / 'Erro ao enviar request HTTP.'.
  lo_http_client->close( ).
  RETURN.
ENDIF.

lo_http_client->receive(
  EXCEPTIONS OTHERS = 1 ).

lv_status = lo_http_client->response->get_header_field( '~status_code' ).
lv_response = lo_http_client->response->get_cdata( ).

WRITE: / 'HTTP Status:', lv_status.

IF lv_status <> 200.
  WRITE: / 'Erro na API:', lv_response.
  lo_http_client->close( ).
  RETURN.
ENDIF.

*----------------------------------------------------------------------*
* 4. PARSEAR RESPOSTA JSON
*----------------------------------------------------------------------*
" Usar /ui2/cl_json para converter JSON -> estrutura ABAP
/ui2/cl_json=>deserialize(
  EXPORTING json = lv_response
  CHANGING  data = ls_response ).

WRITE: / 'Total documentos encontrados:', ls_response-total.
WRITE: / 'Ultimo NSU:', ls_response-ult_nsu.
SKIP.

*----------------------------------------------------------------------*
* 5. PROCESSAR CADA DOCUMENTO
*----------------------------------------------------------------------*
LOOP AT ls_response-documentos ASSIGNING FIELD-SYMBOL(<doc>).
  WRITE: / '--- Documento ---'.
  WRITE: / '  Tipo:', <doc>-tipo.
  WRITE: / '  Chave:', <doc>-chave.
  WRITE: / '  NSU:', <doc>-nsu.
  WRITE: / '  Resumo:', <doc>-is_resumo.

  " Decodificar XML de base64
  IF <doc>-xml_b64 IS NOT INITIAL.
    CALL FUNCTION 'SCMS_BASE64_DECODE_STR'
      EXPORTING input  = <doc>-xml_b64
      IMPORTING output = lv_xml_raw
      EXCEPTIONS OTHERS = 1.

    IF sy-subrc = 0.
      CALL FUNCTION 'ECATT_CONV_XSTRING_TO_STRING'
        EXPORTING im_xstring = lv_xml_raw
        IMPORTING ex_string  = lv_xml_string.

      WRITE: / '  XML decodificado com sucesso. Tamanho:', strlen( lv_xml_string ), 'bytes'.

      " >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
      " AQUI: Processar o XML conforme sua logica de negocio
      " Exemplos:
      "   - Criar entrada MIRO (fatura)
      "   - Registrar no DRC (Document and Reporting Compliance)
      "   - Alimentar tabela Z de controle
      " >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

    ENDIF.
  ELSE.
    WRITE: / '  Documento eh resumo (sem XML). Necessita manifestacao.'.
  ENDIF.

  " 6. CONFIRMAR RECEBIMENTO (remove XML do DFeAxis)
  lv_url = |/api/v1/documentos/{ <doc>-chave }/confirmar|.
  lo_http_client->request->set_header_field(
    name = '~request_uri'  value = lv_url ).
  lo_http_client->request->set_header_field(
    name = 'X-API-Key'     value = gc_api_key ).
  lo_http_client->request->set_method( 'POST' ).

  lo_http_client->send( EXCEPTIONS OTHERS = 1 ).
  lo_http_client->receive( EXCEPTIONS OTHERS = 1 ).

  lv_status = lo_http_client->response->get_header_field( '~status_code' ).

  IF lv_status = 200.
    WRITE: / '  Confirmado no DFeAxis (XML removido do banco).'.
  ELSE.
    WRITE: / '  Erro ao confirmar:', lv_status.
  ENDIF.

  SKIP.
ENDLOOP.

*----------------------------------------------------------------------*
* 7. FECHAR CONEXÃO
*----------------------------------------------------------------------*
lo_http_client->close( ).

WRITE: / '=== Processamento concluido ==='.
WRITE: / 'Documentos processados:', lines( ls_response-documentos ).`

const rfcConfig = `*----------------------------------------------------------------------*
* Configuração da RFC Destination HTTP no SAP
*----------------------------------------------------------------------*
* Transação: SM59
*
* 1. Criar nova RFC Destination tipo "G" (HTTP Connection to Ext. Server)
*
*    Nome:           ZDFEAXIS_API
*    Tipo conexão:   G (HTTP Connection to External Server)
*
* 2. Aba "Technical Settings":
*    Host:           dfeaxis-production.up.railway.app
*    Port:           443
*    Path Prefix:    (deixar vazio)
*
* 3. Aba "Logon & Security":
*    SSL:            Ativo (HTTPS)
*    Certificado SSL: DEFAULT SSL Client (Standard)
*    Não usar logon básico — autenticação via header X-API-Key
*
* 4. Testar conexão (botão "Connection Test")
*    Deve retornar HTTP 200 ou 404 (não 000 ou timeout)
*
* 5. No programa ABAP, incluir o header X-API-Key com a chave
*    gerada no painel DFeAxis (menu Cadastros > API Keys)
*----------------------------------------------------------------------*`

function CopyButton({ text, label }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <Button
      variant="outline"
      size="sm"
      className="gap-1.5 text-xs"
      onClick={() => {
        navigator.clipboard.writeText(text)
        setCopied(true)
        setTimeout(() => setCopied(false), 2000)
      }}
    >
      {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
      {label || (copied ? "Copiado" : "Copiar")}
    </Button>
  )
}

function CollapsibleSection({ title, icon: Icon, badge, children, defaultOpen = false }: {
  title: string
  icon: React.ElementType
  badge?: string
  children: React.ReactNode
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <Card>
      <CardHeader
        className="cursor-pointer select-none"
        onClick={() => setOpen(!open)}
      >
        <CardTitle className="flex items-center gap-3 text-base">
          <div className="size-10 rounded-lg bg-muted flex items-center justify-center shrink-0">
            <Icon className="size-5" />
          </div>
          <span className="flex-1">{title}</span>
          {badge && <Badge variant="secondary" className="text-xs">{badge}</Badge>}
          {open ? <ChevronUp className="size-4 text-muted-foreground" /> : <ChevronDown className="size-4 text-muted-foreground" />}
        </CardTitle>
      </CardHeader>
      {open && <CardContent className="pt-0">{children}</CardContent>}
    </Card>
  )
}

export default function GettingStartedPage() {
  return (
    <div className="space-y-8">
      {/* HEADER */}
      <div>
        <div className="flex items-center gap-2">
          <CheckCircle2 className="size-6 text-primary" />
          <h1 className="text-2xl font-semibold tracking-tight">Primeiros Passos</h1>
        </div>
        <p className="text-sm text-muted-foreground mt-1">
          Siga os passos abaixo para configurar e testar a captura de documentos fiscais recebidos.
        </p>
      </div>

      {/* STEPS */}
      <div className="grid gap-4">
        {steps.map((step) => {
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

      {/* SEPARATOR */}
      <div className="border-t pt-8">
        <div className="flex items-center gap-2 mb-1">
          <Code2 className="size-6 text-primary" />
          <h2 className="text-xl font-semibold tracking-tight">Integração SAP DRC</h2>
        </div>
        <p className="text-sm text-muted-foreground">
          Documentação técnica para integrar o DFeAxis ao SAP via RFC Destination HTTP.
        </p>
      </div>

      {/* API DOCUMENTATION */}
      <CollapsibleSection title="API REST — Endpoints" icon={Server} badge="3 endpoints" defaultOpen>
        <div className="space-y-4">
          <div className="rounded-lg bg-muted/50 p-4 space-y-1">
            <p className="text-sm font-medium">Autenticação</p>
            <p className="text-xs text-muted-foreground">
              Todas as requisições devem incluir o header <code className="bg-muted px-1.5 py-0.5 rounded text-xs font-mono">X-API-Key</code> com a chave gerada em <strong>Cadastros &gt; API Keys</strong>.
            </p>
          </div>

          <div className="space-y-3">
            {apiEndpoints.map((ep, i) => (
              <div key={i} className="rounded-lg border p-4 space-y-2">
                <div className="flex items-center gap-2">
                  <Badge variant={ep.method === "GET" ? "secondary" : "default"} className="text-xs font-mono">
                    {ep.method}
                  </Badge>
                  <code className="text-sm font-mono">{ep.path}</code>
                </div>
                <p className="text-sm text-muted-foreground">{ep.description}</p>
                <div className="text-xs text-muted-foreground">
                  <strong>Parâmetros:</strong> {ep.params}
                </div>
              </div>
            ))}
          </div>

          <div className="rounded-lg border p-4">
            <div className="flex items-center justify-between mb-2">
              <p className="text-sm font-medium">Exemplo — Buscar CT-e</p>
              <CopyButton text={`curl -s "https://dfeaxis-production.up.railway.app/api/v1/documentos?cnpj=SEU_CNPJ&tipo=cte" -H "X-API-Key: SUA_API_KEY"`} />
            </div>
            <pre className="text-xs font-mono bg-zinc-950 text-zinc-100 rounded-lg p-4 overflow-x-auto">
{`curl -s "https://dfeaxis-production.up.railway.app/api/v1/documentos?cnpj=SEU_CNPJ&tipo=cte" \\
  -H "X-API-Key: SUA_API_KEY"

# Resposta:
{
  "cnpj": "01786983000368",
  "total": 2,
  "ult_nsu": "000000000412893",
  "documentos": [
    {
      "chave": "35260398765432000168570010000004561234567891",
      "tipo": "CTE",
      "nsu": "000000000412892",
      "xml_b64": "PD94bWwgdmVyc2lvbi4uLg==",
      "is_resumo": false
    }
  ]
}`}
            </pre>
          </div>

          <div className="rounded-lg border p-4">
            <div className="flex items-center justify-between mb-2">
              <p className="text-sm font-medium">Exemplo — Confirmar recebimento</p>
              <CopyButton text={`curl -s -X POST "https://dfeaxis-production.up.railway.app/api/v1/documentos/CHAVE_44_DIGITOS/confirmar" -H "X-API-Key: SUA_API_KEY"`} />
            </div>
            <pre className="text-xs font-mono bg-zinc-950 text-zinc-100 rounded-lg p-4 overflow-x-auto">
{`curl -s -X POST "https://dfeaxis-production.up.railway.app/api/v1/documentos/CHAVE_44_DIGITOS/confirmar" \\
  -H "X-API-Key: SUA_API_KEY"

# Resposta:
{ "status": "discarded" }
# O XML foi removido do banco. O documento não aparecerá mais na listagem.`}
            </pre>
          </div>
        </div>
      </CollapsibleSection>

      {/* API KEY */}
      <CollapsibleSection title="Autenticação — API Key" icon={Key}>
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">
            A API Key é gerada no painel DFeAxis em <strong>Cadastros &gt; API Keys</strong>. Cada cliente possui suas próprias chaves, garantindo isolamento total dos dados.
          </p>
          <div className="rounded-lg bg-amber-50 border border-amber-200 p-4">
            <p className="text-sm text-amber-800">
              <strong>Importante:</strong> A API Key deve ser mantida em sigilo. Ela dá acesso aos documentos fiscais do cliente. Nunca compartilhe publicamente ou em código-fonte.
            </p>
          </div>
          <div className="rounded-lg border p-4">
            <p className="text-sm font-medium mb-2">Fluxo de segurança</p>
            <ol className="text-sm text-muted-foreground space-y-1 list-decimal list-inside">
              <li>Cliente gera API Key no painel DFeAxis</li>
              <li>Configura a chave no SAP (RFC Destination ou tabela Z)</li>
              <li>SAP envia a chave no header <code className="bg-muted px-1 py-0.5 rounded text-xs font-mono">X-API-Key</code></li>
              <li>DFeAxis valida a chave e identifica o tenant (cliente)</li>
              <li>Retorna apenas os documentos daquele tenant</li>
            </ol>
          </div>
        </div>
      </CollapsibleSection>

      {/* RFC DESTINATION */}
      <CollapsibleSection title="SAP — Configuração RFC Destination (SM59)" icon={Settings}>
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">
            Configure uma RFC Destination tipo G (HTTP to External Server) na transação SM59 do SAP.
          </p>
          <div className="relative">
            <div className="absolute top-2 right-2">
              <CopyButton text={rfcConfig} />
            </div>
            <pre className="text-xs font-mono bg-zinc-950 text-zinc-100 rounded-lg p-4 overflow-x-auto whitespace-pre">
{rfcConfig}
            </pre>
          </div>
        </div>
      </CollapsibleSection>

      {/* ABAP CODE */}
      <CollapsibleSection title="SAP — Programa ABAP Modelo" icon={FileCode} badge="ABAP">
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">
            Programa ABAP completo para consumir documentos do DFeAxis. Substitua <code className="bg-muted px-1 py-0.5 rounded text-xs font-mono">&lt;SUA_API_KEY&gt;</code> e <code className="bg-muted px-1 py-0.5 rounded text-xs font-mono">&lt;CNPJ_EMPRESA&gt;</code> pelos valores reais.
          </p>
          <div className="rounded-lg bg-emerald-50 border border-emerald-200 p-4">
            <p className="text-sm text-emerald-800">
              <strong>Fluxo do programa:</strong> Conecta via RFC Destination &rarr; Busca documentos &rarr; Decodifica XML de base64 &rarr; Processa conforme regra de negócio &rarr; Confirma recebimento (limpa do DFeAxis).
            </p>
          </div>
          <div className="relative">
            <div className="absolute top-2 right-2">
              <CopyButton text={abapCode} />
            </div>
            <pre className="text-xs font-mono bg-zinc-950 text-zinc-100 rounded-lg p-4 overflow-x-auto whitespace-pre max-h-[600px] overflow-y-auto">
{abapCode}
            </pre>
          </div>
        </div>
      </CollapsibleSection>

      {/* FOOTER NOTE */}
      <Card className="bg-muted/30">
        <CardContent className="py-4">
          <p className="text-sm text-muted-foreground">
            <strong>Tipos de documento suportados:</strong> NF-e (modelo 55), CT-e (modelo 57), MDF-e (modelo 58), NFS-e (ADN Nacional). O SAP pode buscar cada tipo separadamente usando o parâmetro <code className="bg-muted px-1 py-0.5 rounded text-xs font-mono">tipo</code> no endpoint de documentos.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
