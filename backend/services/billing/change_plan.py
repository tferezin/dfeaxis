"""Change-plan flow para tenants ja pagantes.

Stripe Checkout Session (`mode='subscription'`) cria uma SUBSCRIPTION NOVA —
serve so pra primeiro pagamento. Cliente que ja tem `stripe_subscription_id`
ativa precisa do `Subscription.modify` API pra trocar de plano sem ser cobrado
em duplicidade.

Este modulo encapsula essa logica + aplica o mesmo gate de max_cnpjs do
checkout (espelho de routers/billing.py:checkout).
"""

from __future__ import annotations

import logging
from typing import Literal

from db.supabase import get_supabase_client
from services.billing.plans import get_plan_by_price_id
from services.billing.stripe_client import get_stripe

logger = logging.getLogger("dfeaxis.billing.change_plan")


class ChangePlanError(Exception):
    """Erros de negocio ao trocar de plano (pra mapear em HTTPException)."""

    def __init__(self, code: str, message: str, **extra) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.extra = extra


def change_subscription_plan(
    tenant_id: str,
    new_price_id: str,
    proration_behavior: Literal["create_prorations", "none"] = "create_prorations",
) -> dict:
    """Troca o plano da subscription ATIVA do tenant.

    Aplica o gate de max_cnpjs antes de chamar Stripe — bloqueia troca pra
    plano que nao comporta o numero atual de certificados ativos.

    Levanta `ChangePlanError` em casos de negocio:
      - NOT_A_SUBSCRIBER: tenant ainda nao tem stripe_subscription_id
      - INVALID_PRICE_ID: price_id fora do catalogo
      - PLAN_CNPJ_LIMIT_EXCEEDED: count_certs > max_cnpjs do novo plano
      - SAME_PLAN: novo price_id == price atual (no-op)
      - SUBSCRIPTION_INACTIVE: sub esta cancelada/expirada (sem Subscription.modify)

    Retorna dict com `subscription_id`, `new_price_id`, `status`.
    """
    target = get_plan_by_price_id(new_price_id)
    if target is None:
        raise ChangePlanError(
            "INVALID_PRICE_ID",
            f"price_id {new_price_id} nao esta no catalogo de planos",
        )

    sb = get_supabase_client()
    tenant_row = sb.table("tenants").select(
        "stripe_subscription_id, subscription_status"
    ).eq("id", tenant_id).single().execute()
    tenant_data = tenant_row.data or {}
    subscription_id = tenant_data.get("stripe_subscription_id")

    if not subscription_id:
        raise ChangePlanError(
            "NOT_A_SUBSCRIBER",
            "Tenant ainda nao possui assinatura ativa. Use /billing/checkout.",
        )

    sub_status = tenant_data.get("subscription_status")
    # past_due e ok — cliente pode reduzir pra resolver pagamento pendente.
    # cancelled/expired NAO da pra modificar via API — Stripe rejeita.
    if sub_status in ("cancelled", "expired"):
        raise ChangePlanError(
            "SUBSCRIPTION_INACTIVE",
            f"Sua assinatura esta {sub_status}. Faca uma nova adesao via /billing/checkout.",
        )

    # Gate: count de certificados ativos vs max_cnpjs do plano alvo.
    cert_count = sb.table("certificates").select(
        "id", count="exact"
    ).eq("tenant_id", tenant_id).eq("is_active", True).execute().count or 0

    if cert_count > target.plan.max_cnpjs:
        raise ChangePlanError(
            "PLAN_CNPJ_LIMIT_EXCEEDED",
            (
                f"Voce tem {cert_count} CNPJs cadastrados, mas o plano "
                f"{target.plan.name} permite ate {target.plan.max_cnpjs}. "
                "Escolha um plano compativel ou remova certificados antes."
            ),
            cnpj_count=cert_count,
            plan_max_cnpjs=target.plan.max_cnpjs,
            plan_key=target.plan.key,
        )

    stripe = get_stripe()
    sub = stripe.Subscription.retrieve(subscription_id)
    items = (sub.get("items") or {}).get("data") or []
    if not items:
        raise ChangePlanError(
            "SUBSCRIPTION_INVALID_STATE",
            "Subscription nao tem itens — estado invalido. Contate suporte.",
        )

    current_item = items[0]
    current_price_id = (current_item.get("price") or {}).get("id")

    if current_price_id == new_price_id:
        raise ChangePlanError(
            "SAME_PLAN",
            "Voce ja esta neste plano.",
        )

    # Modifica subscription mantendo o mesmo billing cycle. Stripe calcula
    # prorata automaticamente entre o item antigo (refund parcial) e o novo
    # (cobranca parcial) na proxima fatura.
    updated = stripe.Subscription.modify(
        subscription_id,
        items=[{"id": current_item["id"], "price": new_price_id}],
        proration_behavior=proration_behavior,
        metadata={
            **(sub.get("metadata") or {}),
            "tenant_id": tenant_id,
            "last_plan_change_to": new_price_id,
        },
    )

    logger.info(
        "Tenant %s trocou de plano: %s -> %s (sub=%s, proration=%s)",
        tenant_id, current_price_id, new_price_id, subscription_id,
        proration_behavior,
    )

    return {
        "subscription_id": updated["id"],
        "new_price_id": new_price_id,
        "previous_price_id": current_price_id,
        "status": updated.get("status"),
        "plan_key": target.plan.key,
    }
