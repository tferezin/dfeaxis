# SAP NFe APIs - Documentação Completa

**Package:** NFEAPIS (SAP Document and Reporting Compliance Outbound Invoicing Option for Brazil)
**Extraído em:** 17/03/2026
**Fonte:** SAP Business Accelerator Hub (api.sap.com)

---

## 1. Electronic Nota Fiscal (NFe) Inbound Simple

**Descrição:** Permite gerenciar NF-es de entrada que seu fornecedor emitiu e enviou para você.

**Base URL (Sandbox):** `https://sandbox.api.sap.com/DocumentReportingComplianceInvoicing4Brazil/nfe-inbound-simple`
**Base URL (Production):** `https://nfe.cfapps.br10.hana.ondemand.com/nfe-inbound-simple`
**Versão:** 1.0.0

### Endpoints

#### GET /health
**Descrição:** Verifica o status de saúde da aplicação.

**Response:**
- `200 OK` - Aplicação online
- `401 Unauthorized`
- `404 Not Found`

---

#### POST /v1/retrieveInboundInvoices
**Descrição:** Recupera informações de NF-es de entrada por CNPJ.

**Request Headers:**
- `Content-Type: application/json`
- `Authorization: Bearer {token}`

**Request Body:**
```json
{
  "cnpj": ["74544297000192"]
}
```

**Response (200 OK):**
```json
{
  "eventFragmentList": [
    {
      "uuid": "ccf9e52b-e2e4-45d8-8884-0721d3246a53",
      "accessKey": "12901234567890123456789012345678901234567890",
      "eventType": "110111",
      "eventSequence": "01",
      "eventDescription": "Cancelamento",
      "eventStatusCode": "100",
      "eventStatusDescription": "Authorized",
      "issueDate": "2018-10-01",
      "processStatusCode": "F00",
      "processStatusDescription": "Valid Signature, Document is Authorized at SEFAZ"
    }
  ],
  "notaFiscalFragmentList": [
    {
      "uuid": "ccf9e52b-e2e4-45d8-8884-0721d3246a53",
      "accessKey": "12901234567890123456789012345678901234567890",
      "companyCNPJ": "12901234567890",
      "companyRegion": "RS",
      "supplierCNPJ": "1234567890",
      "supplierRegion": "RS",
      "notaFiscalNumber": "1234590",
      "notaFiscalSeries": "001",
      "notaFiscalStatusCode": "100",
      "notaFiscalStatusDescription": "Authorized",
      "environmentType": "1",
      "issueType": "2",
      "issueDate": "2018-10-01",
      "processStatusCode": "F00",
      "processStatusDescription": "Valid Signature, Document is Authorized at SEFAZ"
    }
  ]
}
```

**Status Codes:**
- `200 OK` - Sucesso
- `401 Unauthorized`

---

#### DELETE /v1/deleteInboundInvoices
**Descrição:** Deleta informações de NF-es de entrada.

**Request Body:**
```json
{
  "uuidList": ["abc123-def456-ghi789"]
}
```

**Status Codes:**
- `204 No Content` - Deletado com sucesso
- `400 Bad Request` - Nenhum UUID informado
- `401 Unauthorized`

---

#### GET /v1/downloadOfficialDocument
**Descrição:** Faz download do arquivo XML de um documento oficial.

**Query Parameters:**
| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|-------------|-----------|
| accessKey | string | Sim | Chave de acesso (44 dígitos) |
| eventSequence | string | Não | Sequência do evento |
| eventType | string | Não | Tipo do evento |

**Response:** `application/xml`

**Status Codes:**
- `200 OK` - Download realizado
- `400 Bad Request` - Informação inválida
- `404 Not Found` - XML não encontrado
- `422 Unprocessable Entity` - Erro ao ler XML

---

#### DELETE /v1/deleteOfficialDocument
**Descrição:** Deleta o arquivo XML de um documento oficial.

