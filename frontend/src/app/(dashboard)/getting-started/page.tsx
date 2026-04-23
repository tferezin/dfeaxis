"use client"

import { useState } from "react"
import Link from "next/link"
import {
  Settings, ShieldCheck, Play, FileText, CheckCircle2, ArrowRight,
  Code2, Copy, Check, Server, Key, FileCode, ChevronDown, ChevronUp,
  Send, Workflow, Search, History, AlertCircle,
} from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"

// Tour guiado pós-upload do certificado. Cobre validação do setup
// antes de passar pra parte técnica da integração. O upload do .pfx
// é tratado como pré-requisito separado (bloco verde acima) e não
// se repete aqui pra evitar confusão de numeração.
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
    title: "Execute uma Captura Manual",
    description: "Acesse a captura manual, selecione o CNPJ e clique em Capturar. O DFeAxis vai consultar a SEFAZ e trazer os documentos recebidos.",
    icon: Play,
    href: "/execucao/captura",
    color: "text-amber-600 bg-amber-100 border-amber-200",
  },
  {
    number: 3,
    title: "Confira os Resultados",
    description: "Vá em NF-e Recebidas para ver os documentos capturados. Se estiver em homologação e não houver documentos, é normal — a base de testes pode estar vazia.",
    icon: FileText,
    href: "/historico/nfe",
    color: "text-purple-600 bg-purple-100 border-purple-200",
  },
]

