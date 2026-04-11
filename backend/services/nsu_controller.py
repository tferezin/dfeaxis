"""Controle de NSU sem gaps — garante sequência contínua."""

import logging
from db.supabase import get_supabase_client

logger = logging.getLogger(__name__)


class NSUController:
    """Gerencia NSUs para garantir que não haja gaps na sequência."""

    def update_last_nsu(
        self, cert_id: str, tipo: str, new_nsu: str
    ) -> None:
        """[LEGACY] Atualiza o último NSU processado em certificates.

        Mantido por compatibilidade; novo código deve usar update_cursor().
        """
        sb = get_supabase_client()
        column = f"last_nsu_{tipo}"
        sb.table("certificates").update(
            {column: new_nsu, "last_polling_at": "now()"}
        ).eq("id", cert_id).execute()

    def get_last_nsu(self, cert_id: str, tipo: str) -> str:
        """[LEGACY] Retorna o último NSU processado de certificates."""
        sb = get_supabase_client()
        column = f"last_nsu_{tipo}"
        result = sb.table("certificates").select(column).eq(
            "id", cert_id
        ).execute()

        if result.data:
            return result.data[0].get(column, "000000000000000")
        return "000000000000000"

    # ------------------------------------------------------------------
    # nsu_state (novo controle por certificate_id + tipo + ambiente)
    # ------------------------------------------------------------------

    def get_cursor(
        self, certificate_id: str, tipo: str, ambiente: str
    ) -> str:
        """Retorna last_nsu de nsu_state para (cert, tipo, ambiente).

        Se não houver linha ainda, retorna '000000000000000'.
        """
        sb = get_supabase_client()
        try:
            result = sb.table("nsu_state").select("last_nsu").eq(
                "certificate_id", certificate_id
            ).eq("tipo", tipo).eq("ambiente", ambiente).execute()
            if result.data:
                return result.data[0].get("last_nsu") or "000000000000000"
        except Exception as e:
            logger.warning(f"get_cursor falhou ({certificate_id}/{tipo}/{ambiente}): {e}")
        return "000000000000000"

    def update_cursor(
        self,
        certificate_id: str,
        tipo: str,
        ambiente: str,
        last_nsu: str,
        max_nsu: str | None = None,
    ) -> None:
        """Upsert no nsu_state — atualiza last_nsu (e opcionalmente max_nsu/pendentes)."""
        sb = get_supabase_client()
        payload: dict = {
            "certificate_id": certificate_id,
            "tipo": tipo,
            "ambiente": ambiente,
            "last_nsu": last_nsu,
            "updated_at": "now()",
        }
        if max_nsu is not None:
            payload["max_nsu"] = max_nsu
            try:
                payload["pendentes"] = max(int(max_nsu) - int(last_nsu), 0)
            except (TypeError, ValueError):
                payload["pendentes"] = 0
        try:
            sb.table("nsu_state").upsert(
                payload, on_conflict="certificate_id,tipo,ambiente"
            ).execute()
        except Exception as e:
            logger.warning(
                f"update_cursor falhou ({certificate_id}/{tipo}/{ambiente}): {e}"
            )

    def update_pending_count(
        self,
        certificate_id: str,
        tipo: str,
        ambiente: str,
        max_nsu: str,
    ) -> None:
        """Atualiza max_nsu + pendentes no nsu_state sem mover last_nsu.

        Usado quando o trial está bloqueado no cap e não devemos avançar o cursor,
        mas ainda queremos saber quantos documentos ficaram pendentes na SEFAZ.
        """
        sb = get_supabase_client()
        last = self.get_cursor(certificate_id, tipo, ambiente)
        try:
            pendentes = max(int(max_nsu) - int(last), 0)
        except (TypeError, ValueError):
            pendentes = 0
        try:
            sb.table("nsu_state").upsert(
                {
                    "certificate_id": certificate_id,
                    "tipo": tipo,
                    "ambiente": ambiente,
                    "last_nsu": last,
                    "max_nsu": max_nsu,
                    "pendentes": pendentes,
                    "updated_at": "now()",
                },
                on_conflict="certificate_id,tipo,ambiente",
            ).execute()
        except Exception as e:
            logger.warning(
                f"update_pending_count falhou ({certificate_id}/{tipo}/{ambiente}): {e}"
            )

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