**Query Parameters:**
| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|-------------|-----------|
| accessKey | string | Sim | Chave de acesso |
| eventSequence | string | Não | Sequência do evento |
| eventType | string | Não | Tipo do evento |

**Status Codes:**
- `204 No Content` - Deletado
- `400 Bad Request` - Informação inválida
- `404 Not Found` - XML não encontrado

---

#### POST /v1/receiveOfficialDocument
**Descrição:** Recebe o arquivo XML de um documento oficial.

**Request Body:**
```json
{
  "xml": "<?xml version=\"1.0\" encoding=\"utf-8\"?><nfeProc xmlns=\"http://www.portalfiscal.inf.br/nfe\" versao=\"4.00\"></nfeProc>"
}
```

**Status Codes:**
- `202 Accepted` - XML recebido
- `400 Bad Request` - Informação inválida
- `409 Conflict` - XML já existe
- `422 Unprocessable Entity` - Não foi possível processar

### Models

#### InboundInvoiceRetrieveRequest
| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| cnpj | array[string] | Sim | Lista de CNPJs |

#### InboundInvoiceDeleteRequest
| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| uuidList | array[string/uuid] | Sim | Lista de UUIDs |

#### OfficialDocumentReceiveRequest
| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| xml | string | Sim | Conteúdo XML do documento |

#### NotaFiscalFragment
| Campo | Tipo | Descrição |
|-------|------|-----------|
| uuid | string/uuid | Identificador único |
| accessKey | string | Chave de acesso (44 dígitos) |
| companyCNPJ | string | CNPJ da empresa |
| companyRegion | string | UF da empresa |
| supplierCNPJ | string | CNPJ do fornecedor |
| supplierRegion | string | UF do fornecedor |
| notaFiscalNumber | string | Número da NF |
| notaFiscalSeries | string | Série da NF |
| notaFiscalStatusCode | string | Código de status SEFAZ |
| notaFiscalStatusDescription | string | Descrição do status |
| environmentType | string | Tipo de ambiente (1=Prod, 2=Homolog) |
| issueType | string | Tipo de emissão |
| issueDate | date-time | Data de emissão |
| processStatusCode | string | Código de processamento |
| processStatusDescription | string | Descrição do processamento |

#### EventFragment
| Campo | Tipo | Descrição |
|-------|------|-----------|
| uuid | string/uuid | Identificador único |
| accessKey | string | Chave de acesso |
| eventType | string | Tipo do evento (ex: 110111) |
| eventSequence | string | Sequência do evento |
| eventDescription | string | Descrição do evento |
| eventStatusCode | string | Código de status SEFAZ |
| eventStatusDescription | string | Descrição do status |
| issueDate | date-time | Data |
| processStatusCode | string | Código de processamento |
| processStatusDescription | string | Descrição |

---

## 2. Distribution Service

**Descrição:** Permite distribuir arquivos de documentos fiscais eletrônicos por e-mail.

**Base URL (Sandbox):** `https://sandbox.api.sap.com/DocumentReportingComplianceInvoicing4Brazil/distribution-service`
**Base URL (Production):** `https://nfe.cfapps.br10.hana.ondemand.com/distribution-service`
**Versão:** 1.0.0

### Endpoints

#### POST /v1/distribution
**Descrição:** Envia uma requisição de distribuição por e-mail.

**Request Body:**
```json
{
  "documentId": "bfd8273d-0877-457f-81e7-eda52f82093d",
  "documentType": "NFE",
  "environmentType": "HOMOLOGATION",
  "action": "AUTHORIZE",
  "accessKey": "12345678901234567890123456789012345678901234",
  "receiverIdentifier": "13669157000652",
  "issuerIdentifier": "13669157000652",
  "mail": {
    "tradingName": "Trade name Inc.",
    "addressName": "SAP Street",
    "cityName": "Porto Alegre",
    "recipientName": "SAP",
    "phone": "555130811000",
    "qrCode": "https://dfe-portal.svrs.rs.gov.br/...",
    "emails": [
      {
        "type": "RECIPIENT",
        "email": "name@company.com"
      }
    ]
  },
  "attachments": [
    {
      "title": "43211074544297000192558190000567851490575375-procNFe",
      "content": "<base64>",
      "type": "FISCAL_DOCUMENT",
      "mimeType": "application/xml"
    }
  ]
}
```

