"""Plan / Price catalog.

Maps Stripe price IDs (price_xxx) to plan metadata. After running
`scripts/seed_stripe_products.py`, the seed script writes a JSON file
with the actual IDs which is loaded here.

The seed file is gitignored — each environment (dev/staging/prod) has
its own price IDs.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

logger = logging.getLogger("dfeaxis.billing.plans")

PLANS_FILE = Path(__file__).parent.parent.parent / "data" / "stripe_plans.json"


@dataclass(frozen=True)
class Plan:
    key: str  # 'starter' | 'business' | 'enterprise'
    name: str  # display name
    description: str
    price_id_monthly: str
    price_id_yearly: str
    monthly_amount_cents: int
    yearly_amount_cents: int
    docs_included: int
    overage_cents_per_doc: int
    max_cnpjs: int
    features: list[str]


@dataclass(frozen=True)
class PriceLookup:
    plan: Plan
    period: Literal["monthly", "yearly"]


# Default catalog — used as a template by seed script and as a fallback when
# stripe_plans.json hasn't been generated yet (price IDs will be empty).
DEFAULT_PLAN_CATALOG: list[dict] = [
    {
        "key": "starter",
        "name": "Starter",
        "description": "Para empresas que estão começando com captura automática de DF-e.",
        "monthly_amount_cents": 29000,  # R$ 290,00
        "yearly_amount_cents": 278400,  # R$ 232,00/mês × 12 (-20%)
        "docs_included": 3000,
        "overage_cents_per_doc": 12,  # R$ 0,12
        "max_cnpjs": 1,
        "features": [
            "1 CNPJ monitorado",
            "3.000 docs/mês inclusos",
            "NF-e + CT-e + MDF-e + NFS-e",
            "Manifestação manual ou automática",
            "API REST + SAP DRC",
        ],
    },
    {
        "key": "business",
        "name": "Business",
        "description": "Para empresas em operação plena com volume relevante.",
        "monthly_amount_cents": 69000,  # R$ 690,00
        "yearly_amount_cents": 662400,  # R$ 552,00/mês × 12
        "docs_included": 8000,
        "overage_cents_per_doc": 9,
        "max_cnpjs": 5,
        "features": [
            "Até 5 CNPJs",
            "8.000 docs/mês inclusos",
            "NF-e + CT-e + MDF-e + NFS-e",
            "Manifestação manual ou automática",
            "API REST + SAP DRC",
        ],
    },
    {
        "key": "enterprise",
        "name": "Enterprise",
        "description": "Grandes grupos e holdings com alto volume.",
        "monthly_amount_cents": 149000,  # R$ 1.490,00
        "yearly_amount_cents": 1430400,  # R$ 1.192,00/mês × 12
        "docs_included": 20000,
        "overage_cents_per_doc": 7,
        "max_cnpjs": 50,
        "features": [
            "Até 50 CNPJs",
            "20.000 docs/mês inclusos",
            "Todos os tipos de documento",
            "Manifestação manual ou automática",
            "API REST + SAP DRC",
            "Questionário de segurança incluso",
        ],
    },
]


_PLAN_FIELDS = {f for f in Plan.__dataclass_fields__}


@lru_cache(maxsize=1)
def load_plans() -> list[Plan]:
    """Loads plans from data/stripe_plans.json (created by seed script).

    If the file doesn't exist, returns plans with empty price IDs (useful
    for tests / dev environments without Stripe configured yet).

    Extra fields in the JSON (e.g., stripe_product_id) are silently ignored
    so the Plan dataclass stays lean and the seed file can carry metadata.
    """
    catalog: list[dict] = []
    if PLANS_FILE.exists():
        try:
            with PLANS_FILE.open() as f:
                catalog = json.load(f)
        except Exception as e:
            logger.warning("Failed to read %s: %s — using defaults", PLANS_FILE, e)

    if not catalog:
        catalog = [{**p, "price_id_monthly": "", "price_id_yearly": ""} for p in DEFAULT_PLAN_CATALOG]

    plans: list[Plan] = []
    for p in catalog:
        # Filter to known fields only — drop extras like stripe_product_id
        clean = {k: v for k, v in p.items() if k in _PLAN_FIELDS}
        try:
            plans.append(Plan(**clean))
        except TypeError as e:
            logger.error("Invalid plan in catalog (skipping): %s — %s", p.get("key"), e)
    return plans


def get_plan_by_key(key: str) -> Plan | None:
    for p in load_plans():
        if p.key == key:
            return p
    return None


def get_plan_by_price_id(price_id: str) -> PriceLookup | None:
    """Reverse lookup: given a Stripe price_id, find which plan + period it represents.

    Used by the webhook handler to figure out which plan a customer subscribed to.
    """
    for p in load_plans():
        if p.price_id_monthly == price_id:
            return PriceLookup(plan=p, period="monthly")
        if p.price_id_yearly == price_id:
            return PriceLookup(plan=p, period="yearly")
    return None


def reset_cache() -> None:
    """Force reload of plans (useful after seed script runs)."""
    load_plans.cache_clear()
