"""Singleton Stripe client. Reads STRIPE_SECRET_KEY from settings."""

from __future__ import annotations

import logging
from functools import lru_cache

import stripe

from config import settings

logger = logging.getLogger("dfeaxis.billing")


@lru_cache(maxsize=1)
def get_stripe() -> "stripe":  # type: ignore[valid-type]
    """Returns the configured stripe module (singleton).

    Raises RuntimeError if STRIPE_SECRET_KEY is not configured.
    """
    if not settings.stripe_secret_key:
        raise RuntimeError(
            "STRIPE_SECRET_KEY not configured. Set it in your .env to enable billing."
        )
    stripe.api_key = settings.stripe_secret_key
    # Enable automatic retries on idempotent requests
    stripe.max_network_retries = 2
    logger.info("Stripe client initialized (mode=%s)", _mode())
    return stripe


def _mode() -> str:
    key = settings.stripe_secret_key or ""
    if key.startswith("sk_live_"):
        return "live"
    if key.startswith("sk_test_"):
        return "test"
    return "unknown"