**Status Codes:**
- `202 Accepted` - Requisição salva e enviada para processamento
- `400 Bad Request` - Formato de campo incorreto
- `500 Internal Server Error`

---

#### POST /v1/distribution-status
**Descrição:** Consulta o log de distribuição de documentos.

**Request Body:**
```json
{
  "documentIdList": ["bfd8273d-0877-457f-81e7-eda52f82093d"]
}
```

**Response (200 OK):**
```json
[
  {
    "documentId": "bfd8273d-0877-457f-81e7-eda52f82093d",
    "mailLog": {
      "processingStatus": "COMPLETED",
      "messageId": "1810874508.48175.1655930013505.JavaMail...",
      "dateTime": "2022-04-26T11:53:22.341Z",
      "senderList": ["test@email.com"],
      "mailStatusList": [
        {
          "type": "SUCCESS",
          "email": "email@test.com",
          "description": "The e-mail was successfully sent."
        }
      ]
    },
    "messages": [
      {
        "type": "ERROR",
        "distributionType": "MAIL",
        "text": "No recipient e-mail was found..."
      }
    ]
  }
]
```

---

#### DELETE /v1/distribution
**Descrição:** Deleta logs de distribuição.

**Request Body:**
```json
{
  "documentIdList": ["bfd8273d-0877-457f-81e7-eda52f82093d"]
}
```

**Status Codes:**
- `204 No Content` - Logs deletados
- `400 Bad Request`

### Models

#### DistributionRequest
| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| documentId | string | Sim | UUID do documento |
| documentType | enum | Sim | NFE, NFSE, NF3E, CTE, MDFE |
| environmentType | enum | Sim | PRODUCTION, HOMOLOGATION, TESTING |
| action | enum | Sim | AUTHORIZE, CANCEL, CCE, SKIP, EPEC |
| accessKey | string | Não | Chave de acesso (44 dígitos) |
| receiverIdentifier | string | Não | CNPJ do destinatário |
| issuerIdentifier | string | Não | CNPJ do emissor |
| mail | Mail | Sim | Dados do e-mail |
| attachments | array[Attachment] | Não | Anexos |

#### Mail
| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| tradingName | string | Sim | Nome fantasia |
| addressName | string | Sim | Endereço |
| cityName | string | Sim | Cidade |
| recipientName | string | Sim | Nome do destinatário |
| phone | string | Não | Telefone |
| qrCode | string | Não | URL do QR Code |
| emails | array[Address] | Não | Lista de e-mails |

#### Address
| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| type | enum | Sim | RECIPIENT, REPLY_TO |
| email | string | Sim | E-mail |

---

## 3. Download Electronic Documents (Storage Manager)

**Descrição:** Faz download de arquivos de documentos eletrônicos com várias extensões.

**Base URL (Sandbox):** `https://sandbox.api.sap.com/DocumentReportingComplianceInvoicing4Brazil/storage-manager`
**Base URL (Production):** `https://nfe.cfapps.br10.hana.ondemand.com/storage-manager`

_(Ver arquivo storage_manager-spec.json para especificação completa - API muito extensa)_

### Principais Endpoints

#### POST /v1/download
**Descrição:** Faz download de documentos eletrônicos.

#### POST /v1/upload
**Descrição:** Faz upload de documentos.

#### DELETE /v1/delete
**Descrição:** Deleta documentos armazenados.

---

## 4. Electronic Document Partner Connector

**Descrição:** Permite configurar destinos (destinations) na nuvem para parceiros.

**Base URL (Sandbox):** `https://sandbox.api.sap.com/DocumentReportingComplianceInvoicing4Brazil/electronic-document-partner-connector`
**Base URL (Production):** `https://nfe.cfapps.br10.hana.ondemand.com/electronic-document-partner-connector`

