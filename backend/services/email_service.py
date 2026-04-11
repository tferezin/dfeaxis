"""Email service (Resend) for transactional emails.

Graceful: if RESEND_API_KEY is empty (dev/test), logs a warning and returns
False without raising. All successful sends are logged for audit.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from config import get_settings

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "emails"


class EmailService:
    """Thin wrapper around Resend + Jinja2 templates."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.env = Environment(
            loader=FileSystemLoader(str(_TEMPLATES_DIR)),
            autoescape=select_autoescape(["html", "xml"]),
        )
        self._resend = None  # lazily imported to keep module safe in dev

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _render(self, template_name: str, **context) -> str:
        template = self.env.get_template(template_name)
        return template.render(**context)

    def _send(
        self,
        to_email: str,
        subject: str,
        html: str,
        email_type: str,
    ) -> bool:
        """Low-level send. Returns True on success, False on graceful skip/fail."""
        api_key = self.settings.resend_api_key
        from_email = self.settings.resend_from_email

        if not api_key:
            logger.warning(
                "Resend API key empty — email not sent",
                extra={
                    "email_type": email_type,
                    "to": to_email,
                    "subject": subject,
                },
            )
            return False

        try:
            if self._resend is None:
                import resend  # type: ignore

                resend.api_key = api_key
                self._resend = resend

            params = {
                "from": from_email,
                "to": [to_email],
                "subject": subject,
                "html": html,
            }
            response = self._resend.Emails.send(params)  # type: ignore[attr-defined]

            logger.info(
                "Email sent",
                extra={
                    "email_type": email_type,
                    "to": to_email,
                    "subject": subject,
                    "resend_id": (response or {}).get("id") if isinstance(response, dict) else None,
                },
            )
            return True

        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Failed to send email via Resend",
                extra={
                    "email_type": email_type,
                    "to": to_email,
                    "subject": subject,
                    "error": str(exc),
                },
            )
            return False

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def send_trial_nudge(
        self,
        to_email: str,
        name: str,
        days_remaining: int,
        docs_consumed: int,
        docs_cap: int,
    ) -> bool:
        html = self._render(
            "trial_nudge.html",
            name=name,
            days_remaining=days_remaining,
            docs_consumed=docs_consumed,
            docs_cap=docs_cap,
        )
        subject = (
            f"Faltam {days_remaining} dia(s) no seu trial DFeAxis"
            if days_remaining > 0
            else "Seu trial DFeAxis encerra hoje"
        )
        return self._send(to_email, subject, html, email_type="trial_nudge")

    def send_trial_cap_warning(
        self,
        to_email: str,
        name: str,
        docs_consumed: int,
        docs_cap: int,
    ) -> bool:
        html = self._render(
            "trial_cap_warning.html",
            name=name,
            docs_consumed=docs_consumed,
            docs_cap=docs_cap,
        )
        subject = "Você está perto do limite do trial DFeAxis"
        return self._send(to_email, subject, html, email_type="trial_cap_warning")

    def send_trial_expired(
        self,
        to_email: str,
        name: str,
        reason: str = "time",
    ) -> bool:
        """reason: 'time' (trial_expires_at passed) or 'cap' (docs cap hit)."""
        if reason not in ("time", "cap"):
            reason = "time"
        html = self._render("trial_expired.html", name=name, reason=reason)
        subject = "Seu trial DFeAxis encerrou — assine para continuar"
        return self._send(to_email, subject, html, email_type="trial_expired")


# Singleton
email_service = EmailService()
