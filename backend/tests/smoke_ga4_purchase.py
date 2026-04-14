"""Smoke test: dispara um evento purchase REAL no GA4 via Measurement Protocol.

Não é um teste unitário — é um ping de validação ponta a ponta pra confirmar
que o GA4_API_SECRET configurado no ambiente está correto e que o Google
Analytics aceita o payload.

Como rodar:
    cd backend && source venv/bin/activate
    python tests/smoke_ga4_purchase.py

O que esperar:
    - Resposta HTTP 204 do endpoint MP
    - Mensagem "✓ EVENTO ACEITO pelo GA4"
    - Em ~30s o evento aparece em GA4 → Tempo Real com transaction_id="smoke-test-..."
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime

# Ensure backend module path is loadable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

from config import settings  # noqa: E402
from services.tracking.ga4_mp import send_purchase_event  # noqa: E402


def main() -> int:
    print("=" * 70)
    print("GA4 Measurement Protocol — smoke test")
    print("=" * 70)
    print()

    # Config check
    measurement_id = settings.ga4_measurement_id
    api_secret = settings.ga4_api_secret

    print(f"GA4_MEASUREMENT_ID: {measurement_id}")
    if not api_secret:
        print("GA4_API_SECRET:     [VAZIO]")
        print()
        print("✗ GA4_API_SECRET não está configurado no ambiente.")
        print("  Adicione no .env local ou exporte antes de rodar:")
        print("    export GA4_API_SECRET=<valor>")
        return 1

    masked = api_secret[:6] + "..." + api_secret[-4:] if len(api_secret) > 10 else "***"
    print(f"GA4_API_SECRET:     {masked}")
    print()

    # Payload de teste — usa transaction_id único pra não colidir com dedup
    transaction_id = f"smoke-test-{uuid.uuid4().hex[:8]}"
    fake_client_id = "1234567890.9876543210"

    print(f"Enviando purchase event:")
    print(f"  transaction_id: {transaction_id}")
    print(f"  client_id:      {fake_client_id}")
    print(f"  value:          R$ 290,00")
    print(f"  item:           starter / DFeAxis Starter")
    print(f"  timestamp:      {datetime.now().isoformat()}")
    print()

    result = send_purchase_event(
        client_id=fake_client_id,
        transaction_id=transaction_id,
        value_brl=290.0,
        currency="BRL",
        item_id="starter",
        item_name="DFeAxis Starter",
    )

    print(f"Resultado: {result}")
    print()

    if result["status"] == "sent":
        http = result.get("http_status")
        print(f"✓ EVENTO ACEITO pelo GA4 (HTTP {http})")
        print()
        print("Próximo passo: abra GA4 → Relatórios → Tempo real")
        print("                  → 'Contagem de eventos por nome do evento'")
        print(f"                  → deve aparecer 'purchase' em ~30 segundos")
        print()
        print(f"  Filtro opcional pra isolar este teste: transaction_id={transaction_id}")
        return 0

    print("✗ FALHA ao enviar evento.")
    print(f"  status: {result['status']}")
    print(f"  reason: {result.get('reason')}")
    if "body" in result:
        print(f"  body:   {result['body']}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
