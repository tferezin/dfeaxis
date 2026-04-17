"""FakeSefazClient — substitui services.sefaz_client.sefaz_client em testes.

Permite cenários determinísticos sem bater na SEFAZ real nem exigir cert A1.
Mantém estado em memória por (cnpj, tipo), respeita batching de 50 docs
(como a SEFAZ real no DistDFeInteresse), e expõe helpers pra seed/force_error.

Uso típico em teste:

    from tests.fakes.sefaz_fake import FakeSefazClient
    from services import sefaz_client as sefaz_module

    fake = FakeSefazClient()
    fake.seed_documents("12345678000199", "nfe", count=550)
    monkeypatch.setattr(sefaz_module, "sefaz_client", fake)

Os dataclasses SefazDocument / SefazResponse são redeclarados aqui em vez de
importados do módulo real pra evitar import circular em testes e pra manter
o fake auto-contido (o consumidor só espera duck-typing nos atributos).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

# Batch size da SEFAZ real no DistDFeInteresse.
BATCH_SIZE = 50

# Modelo por tipo (chave de acesso, posições 20-21).
_MODELO = {"nfe": "55", "cte": "57", "mdfe": "58"}

# Namespaces (mesmo do sefaz_client real — usados só pra gerar XML).
_NAMESPACES = {
    "nfe": "http://www.portalfiscal.inf.br/nfe",
    "cte": "http://www.portalfiscal.inf.br/cte",
    "mdfe": "http://www.portalfiscal.inf.br/mdfe",
}


@dataclass
class SefazDocument:
    """Espelho do services.sefaz_client.SefazDocument — duck-typed."""
    chave: str
    tipo: str
    nsu: str
    xml_content: str
    schema: str


@dataclass
class SefazResponse:
    """Espelho do services.sefaz_client.SefazResponse — duck-typed."""
    cstat: str
    xmotivo: str
    ult_nsu: str
    max_nsu: str
    documents: list[SefazDocument]
    latency_ms: int


@dataclass
class FakeDoc:
    """Um documento na fila fake, ordenado por NSU."""
    nsu: int                 # inteiro, formatado depois
    chave: str
    xml_content: str
    schema: str
    tipo: str


# --------------------------------------------------------------------------
# Helpers internos (geração de chave + XML)
# --------------------------------------------------------------------------

def _mod11_dv(chave43: str) -> str:
    """Dígito verificador módulo 11 padrão SEFAZ (44º dígito da chave)."""
    weights = [2, 3, 4, 5, 6, 7, 8, 9]
    total = 0
    for i, ch in enumerate(reversed(chave43)):
        total += int(ch) * weights[i % len(weights)]
    resto = total % 11
    dv = 11 - resto
    if dv >= 10:
        dv = 0
    return str(dv)


def _generate_chave(cnpj_emit: str, tipo: str, numero: int) -> str:
    """Gera chave de acesso fake com estrutura válida (44 dígitos + DV mod11).

    - 0-1   : cUF = 35 (SP)
    - 2-5   : AAMM (ano/mês corrente)
    - 6-19  : CNPJ do emitente
    - 20-21 : modelo (55/57/58)
    - 22-24 : série (001)
    - 25-33 : nNF (zero-padded)
    - 34    : tpEmis = 1
    - 35-42 : cNF (zero-padded do número)
    - 43    : DV mod11
    """
    cnpj_14 = (cnpj_emit or "").rjust(14, "0")[-14:]
    now = datetime.now(timezone.utc)
    aamm = f"{now.year % 100:02d}{now.month:02d}"
    modelo = _MODELO.get(tipo, "55")
    serie = "001"
    n_nf = f"{numero:09d}"
    tp_emis = "1"
    c_nf = f"{numero:08d}"
    chave43 = f"35{aamm}{cnpj_14}{modelo}{serie}{n_nf}{tp_emis}{c_nf}"
    dv = _mod11_dv(chave43)
    return chave43 + dv


def _generate_xml(tipo: str, chave: str, cnpj_emit: str, cnpj_dest: str, numero: int) -> str:
    """Gera XML mínimo válido por tipo, com os campos essenciais que o
    parser do DFeAxis costuma extrair (emit, dest, valores, dhEmi)."""
    ns = _NAMESPACES[tipo]
    dh_emi = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S-03:00")
    cnpj_e = (cnpj_emit or "").rjust(14, "0")[-14:]
    cnpj_d = (cnpj_dest or "").rjust(14, "0")[-14:]

    if tipo == "nfe":
        return (
            f'<nfeProc xmlns="{ns}" versao="4.00">'
            f'<NFe xmlns="{ns}">'
            f'<infNFe Id="NFe{chave}" versao="4.00">'
            f'<ide><cUF>35</cUF><nNF>{numero}</nNF><dhEmi>{dh_emi}</dhEmi>'
            f'<mod>55</mod><serie>1</serie><tpNF>1</tpNF></ide>'
            f'<emit><CNPJ>{cnpj_e}</CNPJ><xNome>FAKE EMIT {numero}</xNome></emit>'
            f'<dest><CNPJ>{cnpj_d}</CNPJ><xNome>FAKE DEST</xNome></dest>'
            f'<total><ICMSTot><vNF>{100 + numero:.2f}</vNF></ICMSTot></total>'
            f'<infProt><chNFe>{chave}</chNFe></infProt>'
            f'</infNFe></NFe></nfeProc>'
        )
    if tipo == "cte":
        return (
            f'<cteProc xmlns="{ns}" versao="4.00">'
            f'<CTe xmlns="{ns}">'
            f'<infCte Id="CTe{chave}" versao="4.00">'
            f'<ide><cUF>35</cUF><nCT>{numero}</nCT><dhEmi>{dh_emi}</dhEmi>'
            f'<mod>57</mod><serie>1</serie></ide>'
            f'<emit><CNPJ>{cnpj_e}</CNPJ><xNome>FAKE TRANSP {numero}</xNome></emit>'
            f'<dest><CNPJ>{cnpj_d}</CNPJ><xNome>FAKE DEST</xNome></dest>'
            f'<vPrest><vTPrest>{50 + numero:.2f}</vTPrest></vPrest>'
            f'<infCarga><vCarga>{500 + numero:.2f}</vCarga></infCarga>'
            f'<infProt><chCTe>{chave}</chCTe></infProt>'
            f'</infCte></CTe></cteProc>'
        )
    # mdfe
    return (
        f'<mdfeProc xmlns="{ns}" versao="3.00">'
        f'<MDFe xmlns="{ns}">'
        f'<infMDFe Id="MDFe{chave}" versao="3.00">'
        f'<ide><cUF>35</cUF><nMDF>{numero}</nMDF><dhEmi>{dh_emi}</dhEmi>'
        f'<mod>58</mod><serie>1</serie></ide>'
        f'<emit><CNPJ>{cnpj_e}</CNPJ><xNome>FAKE TRANSP {numero}</xNome></emit>'
        f'<infProt><chMDFe>{chave}</chMDFe></infProt>'
        f'</infMDFe></MDFe></mdfeProc>'
    )


# --------------------------------------------------------------------------
# FakeSefazClient
# --------------------------------------------------------------------------

class FakeSefazClient:
    """Fake in-memory do SefazClient — compatível por duck-typing.

    Respeita o protocolo de batching: cada chamada devolve no máximo
    BATCH_SIZE (=50) documentos com NSU > ult_nsu. `max_nsu` aponta
    sempre pro maior NSU na fila.
    """

    def __init__(self) -> None:
        # (cnpj, tipo) -> lista de FakeDoc ordenada por nsu
        self._queues: dict[tuple[str, str], list[FakeDoc]] = {}
        # Erro agendado pra próxima chamada de (cnpj, tipo)
        self._errors: dict[tuple[str, str], dict] = {}
        # Log de chamadas pra assertions
        self._call_log: list[dict] = []
        # Latency simulada (ms) devolvida no SefazResponse
        self._latency_ms: int = 50
        # Ambiente pra manter compatibilidade de atributo com o real
        self.ambiente: str = "2"

    # -------------- Setup helpers --------------

    def seed_documents(
        self,
        cnpj: str,
        tipo: str,
        count: int,
        schema: str = "procNFe",
        start_nsu: int = 1,
        cnpj_emit: str = "11222333000181",
    ) -> list[str]:
        """Popula a fila fake com N docs. Retorna lista de chaves geradas."""
        if count <= 0:
            self._queues.setdefault((cnpj, tipo), [])
            return []

        key = (cnpj, tipo)
        queue = self._queues.setdefault(key, [])
        # Continua da sequência existente se já houver docs
        next_nsu = max(start_nsu, (queue[-1].nsu + 1) if queue else start_nsu)

        chaves: list[str] = []
        for i in range(count):
            nsu = next_nsu + i
            chave = _generate_chave(cnpj_emit, tipo, nsu)
            xml = _generate_xml(tipo, chave, cnpj_emit, cnpj, nsu)
            queue.append(FakeDoc(
                nsu=nsu,
                chave=chave,
                xml_content=xml,
                schema=schema,
                tipo=tipo,
            ))
            chaves.append(chave)
        return chaves

    def seed_with_xml(self, cnpj: str, tipo: str, xml_contents: list[str]) -> None:
        """Popula com XMLs específicos. Cada item vira um FakeDoc com NSU
        sequencial continuando da fila existente."""
        key = (cnpj, tipo)
        queue = self._queues.setdefault(key, [])
        next_nsu = (queue[-1].nsu + 1) if queue else 1
        for i, xml in enumerate(xml_contents):
            nsu = next_nsu + i
            # Chave gerada determinística mas sintética — se o teste precisar
            # da chave real, extrair do XML.
            chave = _generate_chave("00000000000000", tipo, nsu)
            queue.append(FakeDoc(
                nsu=nsu,
                chave=chave,
                xml_content=xml,
                schema="procNFe" if tipo == "nfe" else f"proc{tipo.upper()}",
                tipo=tipo,
            ))

    def force_error(
        self,
        cnpj: str,
        tipo: str,
        cstat: str,
        xmotivo: str = "",
    ) -> None:
        """Próxima chamada consultar_distribuicao(cnpj, tipo) retorna esse erro.
        Depois o comportamento normal volta."""
        self._errors[(cnpj, tipo)] = {"cstat": str(cstat), "xmotivo": xmotivo}

    def clear(self) -> None:
        """Limpa todo estado — usar em teardown."""
        self._queues.clear()
        self._errors.clear()
        self._call_log.clear()

    def get_calls(
        self, cnpj: str | None = None, tipo: str | None = None,
    ) -> list[dict]:
        """Retorna log de chamadas. Filtra por cnpj/tipo se fornecidos."""
        calls = self._call_log
        if cnpj is not None:
            calls = [c for c in calls if c["cnpj"] == cnpj]
        if tipo is not None:
            calls = [c for c in calls if c["tipo"] == tipo]
        return list(calls)

    def set_latency(self, ms: int) -> None:
        self._latency_ms = int(ms)

    # -------------- API compatível com SefazClient real --------------

    def consultar_distribuicao(
        self,
        cnpj: str,
        tipo: str,
        ult_nsu: str,
        pfx_encrypted: Any = None,
        pfx_iv: Any = None,
        tenant_id: str = "",
        pfx_password: str = "",
        cuf_autor: str = "35",
        ambiente: Optional[str] = None,
    ) -> SefazResponse:
        """Simula chamada SEFAZ respeitando cursor NSU e batching de 50."""
        # Normaliza ult_nsu pra int (o real usa string zero-padded de 15 chars)
        try:
            ult_nsu_int = int((ult_nsu or "0").strip() or "0")
        except ValueError:
            ult_nsu_int = 0

        key = (cnpj, tipo)
        self._call_log.append({
            "cnpj": cnpj,
            "tipo": tipo,
            "ult_nsu": ult_nsu_int,
            "ambiente": ambiente or self.ambiente,
            "cuf_autor": cuf_autor,
            "tenant_id": tenant_id,
        })

        # Erro forçado tem prioridade máxima
        if key in self._errors:
            err = self._errors.pop(key)
            return SefazResponse(
                cstat=err["cstat"],
                xmotivo=err["xmotivo"],
                ult_nsu=_fmt_nsu(ult_nsu_int),
                max_nsu=_fmt_nsu(ult_nsu_int),
                documents=[],
                latency_ms=self._latency_ms,
            )

        queue = self._queues.get(key, [])

        if not queue:
            # Nenhum doc jamais — cstat 137 "nenhum documento localizado"
            return SefazResponse(
                cstat="137",
                xmotivo="Nenhum documento localizado para o destinatário",
                ult_nsu=_fmt_nsu(ult_nsu_int),
                max_nsu=_fmt_nsu(ult_nsu_int),
                documents=[],
                latency_ms=self._latency_ms,
            )

        max_nsu_int = queue[-1].nsu

        # Pega docs com nsu > ult_nsu_int, até BATCH_SIZE
        pending = [d for d in queue if d.nsu > ult_nsu_int][:BATCH_SIZE]

        if not pending:
            # Fila esgotada do ponto de vista desse cursor
            return SefazResponse(
                cstat="137",
                xmotivo="Nenhum documento localizado para o destinatário",
                ult_nsu=_fmt_nsu(max_nsu_int),
                max_nsu=_fmt_nsu(max_nsu_int),
                documents=[],
                latency_ms=self._latency_ms,
            )

        documents = [
            SefazDocument(
                chave=d.chave,
                tipo=tipo.upper(),
                nsu=_fmt_nsu(d.nsu),
                xml_content=d.xml_content,
                schema=d.schema,
            )
            for d in pending
        ]

        new_ult_nsu = pending[-1].nsu
        # cstat 138 = documento localizado
        return SefazResponse(
            cstat="138",
            xmotivo="Documento localizado",
            ult_nsu=_fmt_nsu(new_ult_nsu),
            max_nsu=_fmt_nsu(max_nsu_int),
            documents=documents,
            latency_ms=self._latency_ms,
        )

    # Compat: o real também expõe check_status
    def check_status(self, tipo: str) -> dict:
        return {
            "tipo": tipo,
            "ambiente": "homologação" if self.ambiente == "2" else "produção",
            "status": "online",
            "latency_ms": self._latency_ms,
        }


def _fmt_nsu(n: int) -> str:
    """Formata NSU no padrão 15 chars zero-padded (igual ao sefaz_client real)."""
    return str(max(0, int(n))).zfill(15)
