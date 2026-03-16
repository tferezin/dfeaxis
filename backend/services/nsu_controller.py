"""Controle de NSU sem gaps — garante sequência contínua."""

import logging
from db.supabase import get_supabase_client

logger = logging.getLogger(__name__)


class NSUController:
    """Gerencia NSUs para garantir que não haja gaps na sequência."""

    def update_last_nsu(
        self, cert_id: str, tipo: str, new_nsu: str
    ) -> None:
        """Atualiza o último NSU processado para um certificado/tipo."""
        sb = get_supabase_client()
        column = f"last_nsu_{tipo}"
        sb.table("certificates").update(
            {column: new_nsu, "last_polling_at": "now()"}
        ).eq("id", cert_id).execute()

    def get_last_nsu(self, cert_id: str, tipo: str) -> str:
        """Retorna o último NSU processado."""
        sb = get_supabase_client()
        column = f"last_nsu_{tipo}"
        result = sb.table("certificates").select(column).eq(
            "id", cert_id
        ).execute()

        if result.data:
            return result.data[0].get(column, "000000000000000")
        return "000000000000000"

    def detect_gap(self, last_nsu: str, received_nsus: list[str]) -> list[str]:
        """Detecta gaps na sequência de NSUs recebidos.

        Retorna lista de NSUs faltantes (se houver).
        """
        if not received_nsus:
            return []

        last = int(last_nsu)
        received = sorted(int(n) for n in received_nsus)
        missing = []

        expected = last + 1
        for nsu in received:
            while expected < nsu:
                missing.append(str(expected).zfill(15))
                expected += 1
            expected = nsu + 1

        if missing:
            logger.warning(
                f"NSU gap detected: {len(missing)} missing after {last_nsu}"
            )

        return missing

    def record_dead_letter(
        self, tenant_id: str, cnpj: str, tipo: str, nsu: str, error: str
    ) -> None:
        """Registra NSU que falhou múltiplas vezes (dead letter)."""
        sb = get_supabase_client()
        sb.table("polling_log").insert({
            "tenant_id": tenant_id,
            "cnpj": cnpj,
            "tipo": tipo,
            "triggered_by": "dead_letter",
            "status": "error",
            "ult_nsu": nsu,
            "error_message": error,
        }).execute()


nsu_controller = NSUController()