// Endpoints SAP DRC nativos — consumidos quando o cliente configura
// Communication Arrangement / BTP Destination apontando pro DFeAxis.
// Retornam schema SAP (NotaFiscalFragment com accessKey, companyCNPJ etc)
// já tipado — SAP consome direto, sem parsear XML.
const sapDrcEndpoints = [
  {
    method: "POST",
    path: "/sap-drc/v1/retrieveInboundInvoices",
    description: "Retorna NF-e pendentes já parseadas no schema SAP DRC",
    params: "Body JSON: { cnpjList: [\"01234567000100\"] }",
    response: "Lista de NotaFiscalFragments + EventFragments tipados",
  },
  {
    method: "GET",
    path: "/sap-drc/v1/downloadOfficialDocument",
    description: "Baixa o XML autorizado (procNFe) para uma chave de acesso",
    params: "Query: accessKey (44 dígitos)",
    response: "XML bruto (Content-Type: application/xml)",
  },
  {
    method: "POST",
    path: "/sap-drc/v1/receiveOfficialDocument",
    description: "Envia evento fiscal (ciência/confirmação) via contrato SAP",
    params: "Body JSON: { xml: \"<procEventoNFe>...</procEventoNFe>\" }",
    response: "202 Accepted (ou 4xx com detalhes)",
  },
  {
    method: "DELETE",
    path: "/sap-drc/v1/deleteInboundInvoices",
    description: "Marca notas como entregues e descarta XML (equivalente ao /confirmar)",
    params: "Body JSON: { uuidList: [\"uuid-1\", \"uuid-2\"] }",
    response: "204 No Content",
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
    method: "POST",
    path: "/api/v1/manifestacao",
    description: "Envia evento de manifestação (ciencia, confirmar, desconhecer, nao realizada)",
    params: "Body JSON: { chave_acesso, tipo_evento } — tipo_evento: 210210 | 210200 | 210220 | 210240",
    response: '{ "status": "accepted", "protocolo": "..." }',
  },
  {
    method: "POST",
    path: "/api/v1/manifestacao/batch",
    description: "Manifestação em lote (até 50 chaves com mesmo tipo_evento)",
    params: "Body JSON: { chaves: [...], tipo_evento }",
    response: "Lista de resultados por chave",
  },
  {
    method: "GET",
    path: "/api/v1/manifestacao/pendentes",
    description: "Listar NF-e pendentes de ciência (ainda não manifestadas)",
    params: "cnpj (obrigatório)",
    response: "Lista de documentos pendentes: [{ chave, nsu, manifestacao_status, fetched_at }]",
  },
  {
    method: "GET",
    path: "/api/v1/manifestacao/historico",
    description: "Histórico de eventos de manifestação com filtros",
    params: "cnpj, chave_acesso, tipo_evento, limit (máx 500) — todos opcionais",
    response: '{ "total": N, "events": [{ chave_acesso, tipo_evento, cstat, xmotivo, protocolo, source, created_at }] }',
  },
  {
    method: "GET",
    path: "/api/v1/sefaz/status",
    description: "Health check dos endpoints SEFAZ",
    params: "Nenhum",
    response: "Status de conexão por tipo de documento",
  },
  {
    method: "GET",
    path: "/api/v1/alerts",
    description: "Alertas operacionais (certificado expirando, trial terminando, consumo alto)",
    params: "Nenhum",
    response: '{ "alerts": [{ id, type, severity, message, metadata }], "total": N, "generated_at": "..." }',
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
  WRITE: / 'Erro ao criar conexão HTTP. Verifique a RFC Destination:', gc_rfc_dest.
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

WRITE: / '=== Processamento concluído ==='.
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
*    Host:           api.dfeaxis.com.br
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

const abapCodeConfirmar = `*&---------------------------------------------------------------------*
*& Confirma recebimento do documento (XML é descartado no servidor)
*&---------------------------------------------------------------------*

DATA: lo_http_client TYPE REF TO if_http_client,
      lv_url         TYPE string,
      lv_status      TYPE i,
      lv_response    TYPE string.

" Exemplo: confirmar NF-e com chave específica
DATA(lv_chave) = '35260312345678000190550010012345671234567890'.
lv_url = |https://api.dfeaxis.com.br/api/v1/documentos/{ lv_chave }/confirmar|.

cl_http_client=>create_by_destination(
  EXPORTING destination = gc_rfc_dest
  IMPORTING client      = lo_http_client ).

lo_http_client->request->set_method( 'POST' ).
lo_http_client->request->set_header_field( name = 'X-API-Key' value = gc_api_key ).
lo_http_client->request->set_header_field( name = 'Content-Type' value = 'application/json' ).
lo_http_client->request->set_header_field( name = 'Host' value = 'api.dfeaxis.com.br' ).
lo_http_client->request->set_uri( lv_url ).

lo_http_client->send( ).
lo_http_client->receive( ).
lo_http_client->response->get_status( IMPORTING code = lv_status ).

IF lv_status = 200.
  WRITE: / 'Documento confirmado como recebido. XML descartado no servidor.'.
ELSE.
  WRITE: / 'Erro ao confirmar:', lv_response.
ENDIF.
`

const abapCodeManifestar = `*&---------------------------------------------------------------------*
*& Envia manifestação de NF-e (210200 = Confirmação da Operação)
*& Eventos: 210210=Ciência, 210200=Confirmar, 210220=Desconhecer, 210240=Não Realizada
*&---------------------------------------------------------------------*

DATA: lo_http_client TYPE REF TO if_http_client,
      lv_url         TYPE string,
      lv_body        TYPE string,
      lv_status      TYPE i,
      lv_response    TYPE string.

" Após a MIRO ter sido feita com sucesso, enviar Confirmação
DATA(lv_chave) = '35260312345678000190550010012345671234567890'.
DATA(lv_tipo_evento) = '210200'. " Confirmação da Operação

lv_url = 'https://api.dfeaxis.com.br/api/v1/manifestacao'.

" Monta o JSON do request
lv_body = |\\{"chave_acesso":"{ lv_chave }","tipo_evento":"{ lv_tipo_evento }"\\}|.

cl_http_client=>create_by_destination(
  EXPORTING destination = gc_rfc_dest
  IMPORTING client      = lo_http_client ).

lo_http_client->request->set_method( 'POST' ).
lo_http_client->request->set_header_field( name = 'X-API-Key' value = gc_api_key ).
lo_http_client->request->set_header_field( name = 'Content-Type' value = 'application/json' ).
lo_http_client->request->set_header_field( name = 'Host' value = 'api.dfeaxis.com.br' ).
lo_http_client->request->set_uri( lv_url ).
lo_http_client->request->set_cdata( lv_body ).

lo_http_client->send( ).
lo_http_client->receive( ).
lo_http_client->response->get_status( IMPORTING code = lv_status ).
lo_http_client->response->get_cdata( RECEIVING data = lv_response ).

IF lv_status = 200.
  WRITE: / 'Manifestação enviada com sucesso. Resposta:', lv_response.
ELSE.
  WRITE: / 'Erro na manifestação. Status:', lv_status, 'Resposta:', lv_response.
ENDIF.

" Para manifestação em lote, use:
" POST /manifestacao/batch com body { chaves: [...], tipo_evento: "210200" }
" Limite: 50 chaves por request.
`

const abapCodeConsultarPendentes = `*&---------------------------------------------------------------------*
*& Lista NF-e pendentes de manifestação definitiva para um CNPJ
*& Retorna documentos com ciencia (auto) mas sem manifesto definitivo
*&---------------------------------------------------------------------*

DATA: lo_http_client TYPE REF TO if_http_client,
      lv_url         TYPE string,
      lv_status      TYPE i,
      lv_response    TYPE string.

DATA(lv_cnpj) = '12345678000190'.
lv_url = |https://api.dfeaxis.com.br/api/v1/manifestacao/pendentes?cnpj={ lv_cnpj }|.

cl_http_client=>create_by_destination(
  EXPORTING destination = gc_rfc_dest
  IMPORTING client      = lo_http_client ).

lo_http_client->request->set_method( 'GET' ).
lo_http_client->request->set_header_field( name = 'X-API-Key' value = gc_api_key ).
lo_http_client->request->set_header_field( name = 'Host' value = 'api.dfeaxis.com.br' ).
lo_http_client->request->set_uri( lv_url ).

lo_http_client->send( ).
lo_http_client->receive( ).
lo_http_client->response->get_status( IMPORTING code = lv_status ).
lo_http_client->response->get_cdata( RECEIVING data = lv_response ).

IF lv_status = 200.
  " Parse JSON array: [{chave, nsu, manifestacao_status, fetched_at}, ...]
  " Use /ui2/cl_json para converter
  WRITE: / 'Documentos pendentes encontrados.'.
  WRITE: / 'Resposta:', lv_response.
ELSE.
  WRITE: / 'Erro ao consultar pendentes:', lv_status.
ENDIF.
`

const abapCodeConsultarHistorico = `*&---------------------------------------------------------------------*
*& Consulta histórico de manifestações (todas ou filtradas)
*& Filtros opcionais: cnpj, chave_acesso, tipo_evento, limit (máx 500)
*&---------------------------------------------------------------------*

DATA: lo_http_client TYPE REF TO if_http_client,
      lv_url         TYPE string,
      lv_status      TYPE i,
      lv_response    TYPE string.

" Exemplo 1: últimos 100 eventos de um CNPJ
DATA(lv_cnpj) = '12345678000190'.
lv_url = |https://api.dfeaxis.com.br/api/v1/manifestacao/historico?cnpj={ lv_cnpj }&limit=100|.

" Exemplo 2: histórico de uma NF-e específica
" lv_url = |https://api.dfeaxis.com.br/api/v1/manifestacao/historico?chave_acesso=35260...|.

" Exemplo 3: apenas confirmações (210200)
" lv_url = |https://api.dfeaxis.com.br/api/v1/manifestacao/historico?tipo_evento=210200|.

cl_http_client=>create_by_destination(
  EXPORTING destination = gc_rfc_dest
  IMPORTING client      = lo_http_client ).

lo_http_client->request->set_method( 'GET' ).
lo_http_client->request->set_header_field( name = 'X-API-Key' value = gc_api_key ).
lo_http_client->request->set_header_field( name = 'Host' value = 'api.dfeaxis.com.br' ).
lo_http_client->request->set_uri( lv_url ).

lo_http_client->send( ).
lo_http_client->receive( ).
lo_http_client->response->get_status( IMPORTING code = lv_status ).
lo_http_client->response->get_cdata( RECEIVING data = lv_response ).

IF lv_status = 200.
  " Resposta: { "total": N, "events": [{ chave_acesso, tipo_evento, descricao,
  "                                       cstat, xmotivo, protocolo, source,
  "                                       latency_ms, created_at }, ...] }
  " Source pode ser: auto_capture | dashboard | api
  WRITE: / 'Histórico de manifestações:'.
  WRITE: / lv_response.
ELSE.
  WRITE: / 'Erro ao consultar histórico:', lv_status.
ENDIF.
`

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

type IntegrationProfile = "sap-drc" | "sap-abap" | "generic" | null

export default function GettingStartedPage() {
  const [profile, setProfile] = useState<IntegrationProfile>(null)

  return (
    <div className="space-y-8">
      {/* HEADER */}
      <div>
        <div className="flex items-center gap-2">
          <CheckCircle2 className="size-6 text-primary" />
          <h1 className="text-2xl font-semibold tracking-tight">Primeiros Passos</h1>
        </div>
        <p className="text-sm text-muted-foreground mt-1">
          O DFeAxis captura documentos fiscais da SEFAZ <strong>sob demanda</strong>: seu ERP (SAP, TOTVS, Oracle ou qualquer outro) dispara a consulta via API REST quando quiser. Durante cada captura, enviamos a ciência automática exigida pela SEFAZ e entregamos o documento pronto pro seu ERP processar.
        </p>
      </div>

      {/* PRÉ-REQUISITO — comum a TODOS os cenários */}
      <Card className="border-emerald-500/30 bg-emerald-50/50 dark:bg-emerald-950/20">
        <CardHeader>
          <CardTitle className="flex items-center gap-3 text-base">
            <div className="size-10 rounded-lg bg-emerald-100 dark:bg-emerald-900/40 flex items-center justify-center shrink-0">
              <Key className="size-5 text-emerald-700 dark:text-emerald-300" />
            </div>
            <span>Antes de começar — pré-requisito único</span>
            <Badge variant="secondary" className="text-xs">Comum a todos</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-0 space-y-2 text-sm">
          <p>
            <strong>1.</strong> Acesse <Link href="/cadastros/certificados" className="text-primary hover:underline">Cadastros → Certificados</Link> e faça upload do seu arquivo <code className="bg-muted px-1 py-0.5 rounded text-xs font-mono">.pfx</code>.
          </p>
          <p>
            <strong>2.</strong> A <strong>API Key é gerada automaticamente</strong> nesse momento e aparece na tela <strong>uma única vez</strong> — copie e guarde num lugar seguro.
          </p>
          <p>
            <strong>3.</strong> Se perder, é só gerar nova em <Link href="/cadastros/api-keys" className="text-primary hover:underline">Cadastros → API Keys</Link>.
          </p>
          <p className="text-xs text-muted-foreground pt-2 border-t border-emerald-200 dark:border-emerald-800">
            Depois disso, escolha abaixo como seu ERP vai consumir os documentos — o fluxo muda dependendo do tipo de integração.
          </p>
        </CardContent>
      </Card>

      {/* FLUXO COMPLETO */}
      <Card className="border-primary/30 bg-primary/5">
        <CardHeader>
          <CardTitle className="flex items-center gap-3 text-base">
            <div className="size-10 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
              <Workflow className="size-5 text-primary" />
            </div>
            <span>Fluxo completo — da SEFAZ ao seu ERP</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-0">
          <ol className="space-y-3 text-sm">
            <li className="flex gap-3">
              <span className="shrink-0 size-6 rounded-full bg-primary/15 text-primary font-bold text-xs flex items-center justify-center">1</span>
              <div>
                <strong>Captura sob demanda</strong> — seu ERP dispara a consulta SEFAZ via <code className="bg-muted px-1 py-0.5 rounded text-xs font-mono">POST /api/v1/polling/trigger</code> quando
                quiser (tipicamente em job agendado no seu ERP a cada 30min, 1h ou conforme sua operação). Não há polling
                automático pela plataforma — você controla a frequência. Durante a captura, a Ciência da Operação é enviada
                automaticamente à SEFAZ (obrigatório para liberar o XML completo).
              </div>
            </li>
            <li className="flex gap-3">
              <span className="shrink-0 size-6 rounded-full bg-primary/15 text-primary font-bold text-xs flex items-center justify-center">2</span>
              <div>
                <strong>Cliente busca via API</strong> — o ERP chama <code className="bg-muted px-1 py-0.5 rounded text-xs font-mono">GET /api/v1/documentos</code>
                {" "}quando quiser (tipicamente em job agendado).
              </div>
            </li>
            <li className="flex gap-3">
              <span className="shrink-0 size-6 rounded-full bg-primary/15 text-primary font-bold text-xs flex items-center justify-center">3</span>
              <div>
                <strong>Cliente processa o XML</strong> — decodifica o base64 e grava no seu ERP
                conforme a regra de negócio (lançamento da fatura, entrada de estoque, escrituração, etc).
              </div>
            </li>
            <li className="flex gap-3">
              <span className="shrink-0 size-6 rounded-full bg-primary/15 text-primary font-bold text-xs flex items-center justify-center">4</span>
              <div>
                <strong>Cliente confirma recebimento</strong> — chama <code className="bg-muted px-1 py-0.5 rounded text-xs font-mono">POST /api/v1/documentos/{"{chave}"}/confirmar</code>.
                O XML é descartado do DFeAxis e o documento sai da listagem pendente.
              </div>
            </li>
            <li className="flex gap-3">
              <span className="shrink-0 size-6 rounded-full bg-primary/15 text-primary font-bold text-xs flex items-center justify-center">5</span>
              <div>
                <strong>Manifestação definitiva</strong> — após o lançamento da fatura e geração do contas a pagar no seu ERP, o cliente envia
                {" "}<code className="bg-muted px-1 py-0.5 rounded text-xs font-mono">POST /api/v1/manifestacao</code>
                {" "}com <code className="bg-muted px-1 py-0.5 rounded text-xs font-mono">tipo_evento=210200</code> (Confirmação da Operação).
                Outros eventos: 210210 (Ciência), 210220 (Desconhecer), 210240 (Não Realizada).
              </div>
            </li>
          </ol>
          <div className="mt-4 rounded-lg bg-background/60 border p-3">
            <p className="text-xs text-muted-foreground leading-relaxed">
              <strong>Ciência automática por padrão:</strong> o DFeAxis envia o evento
              {" "}<code className="bg-muted px-1 py-0.5 rounded text-xs font-mono">210210</code> (Ciência da Operação) durante cada captura —
              você não precisa tratar disso no seu ERP. A única manifestação que fica sob responsabilidade do cliente é a
              {" "}<strong>definitiva</strong> (confirmar, desconhecer ou não realizada) após o lançamento da fatura no ERP.
            </p>
          </div>
        </CardContent>
      </Card>

      {/* STEPS — tour guiado de validação pós-upload do certificado */}
      <div>
        <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground mb-3">
          Tour guiado — valide sua configuração
        </h3>
      </div>
      <div className="grid gap-4 -mt-4">
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
                      <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Validação {step.number}</span>
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

      {/* SEPARATOR + ESCOLHA DE PERFIL */}
      <div className="border-t pt-8 space-y-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Code2 className="size-6 text-primary" />
            <h2 className="text-xl font-semibold tracking-tight">Como seu ERP vai consumir os documentos?</h2>
          </div>
          <p className="text-sm text-muted-foreground">
            Cada cenário tem um caminho técnico diferente. Escolha o seu pra ver apenas os exemplos relevantes.
          </p>
        </div>

        <div className="grid md:grid-cols-3 gap-3">
          {/* Card SAP DRC Standard */}
          <Card
            onClick={() => setProfile("sap-drc")}
            className={`cursor-pointer transition-all ${
              profile === "sap-drc"
                ? "border-primary ring-2 ring-primary/30"
                : "hover:border-primary/50 hover:shadow-md"
            }`}
          >
            <CardContent className="py-5 space-y-2">
              <div className="flex items-start gap-3">
                <div className="size-10 rounded-lg bg-blue-100 dark:bg-blue-900/40 flex items-center justify-center shrink-0">
                  <Server className="size-5 text-blue-700 dark:text-blue-300" />
                </div>
                <div className="flex-1">
                  <p className="text-sm font-semibold">SAP DRC Standard</p>
                  <p className="text-xs text-muted-foreground">via BTP / Communication Arrangement</p>
                </div>
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed">
                SAP consome direto do nosso endpoint <code className="bg-muted px-1 py-0.5 rounded text-[10px] font-mono">/sap-drc/v1/*</code>. Zero código ABAP — contrato nativo do SAP DRC.
              </p>
            </CardContent>
          </Card>

          {/* Card SAP ABAP custom */}
          <Card
            onClick={() => setProfile("sap-abap")}
            className={`cursor-pointer transition-all ${
              profile === "sap-abap"
                ? "border-primary ring-2 ring-primary/30"
                : "hover:border-primary/50 hover:shadow-md"
            }`}
          >
            <CardContent className="py-5 space-y-2">
              <div className="flex items-start gap-3">
                <div className="size-10 rounded-lg bg-amber-100 dark:bg-amber-900/40 flex items-center justify-center shrink-0">
                  <FileCode className="size-5 text-amber-700 dark:text-amber-300" />
                </div>
                <div className="flex-1">
                  <p className="text-sm font-semibold">SAP ABAP custom</p>
                  <p className="text-xs text-muted-foreground">via RFC Destination HTTP</p>
                </div>
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed">
                Código <code className="bg-muted px-1 py-0.5 rounded text-[10px] font-mono">Z_</code> próprio consumindo <code className="bg-muted px-1 py-0.5 rounded text-[10px] font-mono">/api/v1/*</code>. Exemplo ABAP completo pronto pra copiar.
              </p>
            </CardContent>
          </Card>

          {/* Card Outros ERPs */}
          <Card
            onClick={() => setProfile("generic")}
            className={`cursor-pointer transition-all ${
              profile === "generic"
                ? "border-primary ring-2 ring-primary/30"
                : "hover:border-primary/50 hover:shadow-md"
            }`}
          >
            <CardContent className="py-5 space-y-2">
              <div className="flex items-start gap-3">
                <div className="size-10 rounded-lg bg-purple-100 dark:bg-purple-900/40 flex items-center justify-center shrink-0">
                  <Workflow className="size-5 text-purple-700 dark:text-purple-300" />
                </div>
                <div className="flex-1">
                  <p className="text-sm font-semibold">Outros ERPs</p>
                  <p className="text-xs text-muted-foreground">TOTVS, Oracle, Sankhya, próprio</p>
                </div>
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed">
                REST genérico consumindo <code className="bg-muted px-1 py-0.5 rounded text-[10px] font-mono">/api/v1/*</code>. Exemplos em <code className="bg-muted px-1 py-0.5 rounded text-[10px] font-mono">curl</code> + JSON.
              </p>
            </CardContent>
          </Card>
        </div>

        {profile === null && (
          <Card className="bg-muted/30 border-dashed">
            <CardContent className="py-6 text-center">
              <p className="text-sm text-muted-foreground">
                Selecione um dos cards acima para ver o guia passo a passo do seu cenário.
              </p>
            </CardContent>
          </Card>
        )}
      </div>

      {/* ═══════════════════════════════════════════════════════════════ */}
      {/* PERFIL: SAP DRC STANDARD                                          */}
      {/* ═══════════════════════════════════════════════════════════════ */}
      {profile === "sap-drc" && (
        <div className="space-y-4">
          <Card className="border-blue-500/30 bg-blue-50/50 dark:bg-blue-950/20">
            <CardContent className="pt-4 pb-4">
              <p className="text-sm text-blue-900 dark:text-blue-100">
                <strong>Caminho nativo SAP DRC.</strong> O SAP consome direto do nosso endpoint — sem código ABAP custom, sem parsear XML manualmente. Configure o Communication Arrangement apontando pro DFeAxis e deixe o DRC Standard fazer o trabalho.
              </p>
            </CardContent>
          </Card>

          {/* Fluxo end-to-end */}
          <CollapsibleSection title="Fluxo completo SAP DRC ↔ DFeAxis" icon={Workflow} defaultOpen>
            <ol className="space-y-3 text-sm list-decimal list-inside">
              <li>
                <strong>SAP chama</strong> <code className="bg-muted px-1 py-0.5 rounded text-xs font-mono">retrieveInboundInvoices</code>
                {" "}— descobre quais NF-e novas o DFeAxis capturou pros CNPJs da conta.
              </li>
              <li>
                <strong>SAP chama</strong> <code className="bg-muted px-1 py-0.5 rounded text-xs font-mono">downloadOfficialDocument</code>
                {" "}pra cada chave retornada — baixa o XML autorizado (procNFe).
              </li>
              <li>
                <strong>SAP processa o XML</strong> — MIRO, lançamento contábil, entrada de estoque, etc.
              </li>
              <li>
                <strong>SAP chama</strong> <code className="bg-muted px-1 py-0.5 rounded text-xs font-mono">receiveOfficialDocument</code>
                {" "}com o evento de manifestação definitiva (confirmar/desconhecer/não realizada).
              </li>
              <li>
                <strong>SAP chama</strong> <code className="bg-muted px-1 py-0.5 rounded text-xs font-mono">deleteInboundInvoices</code>
                {" "}— confirma recebimento e libera o DFeAxis a descartar o XML (padrão zero-retention).
              </li>
            </ol>
            <p className="text-xs text-muted-foreground mt-3">
              A <strong>ciência da operação (210210)</strong> é enviada automaticamente pelo DFeAxis durante a captura — o SAP DRC nunca precisa chamar ciência.
            </p>
          </CollapsibleSection>

          {/* Configuração SAP */}
          <CollapsibleSection title="1. Configurar Communication Arrangement no SAP" icon={Settings} defaultOpen>
            <div className="space-y-4 text-sm">
              <div className="rounded-lg bg-amber-50 border border-amber-200 p-3 dark:bg-amber-950/30 dark:border-amber-800">
                <p className="text-xs text-amber-900 dark:text-amber-100">
                  <strong>Pré-requisito:</strong> o scenario <code className="bg-white/60 px-1 py-0.5 rounded font-mono">SAP_COM_0708</code> (Electronic Invoice for Brazil — Inbound) precisa estar habilitado no seu S/4HANA. Se não estiver disponível, consulte o Basis do seu ambiente — depende do release e do módulo DRC estar licenciado.
                </p>
              </div>

              <div>
                <p className="font-medium mb-2">Passo 1.1 — Communication System</p>
                <ol className="list-decimal list-inside space-y-1 text-muted-foreground text-xs">
                  <li>No Fiori Launchpad, abra <strong>Communication Systems</strong>.</li>
                  <li>Clique em <strong>New</strong>. Preencha:</li>
                </ol>
                <div className="mt-2 rounded-lg border bg-muted/30 p-3 text-xs font-mono space-y-1">
                  <div><span className="text-muted-foreground">System ID:</span> DFEAXIS_API</div>
                  <div><span className="text-muted-foreground">System Name:</span> DFeAxis NF-e Inbound</div>
                  <div><span className="text-muted-foreground">Host Name:</span> api.dfeaxis.com.br</div>
                  <div><span className="text-muted-foreground">Port:</span> 443</div>
                  <div><span className="text-muted-foreground">Protocol:</span> HTTPS (TLS 1.2+)</div>
                </div>
              </div>

              <div>
                <p className="font-medium mb-2">Passo 1.2 — Communication User</p>
                <ol className="list-decimal list-inside space-y-1 text-muted-foreground text-xs">
                  <li>Dentro do Communication System, aba <strong>Users for Outbound Communication</strong>, clique <strong>Add</strong>.</li>
                  <li>Selecione <strong>Authentication Method: Authentication with API Key</strong>.</li>
                  <li>No campo <strong>API Key</strong>, cole a chave gerada no DFeAxis (em Cadastros → Chave da API).</li>
                  <li>O DFeAxis valida pelo header <code className="bg-muted px-1 py-0.5 rounded font-mono">X-API-Key</code> — o SAP envia isso automaticamente quando a autenticação é "API Key".</li>
                </ol>
              </div>

              <div>
                <p className="font-medium mb-2">Passo 1.3 — Communication Arrangement</p>
                <ol className="list-decimal list-inside space-y-1 text-muted-foreground text-xs">
                  <li>Abra <strong>Communication Arrangements</strong> e clique <strong>New</strong>.</li>
                  <li>Escolha o scenario <code className="bg-muted px-1 py-0.5 rounded font-mono">SAP_COM_0708</code>.</li>
                  <li>Em <strong>Communication System</strong>, selecione <strong>DFEAXIS_API</strong> (criado no passo 1.1).</li>
                  <li>Na aba <strong>Outbound Services</strong>, ative os 4 serviços abaixo apontando pros paths do DFeAxis:</li>
                </ol>
                <div className="mt-2 rounded-lg border bg-muted/30 p-3 text-xs font-mono space-y-1">
                  <div><span className="text-emerald-700 dark:text-emerald-400">Retrieve Inbound Invoices</span>   → /sap-drc/v1/retrieveInboundInvoices</div>
                  <div><span className="text-emerald-700 dark:text-emerald-400">Download Official Document</span>  → /sap-drc/v1/downloadOfficialDocument</div>
                  <div><span className="text-emerald-700 dark:text-emerald-400">Receive Official Document</span>   → /sap-drc/v1/receiveOfficialDocument</div>
                  <div><span className="text-emerald-700 dark:text-emerald-400">Delete Inbound Invoices</span>     → /sap-drc/v1/deleteInboundInvoices</div>
                </div>
                <p className="text-xs text-muted-foreground mt-2">
                  Ative o Communication Arrangement e pronto — o SAP DRC vai usar essas URLs nas próximas execuções do job de captura.
                </p>
              </div>

              <div>
                <p className="font-medium mb-2">Passo 1.4 — Teste de conectividade</p>
                <p className="text-xs text-muted-foreground">
                  Antes de rodar o job completo, teste a conectividade via terminal ou postman com um dos exemplos curl abaixo. Retorno <code className="bg-muted px-1 py-0.5 rounded font-mono">200 OK</code> confirma que a chave está válida e o Communication System está acessível.
                </p>
              </div>
            </div>
          </CollapsibleSection>

          {/* Exemplos curl — 4 endpoints */}
          <CollapsibleSection title="2. Exemplos práticos — 4 endpoints" icon={Server} badge="curl">
            <div className="space-y-4">
              <div className="rounded-lg bg-muted/50 p-3">
                <p className="text-xs text-muted-foreground">
                  Em todos os exemplos, substitua <code className="bg-muted px-1 py-0.5 rounded font-mono">SUA_API_KEY</code> pela chave gerada em Cadastros → Chave da API. Respostas vêm no schema <strong>NotaFiscalFragment</strong> (SAP DRC nativo), prontas pra consumir sem parsear XML.
                </p>
              </div>

              {/* 1) retrieveInboundInvoices */}
              <div className="rounded-lg border p-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <Badge className="text-xs font-mono">POST</Badge>
                    <code className="text-sm font-mono">/sap-drc/v1/retrieveInboundInvoices</code>
                  </div>
                  <CopyButton text={`curl -s -X POST "https://api.dfeaxis.com.br/sap-drc/v1/retrieveInboundInvoices" -H "X-API-Key: SUA_API_KEY" -H "Content-Type: application/json" -d '{"cnpjList":["01234567000100"]}'`} />
                </div>
                <p className="text-xs text-muted-foreground mb-2">
                  Descobre NF-e novas capturadas. Retorna fragments tipados (accessKey, CNPJs, número, data, valor, status).
                </p>
                <pre className="text-xs font-mono bg-zinc-950 text-zinc-100 rounded-lg p-3 overflow-x-auto">
{`curl -s -X POST "https://api.dfeaxis.com.br/sap-drc/v1/retrieveInboundInvoices" \\
  -H "X-API-Key: SUA_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"cnpjList":["01234567000100"]}'

# Resposta:
{
  "notaFiscalFragments": [
    {
      "accessKey": "35260398765432000168550010000004561234567891",
      "companyCNPJ": "01234567000100",
      "companyRegion": "SP",
      "supplierCNPJ": "98765432000168",
      "supplierRegion": "SP",
      "notaFiscalNumber": "456",
      "notaFiscalSeries": "1",
      "issueDate": "2026-04-15",
      "notaFiscalStatusCode": "100",
      "notaFiscalStatusDescription": "Autorizado"
    }
  ],
  "eventFragments": []
}`}
                </pre>
              </div>

              {/* 2) downloadOfficialDocument */}
              <div className="rounded-lg border p-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary" className="text-xs font-mono">GET</Badge>
                    <code className="text-sm font-mono">/sap-drc/v1/downloadOfficialDocument</code>
                  </div>
                  <CopyButton text={`curl -s -o invoice.xml "https://api.dfeaxis.com.br/sap-drc/v1/downloadOfficialDocument?accessKey=CHAVE_44_DIGITOS" -H "X-API-Key: SUA_API_KEY"`} />
                </div>
                <p className="text-xs text-muted-foreground mb-2">
                  Baixa o XML autorizado (procNFe) pra uma chave específica. Content-Type: <code className="bg-muted px-1 py-0.5 rounded font-mono">application/xml</code>.
                </p>
                <pre className="text-xs font-mono bg-zinc-950 text-zinc-100 rounded-lg p-3 overflow-x-auto">
{`curl -s -o invoice.xml \\
  "https://api.dfeaxis.com.br/sap-drc/v1/downloadOfficialDocument?accessKey=CHAVE_44_DIGITOS" \\
  -H "X-API-Key: SUA_API_KEY"

# Resposta: XML bruto (procNFe com envelope nfeProc)
# HTTP 200 OK — XML gravado em invoice.xml
# HTTP 404 Not Found — chave não existe ou já foi descartada`}
                </pre>
              </div>

              {/* 3) receiveOfficialDocument */}
              <div className="rounded-lg border p-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <Badge className="text-xs font-mono">POST</Badge>
                    <code className="text-sm font-mono">/sap-drc/v1/receiveOfficialDocument</code>
                  </div>
                  <CopyButton text={`curl -s -X POST "https://api.dfeaxis.com.br/sap-drc/v1/receiveOfficialDocument" -H "X-API-Key: SUA_API_KEY" -H "Content-Type: application/json" -d '{"xml":"<procEventoNFe>...</procEventoNFe>"}'`} />
                </div>
                <p className="text-xs text-muted-foreground mb-2">
                  Envia o evento de manifestação definitiva (confirmação/desconhecimento/não realizada). O SAP monta o XML do evento; o DFeAxis transmite à SEFAZ e devolve o protocolo.
                </p>
                <pre className="text-xs font-mono bg-zinc-950 text-zinc-100 rounded-lg p-3 overflow-x-auto">
{`curl -s -X POST "https://api.dfeaxis.com.br/sap-drc/v1/receiveOfficialDocument" \\
  -H "X-API-Key: SUA_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"xml": "<procEventoNFe>...</procEventoNFe>"}'

# Respostas:
# 202 Accepted — evento aceito pela SEFAZ (cStat 135/136)
# 400 Bad Request — XML malformado
# 422 Unprocessable Entity — evento rejeitado pela SEFAZ com cStat de erro`}
                </pre>
              </div>

              {/* 4) deleteInboundInvoices */}
              <div className="rounded-lg border p-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <Badge variant="destructive" className="text-xs font-mono">DELETE</Badge>
                    <code className="text-sm font-mono">/sap-drc/v1/deleteInboundInvoices</code>
                  </div>
                  <CopyButton text={`curl -s -X DELETE "https://api.dfeaxis.com.br/sap-drc/v1/deleteInboundInvoices" -H "X-API-Key: SUA_API_KEY" -H "Content-Type: application/json" -d '{"uuidList":["uuid-1","uuid-2"]}'`} />
                </div>
                <p className="text-xs text-muted-foreground mb-2">
                  Confirma recebimento e libera o DFeAxis a descartar os XMLs do banco (padrão zero-retention). Equivale ao endpoint genérico <code className="bg-muted px-1 py-0.5 rounded font-mono">/documentos/{"{chave}"}/confirmar</code>, mas em lote e usando UUIDs.
                </p>
                <pre className="text-xs font-mono bg-zinc-950 text-zinc-100 rounded-lg p-3 overflow-x-auto">
{`curl -s -X DELETE "https://api.dfeaxis.com.br/sap-drc/v1/deleteInboundInvoices" \\
  -H "X-API-Key: SUA_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"uuidList": ["uuid-1", "uuid-2"]}'

# Resposta: 204 No Content
# Docs saem da listagem pendente + contador de consumo avança.`}
                </pre>
              </div>
            </div>
          </CollapsibleSection>

          {/* Troubleshooting */}
          <CollapsibleSection title="3. Troubleshooting comum" icon={AlertCircle}>
            <div className="space-y-3 text-sm">
              <div className="rounded-lg border p-3">
                <p className="font-medium text-destructive">401 Unauthorized</p>
                <p className="text-xs text-muted-foreground mt-1">
                  Chave não reconhecida. Verifique (a) se o header <code className="bg-muted px-1 py-0.5 rounded font-mono">X-API-Key</code> está sendo enviado pelo Communication Arrangement, (b) se a chave foi revogada em <Link href="/cadastros/api-keys" className="text-primary hover:underline">Cadastros → Chave da API</Link>. Se sim, gere nova e atualize o Communication User.
                </p>
              </div>
              <div className="rounded-lg border p-3">
                <p className="font-medium text-amber-700 dark:text-amber-400">403 Forbidden — CNPJ não cadastrado</p>
                <p className="text-xs text-muted-foreground mt-1">
                  O CNPJ enviado em <code className="bg-muted px-1 py-0.5 rounded font-mono">cnpjList</code> não tem certificado A1 ativo nesta conta. Cadastre em <Link href="/cadastros/certificados" className="text-primary hover:underline">Cadastros → Certificados A1</Link>.
                </p>
              </div>
              <div className="rounded-lg border p-3">
                <p className="font-medium text-amber-700 dark:text-amber-400">Resposta vazia em retrieveInboundInvoices</p>
                <p className="text-xs text-muted-foreground mt-1">
                  Significa que a SEFAZ não tem NF-e novas pendentes pros CNPJs. Comportamento normal, especialmente em homologação. Em produção, é sinal de que o scheduler adaptativo do DFeAxis ainda não capturou docs novos desde a última consulta — aguarde o próximo ciclo (≤15 min).
                </p>
              </div>
              <div className="rounded-lg border p-3">
                <p className="font-medium text-amber-700 dark:text-amber-400">404 Not Found em downloadOfficialDocument</p>
                <p className="text-xs text-muted-foreground mt-1">
                  Chave não existe ou XML já foi descartado (após <code className="bg-muted px-1 py-0.5 rounded font-mono">deleteInboundInvoices</code>). Baixe o XML sempre <strong>antes</strong> de chamar delete.
                </p>
              </div>
            </div>
          </CollapsibleSection>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════════ */}
      {/* PERFIL: SAP ABAP CUSTOM                                           */}
      {/* ═══════════════════════════════════════════════════════════════ */}
      {profile === "sap-abap" && (
        <div className="space-y-4">
          <Card className="border-amber-500/30 bg-amber-50/50 dark:bg-amber-950/20">
            <CardContent className="pt-4 pb-4">
              <p className="text-sm text-amber-900 dark:text-amber-100">
                <strong>Caminho ABAP custom.</strong> Você escreve um programa <code className="bg-muted px-1 py-0.5 rounded text-xs font-mono">Z_</code> próprio consumindo nossa API REST via RFC Destination HTTP. Exemplos completos abaixo, prontos pra copiar e adaptar.
              </p>
            </CardContent>
          </Card>

          <CollapsibleSection title="SAP — Configuração RFC Destination (SM59)" icon={Settings}>
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Configure uma RFC Destination tipo G (HTTP to External Server) na transação SM59.
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

          <CollapsibleSection title="1. Buscar documentos — Programa ABAP modelo" icon={FileCode} badge="ABAP">
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Substitua <code className="bg-muted px-1 py-0.5 rounded text-xs font-mono">&lt;SUA_API_KEY&gt;</code> e <code className="bg-muted px-1 py-0.5 rounded text-xs font-mono">&lt;CNPJ_EMPRESA&gt;</code> pelos valores reais.
              </p>
              <div className="rounded-lg bg-emerald-50 border border-emerald-200 p-4">
                <p className="text-sm text-emerald-800">
                  <strong>Fluxo:</strong> Conecta via RFC Destination → Busca documentos → Decodifica XML de base64 → Processa conforme regra de negócio → Confirma recebimento.
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

          <CollapsibleSection title="2. Confirmar recebimento" icon={CheckCircle2} badge="ABAP">
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Após processar o XML no ERP, chame <code className="bg-muted px-1 py-0.5 rounded text-xs font-mono">POST /api/v1/documentos/{"{chave}"}/confirmar</code>. O XML é descartado do DFeAxis.
              </p>
              <div className="relative">
                <div className="absolute top-2 right-2 z-10">
                  <CopyButton text={abapCodeConfirmar} />
                </div>
                <pre className="text-xs font-mono bg-zinc-950 text-zinc-100 rounded-lg p-4 overflow-x-auto whitespace-pre max-h-[500px] overflow-y-auto">
{abapCodeConfirmar}
                </pre>
              </div>
            </div>
          </CollapsibleSection>

          <CollapsibleSection title="3. Manifestação definitiva" icon={Send} badge="ABAP">
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Após a MIRO, envie o evento de manifestação (<code className="bg-muted px-1 py-0.5 rounded text-xs font-mono">tipo_evento=210200</code> = Confirmação).
              </p>
              <div className="rounded-lg bg-blue-50 border border-blue-200 p-4">
                <p className="text-sm text-blue-900 font-medium mb-1">Tipos de evento</p>
                <ul className="text-xs text-blue-800 space-y-0.5">
                  <li><code className="bg-white/60 px-1 py-0.5 rounded font-mono">210210</code> — Ciência da Operação (auto no modo auto_ciencia)</li>
                  <li><code className="bg-white/60 px-1 py-0.5 rounded font-mono">210200</code> — Confirmação da Operação (após MIRO)</li>
                  <li><code className="bg-white/60 px-1 py-0.5 rounded font-mono">210220</code> — Desconhecimento da Operação</li>
                  <li><code className="bg-white/60 px-1 py-0.5 rounded font-mono">210240</code> — Operação não Realizada</li>
                </ul>
              </div>
              <div className="relative">
                <div className="absolute top-2 right-2 z-10">
                  <CopyButton text={abapCodeManifestar} />
                </div>
                <pre className="text-xs font-mono bg-zinc-950 text-zinc-100 rounded-lg p-4 overflow-x-auto whitespace-pre max-h-[500px] overflow-y-auto">
{abapCodeManifestar}
                </pre>
              </div>
            </div>
          </CollapsibleSection>

          <CollapsibleSection title="4. Consultar pendentes / histórico" icon={Search} badge="ABAP">
            <div className="space-y-4">
              <div>
                <p className="text-sm text-muted-foreground mb-2">
                  <strong>Pendentes</strong> — NF-e aguardando manifestação definitiva (ciência já enviada).
                </p>
                <div className="relative">
                  <div className="absolute top-2 right-2 z-10">
                    <CopyButton text={abapCodeConsultarPendentes} />
                  </div>
                  <pre className="text-xs font-mono bg-zinc-950 text-zinc-100 rounded-lg p-4 overflow-x-auto whitespace-pre max-h-[400px] overflow-y-auto">
{abapCodeConsultarPendentes}
                  </pre>
                </div>
              </div>
              <div>
                <p className="text-sm text-muted-foreground mb-2">
                  <strong>Histórico</strong> — eventos de manifestação já enviados (filtros opcionais por cnpj, chave, tipo, limit).
                </p>
                <div className="relative">
                  <div className="absolute top-2 right-2 z-10">
                    <CopyButton text={abapCodeConsultarHistorico} />
                  </div>
                  <pre className="text-xs font-mono bg-zinc-950 text-zinc-100 rounded-lg p-4 overflow-x-auto whitespace-pre max-h-[400px] overflow-y-auto">
{abapCodeConsultarHistorico}
                  </pre>
                </div>
              </div>
            </div>
          </CollapsibleSection>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════════ */}
      {/* PERFIL: OUTROS ERPs (REST GENÉRICO)                               */}
      {/* ═══════════════════════════════════════════════════════════════ */}
      {profile === "generic" && (
        <div className="space-y-4">
          <Card className="border-purple-500/30 bg-purple-50/50 dark:bg-purple-950/20">
            <CardContent className="pt-4 pb-4">
              <p className="text-sm text-purple-900 dark:text-purple-100">
                <strong>REST genérico.</strong> Funciona em qualquer linguagem (Java, .NET, Node, Python, ADVPL, PL/SQL…). O ERP chama nossa API e recebe JSON com os metadados já estruturados (emitente, destinatário, número, data, valor) + XML em base64 quando precisar do documento completo.
              </p>
            </CardContent>
          </Card>

          <CollapsibleSection title="1. Buscar documentos" icon={Server} defaultOpen>
            <div className="space-y-3">
              <div className="rounded-lg border p-4">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-sm font-medium">Exemplo — Buscar CT-e</p>
                  <CopyButton text={`curl -s "https://api.dfeaxis.com.br/api/v1/documentos?cnpj=SEU_CNPJ&tipo=cte" -H "X-API-Key: SUA_API_KEY"`} />
                </div>
                <pre className="text-xs font-mono bg-zinc-950 text-zinc-100 rounded-lg p-4 overflow-x-auto">
{`curl -s "https://api.dfeaxis.com.br/api/v1/documentos?cnpj=SEU_CNPJ&tipo=cte" \\
  -H "X-API-Key: SUA_API_KEY"

# Resposta — metadados já estruturados + XML em base64
{
  "cnpj": "01234567000100",
  "total": 2,
  "ult_nsu": "000000000412893",
  "documentos": [
    {
      "chave": "35260398765432000168570010000004561234567891",
      "tipo": "CTE",
      "nsu": "000000000412892",
      "xml_b64": "PD94bWwgdmVyc2lvbi4uLg==",
      "supplier_cnpj": "98765432000168",
      "supplier_name": "TRANSPORTES ACME LTDA",
      "company_cnpj": "01234567000100",
      "nota_numero": "456",
      "data_emissao": "2026-04-15T10:30:00-03:00",
      "valor_total": 15750.50,
      "is_resumo": false
    }
  ]
}`}
                </pre>
                <p className="text-xs text-muted-foreground mt-2">
                  Os campos <code className="bg-muted px-1 py-0.5 rounded text-[10px] font-mono">supplier_cnpj</code>, <code className="bg-muted px-1 py-0.5 rounded text-[10px] font-mono">nota_numero</code>, <code className="bg-muted px-1 py-0.5 rounded text-[10px] font-mono">data_emissao</code> e <code className="bg-muted px-1 py-0.5 rounded text-[10px] font-mono">valor_total</code> vêm pré-extraídos do XML — seu ERP não precisa parsear o XML só pra isso.
                </p>
              </div>
            </div>
          </CollapsibleSection>

          <CollapsibleSection title="2. Confirmar recebimento" icon={CheckCircle2}>
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Após seu ERP gravar o documento, confirme pra descartar o XML do nosso banco.
              </p>
              <div className="rounded-lg border p-4">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-sm font-medium">Exemplo</p>
                  <CopyButton text={`curl -s -X POST "https://api.dfeaxis.com.br/api/v1/documentos/CHAVE_44_DIGITOS/confirmar" -H "X-API-Key: SUA_API_KEY"`} />
                </div>
                <pre className="text-xs font-mono bg-zinc-950 text-zinc-100 rounded-lg p-4 overflow-x-auto">
{`curl -s -X POST "https://api.dfeaxis.com.br/api/v1/documentos/CHAVE_44_DIGITOS/confirmar" \\
  -H "X-API-Key: SUA_API_KEY"

# Resposta:
{ "status": "discarded" }`}
                </pre>
              </div>
            </div>
          </CollapsibleSection>

          <CollapsibleSection title="3. Manifestação definitiva" icon={Send}>
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Após confirmar a entrada no seu ERP, envie o evento fiscal. <code className="bg-muted px-1 py-0.5 rounded text-xs font-mono">tipo_evento=210200</code> = Confirmação da Operação.
              </p>
              <div className="rounded-lg border p-4">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-sm font-medium">Exemplo</p>
                  <CopyButton text={`curl -s -X POST "https://api.dfeaxis.com.br/api/v1/manifestacao" -H "X-API-Key: SUA_API_KEY" -H "Content-Type: application/json" -d '{"chave_acesso":"CHAVE_44_DIGITOS","tipo_evento":"210200"}'`} />
                </div>
                <pre className="text-xs font-mono bg-zinc-950 text-zinc-100 rounded-lg p-4 overflow-x-auto">
{`curl -s -X POST "https://api.dfeaxis.com.br/api/v1/manifestacao" \\
  -H "X-API-Key: SUA_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "chave_acesso": "CHAVE_44_DIGITOS",
    "tipo_evento": "210200"
  }'

# Resposta:
{ "status": "accepted", "protocolo": "135260000001234" }`}
                </pre>
                <p className="text-xs text-muted-foreground mt-2">
                  Tipos: <code className="bg-muted px-1 py-0.5 rounded text-[10px] font-mono">210210</code> (Ciência), <code className="bg-muted px-1 py-0.5 rounded text-[10px] font-mono">210200</code> (Confirmação), <code className="bg-muted px-1 py-0.5 rounded text-[10px] font-mono">210220</code> (Desconhecimento), <code className="bg-muted px-1 py-0.5 rounded text-[10px] font-mono">210240</code> (Não Realizada). Para lote, use <code className="bg-muted px-1 py-0.5 rounded text-[10px] font-mono">/api/v1/manifestacao/batch</code> (até 50 chaves).
                </p>
              </div>
            </div>
          </CollapsibleSection>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════════ */}
      {/* REFERÊNCIA COMPLETA — sempre visível no rodapé, colapsada          */}
      {/* ═══════════════════════════════════════════════════════════════ */}
      <div className="border-t pt-6">
        <div className="flex items-center gap-2 mb-3">
          <Server className="size-5 text-muted-foreground" />
          <h2 className="text-base font-semibold">Referência completa — todos os endpoints</h2>
        </div>

        <CollapsibleSection title="API genérica — /api/v1/*" icon={Server} badge={`${apiEndpoints.length} endpoints`}>
          <div className="space-y-3">
            {apiEndpoints.map((ep, i) => (
              <div key={i} className="rounded-lg border p-3 space-y-1.5">
                <div className="flex items-center gap-2">
                  <Badge variant={ep.method === "GET" ? "secondary" : "default"} className="text-xs font-mono">
                    {ep.method}
                  </Badge>
                  <code className="text-sm font-mono">{ep.path}</code>
                </div>
                <p className="text-xs text-muted-foreground">{ep.description}</p>
                <div className="text-xs text-muted-foreground">
                  <strong>Parâmetros:</strong> {ep.params}
                </div>
              </div>
            ))}
          </div>
        </CollapsibleSection>
      </div>


      {/* FOOTER NOTE */}
      <Card className="bg-muted/30">
        <CardContent className="py-4">
          <p className="text-sm text-muted-foreground">
            <strong>Tipos de documento suportados:</strong> NF-e (modelo 55), CT-e (modelo 57), CT-e OS (modelo 67), MDF-e (modelo 58), NFS-e (ADN Nacional). O SAP pode buscar cada tipo separadamente usando o parâmetro <code className="bg-muted px-1 py-0.5 rounded text-xs font-mono">tipo</code> no endpoint de documentos.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
