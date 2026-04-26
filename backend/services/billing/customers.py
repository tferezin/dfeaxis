"""Stripe Customer lifecycle — lazy creation, idempotent."""

from __future__ import annotations

import logging
from typing import Optional

from db.supabase import get_supabase_client

from .stripe_client import get_stripe

logger = logging.getLogger("dfeaxis.billing.customers")


def ensure_customer(tenant_id: str) -> str:
    """Returns the Stripe Customer ID for a tenant, creating one if missing.

    Idempotent: if tenants.stripe_customer_id is already set, returns it.
    Otherwise, creates a new Customer in Stripe linked to the tenant by
    metadata, persists the ID, and returns it.
    """
    sb = get_supabase_client()
    tenant = (
        sb.table("tenants")
        .select("id, email, company_name, stripe_customer_id, phone, cnpj")
        .eq("id", tenant_id)
        .single()
        .execute()
    )
    if not tenant.data:
        raise ValueError(f"Tenant {tenant_id} not found")

    if tenant.data.get("stripe_customer_id"):
        return tenant.data["stripe_customer_id"]

    stripe = get_stripe()
    # Item M2: idempotency_key elimina race condition entre 2 requests
    # paralelas pro mesmo tenant. Stripe garante que mesmo idempotency_key
    # sempre retorna o mesmo Customer (mesmo objeto, sem duplicacao).
    # Mais simples e barato que advisory lock no Postgres.
    customer = stripe.Customer.create(
        email=tenant.data.get("email"),
        name=tenant.data.get("company_name"),
        phone=tenant.data.get("phone"),
        metadata={
            "tenant_id": tenant_id,
            "cnpj": tenant.data.get("cnpj") or "",
        },
        idempotency_key=f"customer-{tenant_id}",
    )

    sb.table("tenants").update(
        {"stripe_customer_id": customer.id}
    ).eq("id", tenant_id).execute()

    logger.info("Created Stripe customer %s for tenant %s", customer.id, tenant_id)
    return customer.id


def get_customer_id(tenant_id: str) -> Optional[str]:
    """Returns the Stripe Customer ID without creating one."""
    sb = get_supabase_client()
    res = (
        sb.table("tenants")
        .select("stripe_customer_id")
        .eq("id", tenant_id)
        .single()
        .execute()
    )
    return (res.data or {}).get("stripe_customer_id")
