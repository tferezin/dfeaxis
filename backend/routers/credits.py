"""Endpoints de créditos e integração MercadoPago."""

import os

from fastapi import APIRouter, Depends, HTTPException, Request

from db.supabase import get_supabase_client
from middleware.security import verify_jwt_token
from models.schemas import CheckoutRequest, CheckoutResponse, CreditBalanceResponse

router = APIRouter()

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
    import hmac
    import hashlib

    body = await request.json()

    # Valida assinatura do webhook (MercadoPago x-signature format)
    webhook_secret = os.getenv("MP_WEBHOOK_SECRET", "")
    if webhook_secret:
        x_signature = request.headers.get("x-signature", "")
        x_request_id = request.headers.get("x-request-id", "")
        if not x_signature:
            raise HTTPException(status_code=401, detail="Missing signature")

        # Parse x-signature: "ts=...,v1=..."
        parts = dict(p.split("=", 1) for p in x_signature.split(",") if "=" in p)
        ts = parts.get("ts", "")
        v1 = parts.get("v1", "")

        data_id = body.get("data", {}).get("id", "")
        manifest = f"id:{data_id};request-id:{x_request_id};ts:{ts};"
        expected = hmac.new(
            webhook_secret.encode(), manifest.encode(), hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(v1, expected):
            raise HTTPException(status_code=401, detail="Invalid signature")

    if body.get("type") != "payment":
        return {"status": "ignored"}

    payment_id = body.get("data", {}).get("id")
    if not payment_id:
        return {"status": "ignored"}

    # Busca detalhes do pagamento
    import mercadopago
    sdk = mercadopago.SDK(os.environ["MP_ACCESS_TOKEN"])
    payment = sdk.payment().get(payment_id)

    if payment["status"] != 200:
        return {"status": "error"}

    payment_data = payment["response"]
    if payment_data.get("status") != "approved":
        return {"status": "pending"}

    # Extrai tenant_id e quantidade do external_reference
    external_ref = payment_data.get("external_reference", "")
    parts = external_ref.split("_")
    if len(parts) != 2:
        return {"status": "invalid_reference"}

    tenant_id, amount_str = parts
    amount = int(amount_str)

    sb = get_supabase_client()

    # Credita no tenant
    tenant = sb.table("tenants").select("credits").eq(
        "id", tenant_id
    ).single().execute()

    if not tenant.data:
        return {"status": "tenant_not_found"}

    new_credits = tenant.data["credits"] + amount
    sb.table("tenants").update(
        {"credits": new_credits}
    ).eq("id", tenant_id).execute()

    # Registra transação
    sb.table("credit_transactions").insert({
        "tenant_id": tenant_id,
        "amount": amount,
        "description": f"Compra de {amount} créditos via MercadoPago",
        "reference_id": str(payment_id),
    }).execute()

    return {"status": "credited", "amount": amount}
