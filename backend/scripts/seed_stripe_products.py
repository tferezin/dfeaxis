"""Seed Stripe products and prices from the default plan catalog.

Usage:
    cd backend && source venv/bin/activate
    python scripts/seed_stripe_products.py

What it does:
    1. Reads DEFAULT_PLAN_CATALOG from services.billing.plans
    2. For each plan, ensures a Stripe Product exists (lookup_key = plan.key)
    3. For each plan, creates a monthly + yearly Price in BRL
    4. Writes data/stripe_plans.json with the resulting price IDs

Idempotent: re-running won't duplicate Products. Prices are immutable in
Stripe, so re-running creates NEW prices and points the JSON to them.
The old ones get deactivated automatically by lookup.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Allow running as a script: add backend/ to sys.path
THIS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = THIS_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

# Load .env from project root
from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND_DIR.parent / ".env")

from services.billing.plans import DEFAULT_PLAN_CATALOG  # noqa: E402
from services.billing.stripe_client import get_stripe  # noqa: E402

OUTPUT_FILE = BACKEND_DIR / "data" / "stripe_plans.json"


def ensure_product(stripe, plan: dict) -> str:
    """Find or create a Stripe Product for this plan key."""
    # Search by metadata key
    products = stripe.Product.search(query=f"metadata['plan_key']:'{plan['key']}'")
    if products.data:
        prod = products.data[0]
        # Update name/description in case they changed
        stripe.Product.modify(
            prod.id,
            name=plan["name"],
            description=plan["description"],
        )
        print(f"  ✓ Product exists: {plan['name']} ({prod.id})")
        return prod.id

    prod = stripe.Product.create(
        name=plan["name"],
        description=plan["description"],
        metadata={
            "plan_key": plan["key"],
            "docs_included": str(plan["docs_included"]),
            "max_cnpjs": str(plan["max_cnpjs"]),
        },
    )
    print(f"  ✓ Product created: {plan['name']} ({prod.id})")
    return prod.id


def create_price(
    stripe,
    product_id: str,
    plan_key: str,
    interval: str,
    amount_cents: int,
) -> str:
    """Create a recurring Price in BRL for this product."""
    lookup_key = f"{plan_key}_{interval}"

    # Try to find existing price by lookup_key
    existing = stripe.Price.list(lookup_keys=[lookup_key], active=True, limit=1)
    if existing.data:
        existing_price = existing.data[0]
        if existing_price.unit_amount == amount_cents:
            print(f"    ✓ Price exists ({interval}): {existing_price.id}")
            return existing_price.id
        # Amount changed: deactivate old, create new
        stripe.Price.modify(existing_price.id, active=False)
        # Stripe requires unique lookup_keys among active prices, so old must be deactivated first
        # Then create new one with same lookup_key
        # Need to also remove the lookup_key from the deactivated price
        stripe.Price.modify(existing_price.id, lookup_key=None)

    interval_unit = "month" if interval == "monthly" else "year"
    price = stripe.Price.create(
        product=product_id,
        currency="brl",
        unit_amount=amount_cents,
        recurring={"interval": interval_unit},
        lookup_key=lookup_key,
        metadata={
            "plan_key": plan_key,
            "period": interval,
        },
    )
    print(f"    ✓ Price created ({interval}): {price.id} (R$ {amount_cents/100:.2f})")
    return price.id


def main() -> int:
    try:
        stripe = get_stripe()
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print(f"Seeding Stripe products for {len(DEFAULT_PLAN_CATALOG)} plans...")
    print()

    output_catalog = []
    for plan in DEFAULT_PLAN_CATALOG:
        print(f"→ {plan['name']}")
        product_id = ensure_product(stripe, plan)

        price_id_monthly = create_price(
            stripe,
            product_id,
            plan["key"],
            "monthly",
            plan["monthly_amount_cents"],
        )
        price_id_yearly = create_price(
            stripe,
            product_id,
            plan["key"],
            "yearly",
            plan["yearly_amount_cents"],
        )

        output_catalog.append(
            {
                **plan,
                "stripe_product_id": product_id,
                "price_id_monthly": price_id_monthly,
                "price_id_yearly": price_id_yearly,
            }
        )
        print()

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE.open("w") as f:
        json.dump(output_catalog, f, indent=2, ensure_ascii=False)

    print(f"✓ Wrote {OUTPUT_FILE}")
    print()
    print("Plans configured:")
    for p in output_catalog:
        print(
            f"  {p['key']:12} mensal={p['price_id_monthly']:30} anual={p['price_id_yearly']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
