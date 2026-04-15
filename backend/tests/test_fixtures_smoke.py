"""Smoke test da Fase 2.4 — valida cada fixture do conftest.py.

Objetivo: garantir que as fixtures carregam sem erro e fazem o que prometem.
Não testam cenários E2E completos (isso é Fase 3). Rode com:

    ./venv/bin/python -m pytest backend/tests/test_fixtures_smoke.py -v
"""

from __future__ import annotations


def test_fake_sefaz_seeds_and_patches_global(fake_sefaz) -> None:
    """O fake deve poder receber seed e deve ter sido patchado nos 3 call sites."""
    chaves = fake_sefaz.seed_documents(cnpj="99000000000001", tipo="nfe", count=10)
    assert len(chaves) == 10

    # consultar_distribuicao deve devolver os 10 (batch <= 50)
    resp = fake_sefaz.consultar_distribuicao(
        cnpj="99000000000001",
        tipo="nfe",
        ult_nsu="0",
    )
    assert resp.cstat == "138"
    assert len(resp.documents) == 10

    # Patch global confirmado
    from services import sefaz_client as sefaz_module

    assert sefaz_module.sefaz_client is fake_sefaz

    # Patch no scheduler/polling_job
    from scheduler import polling_job as polling_job_module

    assert polling_job_module.sefaz_client is fake_sefaz

    # Patch no router de documentos
    from routers import documents as documents_router_module

    assert documents_router_module.sefaz_client is fake_sefaz


def test_fake_stripe_preloads_subscription(fake_stripe) -> None:
    """preload_subscription popula e retrieve devolve o objeto correto."""
    fake_stripe.preload_subscription(
        "sub_qa_smoke",
        status="active",
        price_id="price_qa_starter",
    )

    # get_stripe patchado na fonte canônica
    from services.billing.stripe_client import get_stripe

    s = get_stripe()
    assert s is fake_stripe

    sub = s.Subscription.retrieve("sub_qa_smoke")
    assert sub["status"] == "active"
    assert sub.status == "active"  # dupla interface (dict + attr)
    assert sub["id"] == "sub_qa_smoke"


def test_fake_stripe_patched_in_call_sites(fake_stripe) -> None:
    """Cada módulo que faz `from .stripe_client import get_stripe` deve estar
    apontando pro fake (patch de símbolo local)."""
    for module_path in (
        "services.billing.webhooks",
        "services.billing.checkout",
        "services.billing.customers",
        "services.billing.portal",
        "scheduler.monthly_overage_job",
    ):
        mod = __import__(module_path, fromlist=["get_stripe"])
        assert mod.get_stripe() is fake_stripe, (
            f"{module_path}.get_stripe não foi patchado pro fake"
        )


def test_test_tenant_creates_and_cleans(test_tenant) -> None:
    """Tenant é criado com prefixo qa-*, cert fake, api_key fake."""
    assert test_tenant["tenant_id"]
    assert test_tenant["email"].startswith("qa-")
    assert "@test.dfeaxis.com.br" in test_tenant["email"]
    assert test_tenant["api_key_raw"].startswith("dfa_qa_")
    assert test_tenant["cnpj"].startswith("99")
    assert test_tenant["certificate_id"]

    # api_key_hash bate com sha256(api_key_raw)
    import hashlib

    expected = hashlib.sha256(test_tenant["api_key_raw"].encode()).hexdigest()
    assert test_tenant["api_key_hash"] == expected


def test_sap_client_health(sap_client, test_tenant) -> None:
    """TestSAPClient usa a api_key correta e consegue bater em /sap-drc/health."""
    assert sap_client is not None
    resp = sap_client.sap_health()
    # /sap-drc/health deve retornar 200 (endpoint de health é público/leve)
    assert resp["status_code"] == 200
