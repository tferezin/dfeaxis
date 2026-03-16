"""Endpoints de créditos e integração MercadoPago."""

import hashlib
import hmac
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request

from db.supabase import get_supabase_client
from middleware.security import verify_jwt_token
from models.schemas import CheckoutRequest, CheckoutResponse, CreditBalanceResponse

router = APIRouter()
logger = logging.getLogger(__name__)

# Preço por crédito (centavos BRL)
CREDIT_PRICE_CENTS = 10  # R$ 0,10 por documento


@router.get("/credits/balance", response_model=CreditBalanceResponse)
async def get_balance(auth: dict = Depends(verify_jwt_token)):
    """Retorna saldo de créditos do tenant."""
    sb = get_supabase_client()
    result = sb.table("tenants").select("id, credits").eq(
        "id", auth["tenant_id"]
    ).single().execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return CreditBalanceResponse(
        tenant_id=result.data["id"],
        credits=result.data["credits"],
    )


@router.post("/credits/checkout", response_model=CheckoutResponse)
async def create_checkout(
    body: CheckoutRequest,
    auth: dict = Depends(verify_jwt_token),
):
    """Gera preferência MercadoPago para compra de créditos."""
    import mercadopago

    sdk = mercadopago.SDK(os.environ["MP_ACCESS_TOKEN"])

    total_cents = body.amount * CREDIT_PRICE_CENTS
    total_brl = total_cents / 100

    preference_data = {
        "items": [
            {
                "title": f"DFeAxis - {body.amount} créditos",
                "quantity": 1,
                "unit_price": total_brl,
                "currency_id": "BRL",
            }
        ],
        "external_reference": f"{auth['tenant_id']}_{body.amount}",
        "back_urls": {
            "success": f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/credits/success",
            "failure": f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/credits/failure",
        },
        "auto_return": "approved",
        "notification_url": f"{os.getenv('API_BASE_URL', 'http://localhost:8000')}/api/v1/credits/webhook",
    }

    result = sdk.preference().create(preference_data)

    if result["status"] != 201:
        raise HTTPException(status_code=500, detail="Erro ao criar checkout")

    preference = result["response"]
    return CheckoutResponse(
        checkout_url=preference["init_point"],
        preference_id=preference["id"],
    )


@router.post("/credits/webhook")
async def mercadopago_webhook(request: Request):
    """Webhook do MercadoPago — processa pagamento aprovado e credita."""
    # --- Signature validation (fail-safe: MANDATORY) ---
    webhook_secret = os.getenv("MP_WEBHOOK_SECRET", "")
    if not webhook_secret:
        logger.critical(
            "MP_WEBHOOK_SECRET is not configured. "
            "Rejecting ALL webhooks until it is set."
        )
        raise HTTPException(status_code=503, detail="Webhook unavailable")

    raw_body = await request.body()

    signature = request.headers.get("x-signature", "")
    if not signature:
        raise HTTPException(status_code=401, detail="Unauthorized")

    expected = hmac.new(
        webhook_secret.encode(),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="Unauthorized")

    # --- Parse body ---
    body = await request.json()

    if body.get("type") != "payment":
        return {"status": "ignored"}

    payment_id = body.get("data", {}).get("id")
    if not payment_id:
        return {"status": "ignored"}

    # --- Idempotency check ---
    sb = get_supabase_client()
    existing = (
        sb.table("credit_transactions")
        .select("id")
        .eq("reference_id", str(payment_id))
        .execute()
    )
    if existing.data:
        logger.info("Payment %s already processed, skipping.", payment_id)
        return {"status": "already_processed"}

    # --- Fetch payment details from MercadoPago ---
    import mercadopago

    sdk = mercadopago.SDK(os.environ["MP_ACCESS_TOKEN"])
    payment = sdk.payment().get(payment_id)

    if payment["status"] != 200:
        logger.error("Failed to fetch payment %s from MercadoPago.", payment_id)
        return {"status": "error"}

    payment_data = payment["response"]
    if payment_data.get("status") != "approved":
        return {"status": "pending"}

    # Extrai tenant_id e quantidade do external_reference
    external_ref = payment_data.get("external_reference", "")
    parts = external_ref.split("_")
    if len(parts) != 2:
        logger.warning("Invalid external_reference: redacted")
        return {"status": "invalid_reference"}

    tenant_id, amount_str = parts
    try:
        amount = int(amount_str)
    except ValueError:
        logger.warning("Non-integer amount in external_reference")
        return {"status": "invalid_reference"}

    # Credita atomicamente via RPC (atomic debit_credits from agent 3)
    try:
        result = sb.rpc("debit_credits", {
            "p_tenant_id": tenant_id,
            "p_amount": amount,
            "p_description": f"Compra de {amount} créditos via MercadoPago",
            "p_reference_id": str(payment_id),
        }).execute()
    except Exception:
        logger.warning("Tenant not found or RPC failed for payment %s", payment_id)
        return {"status": "tenant_not_found"}

    return {"status": "credited", "amount": amount}