_(Ver arquivo electronic_document_partner_connector-spec.json para especificação completa)_

### Principais Endpoints

#### POST /v1/partner/destination
**Descrição:** Cria/atualiza configuração de destino do parceiro.

#### GET /v1/partner/destination
**Descrição:** Recupera configurações de destino.

#### DELETE /v1/partner/destination
**Descrição:** Remove configuração de destino.

---

## 5. Electronic Document Orchestrator

**Descrição:** Permite enviar e verificar o status de documentos eletrônicos processados pela solução do parceiro configurado.

**Base URL (Sandbox):** `https://sandbox.api.sap.com/DocumentReportingComplianceInvoicing4Brazil/electronic-document-orchestrator`
**Base URL (Production):** `https://nfe.cfapps.br10.hana.ondemand.com/electronic-document-orchestrator`

_(Ver arquivo electronic_document_orchestrator-spec.json para especificação completa - API muito extensa com ~60 endpoints)_

### Principais Endpoints

#### POST /v1/authorize
**Descrição:** Envia documento para autorização.

#### POST /v1/status
**Descrição:** Consulta status de documentos.

#### POST /v1/cancel
**Descrição:** Cancela documento.

#### POST /v1/cce
**Descrição:** Envia carta de correção.

---

## 6. Digital Certificate Storage

**Descrição:** Gerencia certificados digitais.

**Base URL (Sandbox):** `https://sandbox.api.sap.com/DocumentReportingComplianceInvoicing4Brazil/certificate-store`
**Base URL (Production):** `https://nfe.cfapps.br10.hana.ondemand.com/certificate-store`

### Endpoints

#### POST /v1/certificates
**Descrição:** Faz upload de um certificado digital.

**Request Body (multipart/form-data):**
```
file: <arquivo .pfx ou .p12>
password: <senha do certificado>
cnpj: <CNPJ associado>
validFrom: <data início validade>
validTo: <data fim validade>
```

**Status Codes:**
- `201 Created` - Certificado criado
- `400 Bad Request` - Dados inválidos
- `409 Conflict` - Certificado já existe

---

#### GET /v1/certificates
**Descrição:** Lista todos os certificados cadastrados.

**Response (200 OK):**
```json
[
  {
    "certificateId": "uuid",
    "cnpj": "12345678000199",
    "subjectCN": "Nome da Empresa",
    "issuerCN": "Autoridade Certificadora",
    "serialNumber": "123456789",
    "validFrom": "2024-01-01T00:00:00Z",
    "validTo": "2025-01-01T00:00:00Z",
    "status": "ACTIVE"
  }
]
```

---

#### GET /v1/certificates/{certificateId}
**Descrição:** Recupera detalhes de um certificado específico.

---

#### DELETE /v1/certificates/{certificateId}
**Descrição:** Remove um certificado.

**Status Codes:**
- `204 No Content` - Deletado
- `404 Not Found` - Não encontrado

---

## Autenticação

Todas as APIs usam **OAuth 2.0** (Client Credentials flow).

**Token URL (Sandbox):** `https://sandboxapihub.authentication.br10.hana.ondemand.com/oauth/token?grant_type=client_credentials`

**Token URL (Production):** `https://nfe-tenant-try-out.authentication.br10.hana.ondemand.com/oauth/token?grant_type=client_credentials`

**Headers obrigatórios:**
```
Authorization: Bearer {access_token}
Content-Type: application/json
```

---

## Arquivos de Especificação (OpenAPI/Swagger)

Os arquivos JSON completos das especificações estão em:
- `memory/sap/nfe-inbound-simple-spec.json`
- `memory/sap/distribution_service-spec.json`
- `memory/sap/storage_manager-spec.json`
- `memory/sap/electronic_document_partner_connector-spec.json`
- `memory/sap/electronic_document_orchestrator-spec.json`
- `memory/sap/certificate_store-spec.json`
