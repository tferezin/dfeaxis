"""Script standalone para testar conexão SEFAZ.

Recebe: PFX base64, senha, CNPJ, tipos
Retorna: JSON com resultado da consulta

Uso: python test_sefaz.py <pfx_base64> <senha> <cnpj> <tipos_csv>
"""

import base64
import gzip
import json
import os
import sys
import tempfile
import time

import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12
from lxml import etree


SEFAZ_ENDPOINTS = {
    "nfe": "https://hom.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx?wsdl",
    "cte": "https://hom1.cte.fazenda.gov.br/CTeDistribuicaoDFe/CTeDistribuicaoDFe.asmx?wsdl",
    "mdfe": "https://hom.mdfe.fazenda.gov.br/MdFeDistribuicaoDFe/MdFeDistribuicaoDFe.asmx?wsdl",
}

NAMESPACES = {
    "nfe": "http://www.portalfiscal.inf.br/nfe",
    "cte": "http://www.portalfiscal.inf.br/cte",
    "mdfe": "http://www.portalfiscal.inf.br/mdfe",
}

SERVICE_NAMES = {
    "nfe": "nfeDistDFeInteresse",
    "cte": "cteDistDFeInteresse",
    "mdfe": "mdfeDistDFeInteresse",
}


def consultar_sefaz(pfx_bytes, password, cnpj, tipo):
    """Consulta SEFAZ homologação para um tipo de documento."""
    from zeep import Client as ZeepClient
    from zeep.transports import Transport

    # Extrai cert e key do PFX
    private_key, certificate, chain = pkcs12.load_key_and_certificates(
        pfx_bytes, password.encode()
    )

    if not private_key or not certificate:
        return {"tipo": tipo, "status": "error", "message": "Certificado ou chave não encontrados no .pfx"}

    cert_pem = certificate.public_bytes(serialization.Encoding.PEM)
    key_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )

    # Adiciona cadeia intermediária
    chain_pem = b""
    if chain:
        for ca in chain:
            chain_pem += ca.public_bytes(serialization.Encoding.PEM)

    cert_file = None
    key_file = None
    try:
        cert_file = tempfile.NamedTemporaryFile(suffix=".pem", delete=False, mode="wb")
        cert_file.write(cert_pem + chain_pem)
        cert_file.flush()
        cert_file.close()

        key_file = tempfile.NamedTemporaryFile(suffix=".pem", delete=False, mode="wb")
        key_file.write(key_pem)
        key_file.flush()
        key_file.close()

        # Sessão mTLS
        session = requests.Session()
        session.cert = (cert_file.name, key_file.name)
        session.verify = True

        endpoint = SEFAZ_ENDPOINTS.get(tipo)
        if not endpoint:
            return {"tipo": tipo, "status": "error", "message": f"Tipo {tipo} não suportado para consulta SEFAZ"}

        ns = NAMESPACES[tipo]

        # Monta XML
        root = etree.Element("distDFeInt", nsmap={None: ns})
        root.set("versao", "1.01")
        etree.SubElement(root, "tpAmb").text = "2"  # Homologação
        etree.SubElement(root, "cUFAutor").text = "35"  # SP
        etree.SubElement(root, "CNPJ").text = cnpj
        dist_nsu = etree.SubElement(root, "distNSU")
        etree.SubElement(dist_nsu, "ultNSU").text = "000000000000000"

        # SOAP call
        start = time.time()
        transport = Transport(session=session, timeout=30)
        client = ZeepClient(wsdl=endpoint, transport=transport)

        service_name = SERVICE_NAMES[tipo]
        response = client.service[service_name](nfeDadosMsg=root)
        latency = int((time.time() - start) * 1000)

        # Parse response
        if isinstance(response, str):
            resp_root = etree.fromstring(response.encode())
        elif isinstance(response, bytes):
            resp_root = etree.fromstring(response)
        else:
            resp_root = response

        nsmap = {"ns": ns}

        def find_text(r, xpath):
            elem = r.find(xpath, nsmap)
            return elem.text if elem is not None else None

        cstat = find_text(resp_root, ".//ns:cStat") or "999"
        xmotivo = find_text(resp_root, ".//ns:xMotivo") or ""
        ult_nsu = find_text(resp_root, ".//ns:ultNSU") or "000000000000000"
        max_nsu = find_text(resp_root, ".//ns:maxNSU") or ult_nsu

        # Conta docs
        docs = list(resp_root.iter(f"{{{ns}}}docZip"))

        return {
            "tipo": tipo.upper(),
            "status": "success",
            "cstat": cstat,
            "xmotivo": xmotivo,
            "ult_nsu": ult_nsu,
            "max_nsu": max_nsu,
            "docs_found": len(docs),
            "latency_ms": latency,
        }

    except Exception as e:
        return {
            "tipo": tipo.upper(),
            "status": "error",
            "message": str(e),
        }
    finally:
        if cert_file and os.path.exists(cert_file.name):
            os.unlink(cert_file.name)
        if key_file and os.path.exists(key_file.name):
            os.unlink(key_file.name)


def main():
    if len(sys.argv) < 5:
        print(json.dumps({"error": "Uso: test_sefaz.py <pfx_base64> <senha> <cnpj> <tipos_csv>"}))
        sys.exit(1)

    pfx_b64 = sys.argv[1]
    password = sys.argv[2]
    cnpj = sys.argv[3]
    tipos = sys.argv[4].split(",")

    try:
        pfx_bytes = base64.b64decode(pfx_b64)
    except Exception:
        print(json.dumps({"error": "PFX base64 inválido"}))
        sys.exit(1)

    # Valida o certificado primeiro
    try:
        pk, cert, _ = pkcs12.load_key_and_certificates(pfx_bytes, password.encode())
        if not pk or not cert:
            print(json.dumps({"error": "Certificado ou chave não encontrados no .pfx"}))
            sys.exit(1)

        cert_info = {
            "subject": str(cert.subject),
            "valid_from": str(cert.not_valid_before_utc),
            "valid_until": str(cert.not_valid_after_utc),
        }
    except Exception as e:
        print(json.dumps({"error": f"Senha incorreta ou arquivo .pfx inválido: {e}"}))
        sys.exit(1)

    results = []
    for tipo in tipos:
        tipo = tipo.strip().lower()
        if tipo == "nfse":
            results.append({
                "tipo": "NFSE",
                "status": "skipped",
                "message": "NFS-e usa API REST (ADN), não SOAP. Teste separado necessário.",
            })
            continue
        result = consultar_sefaz(pfx_bytes, password, cnpj, tipo)
        results.append(result)

    output = {
        "certificate": cert_info,
        "cnpj": cnpj,
        "ambiente": "Homologação",
        "results": results,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
