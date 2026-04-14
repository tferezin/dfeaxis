"""Server-side marketing/analytics tracking (GA4 Measurement Protocol)."""

from .ga4_mp import send_purchase_event

__all__ = ["send_purchase_event"]
