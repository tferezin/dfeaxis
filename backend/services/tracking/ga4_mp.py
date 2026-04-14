"""GA4 Measurement Protocol sender.

Envia eventos server-side para o Google Analytics 4 via endpoint oficial
do Measurement Protocol (https://www.google-analytics.com/mp/collect).

Isso complementa o rastreamento client-side (gtag.js) — é usado quando um
evento acontece fora do browser do usuário, tipicamente:

- Webhook do Stripe chegando no backend (checkout.session.completed)
- Job server-side concluindo algo (ex: ativação de assinatura)

Pré-requisitos:
  1. GA4_MEASUREMENT_ID definido (ex: "G-XZTRG63C53")
  2. GA4_API_SECRET criado em GA4 Admin → Data Streams → Measurement Protocol
     API secrets → Create. Copiado para a variável de ambiente GA4_API_SECRET.
  3. Um `client_id` que corresponda ao cookie _ga do usuário (capturado no
     signup). Sem ele, GA4 trata o evento como de um usuário anônimo novo
     e perde a atribuição do clique original do anúncio.

A função NUNCA levanta exceção — se o envio falhar (secret vazio, network
error, GA4 retorna 4xx/5xx), loga um warning e retorna um dict de status.
Rastreamento nunca pode quebrar fluxo de negócio.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from config import settings

logger = logging.getLogger("dfeaxis.tracking.ga4_mp")

# Endpoint oficial do Measurement Protocol. É o mesmo domínio que o gtag.js
# usa client-side.
MP_ENDPOINT = "https://www.google-analytics.com/mp/collect"

# Timeout curto: rastreamento não pode bloquear o webhook do Stripe.
# Se o Google estiver lento, preferimos perder o evento a deixar o Stripe
# re-entregar o webhook.
MP_TIMEOUT_SECONDS = 3.0


def send_purchase_event(
    *,
    client_id: str | None,
    transaction_id: str,
    value_brl: float,
    currency: str = "BRL",
    item_id: str | None = None,
    item_name: str | None = None,
) -> dict[str, Any]:
    """Dispara um evento GA4 `purchase` via Measurement Protocol.

    Parameters
    ----------
    client_id:
        Valor capturado do cookie `_ga` do usuário no momento do signup
        (formato "XXXXXXXX.YYYYYYYY"). Pode ser None se não foi capturado
        — nesse caso a função loga warning e envia um fallback anônimo
        que ainda chega no GA4 mas perde atribuição do clique original.
    transaction_id:
        Identificador único da transação (tipicamente o stripe_subscription_id
        ou o checkout_session.id). GA4 usa para deduplicar eventos.
    value_brl:
        Valor da compra em reais (não em centavos). Ex: 290.00 para o Starter.
    currency:
        ISO 4217. Default BRL.
    item_id, item_name:
        Metadata opcional do item vendido (ex: "starter", "DFeAxis Starter").

    Returns
    -------
    dict com status da operação:
        - {"status": "sent", "http_status": 204} em caso de sucesso
        - {"status": "skipped", "reason": "..."} se config estiver incompleta
        - {"status": "error", "reason": "..."} se a chamada HTTP falhou

    Nunca levanta exceção — caller (webhook do Stripe) depende disso para
    não interromper o processamento do evento quando o tracking falha.
    """
    try:
        return _send_purchase_event_impl(
            client_id=client_id,
            transaction_id=transaction_id,
            value_brl=value_brl,
            currency=currency,
            item_id=item_id,
            item_name=item_name,
        )
    except Exception as exc:  # noqa: BLE001 — promise: never raises
        logger.warning(
            "ga4_mp: unexpected error sending purchase transaction_id=%s: %s: %s",
            transaction_id,
            type(exc).__name__,
            exc,
        )
        return {"status": "error", "reason": f"unexpected: {type(exc).__name__}"}


def _send_purchase_event_impl(
    *,
    client_id: str | None,
    transaction_id: str,
    value_brl: float,
    currency: str,
    item_id: str | None,
    item_name: str | None,
) -> dict[str, Any]:
    """Implementação real do envio. Qualquer exceção é capturada pelo wrapper."""
    measurement_id = settings.ga4_measurement_id
    api_secret = settings.ga4_api_secret

    if not api_secret:
        logger.warning(
            "ga4_mp: GA4_API_SECRET não configurado — purchase event não será enviado "
            "(transaction_id=%s value=%s)",
            transaction_id,
            value_brl,
        )
        return {"status": "skipped", "reason": "api_secret_missing"}

    if not measurement_id:
        logger.warning("ga4_mp: GA4_MEASUREMENT_ID vazio — evento não enviado")
        return {"status": "skipped", "reason": "measurement_id_missing"}

    # Fallback defensivo: se não temos client_id, sintetizamos um derivado do
    # transaction_id. O evento chega no GA4 mas sem atribuição ao clique
    # original — útil apenas pro volume agregado, não pro funil do Google Ads.
    effective_client_id = client_id or f"server.{transaction_id}"
    if not client_id:
        logger.warning(
            "ga4_mp: client_id ausente para transaction_id=%s — usando fallback %s "
            "(atribuição do Google Ads pode ser perdida)",
            transaction_id,
            effective_client_id,
        )

    # Payload do Measurement Protocol para evento de ecommerce purchase.
    # Referência: https://developers.google.com/analytics/devguides/collection/protocol/ga4/reference/events#purchase
    event_params: dict[str, Any] = {
        "currency": currency,
        "value": value_brl,
        "transaction_id": transaction_id,
    }
    if item_id or item_name:
        event_params["items"] = [
            {
                "item_id": item_id or "",
                "item_name": item_name or item_id or "",
                "price": value_brl,
                "quantity": 1,
            }
        ]

    payload = {
        "client_id": effective_client_id,
        # `non_personalized_ads=false` deixa o GA4 usar o evento para
        # remarketing e otimização de lances no Google Ads.
        "non_personalized_ads": False,
        "events": [
            {
                "name": "purchase",
                "params": event_params,
            }
        ],
    }

    url = f"{MP_ENDPOINT}?measurement_id={measurement_id}&api_secret={api_secret}"

    try:
        response = requests.post(
            url,
            json=payload,
            timeout=MP_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        logger.warning(
            "ga4_mp: network error enviando purchase transaction_id=%s: %s",
            transaction_id,
            exc,
        )
        return {"status": "error", "reason": f"network: {type(exc).__name__}"}

    # GA4 Measurement Protocol retorna 204 No Content em sucesso.
    # 2xx em geral = aceito. 4xx/5xx = erro (mas não levantamos).
    if 200 <= response.status_code < 300:
        logger.info(
            "ga4_mp: purchase enviado transaction_id=%s value=%s client_id=%s http=%s",
            transaction_id,
            value_brl,
            effective_client_id,
            response.status_code,
        )
        return {"status": "sent", "http_status": response.status_code}

    logger.warning(
        "ga4_mp: GA4 rejeitou purchase transaction_id=%s http=%s body=%s",
        transaction_id,
        response.status_code,
        response.text[:500],
    )
    return {
        "status": "error",
        "reason": f"http_{response.status_code}",
        "body": response.text[:500],
    }
