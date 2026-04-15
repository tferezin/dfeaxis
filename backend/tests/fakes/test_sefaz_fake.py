"""Testes standalone do FakeSefazClient — rodar sem pytest.

    ./backend/venv/bin/python backend/tests/fakes/test_sefaz_fake.py

Valida:
  1. Seed 10 docs → 1ª chamada devolve 10, ultNSU=maxNSU=10, cstat=138
  2. Seed 100 docs → 3 chamadas (50, 50, 0)
  3. Seed 0 → cstat=137
  4. force_error(656) → 1ª chamada erra, 2ª volta ao normal
  5. Cursor: seed 100, ult_nsu=50 → devolve NSUs 51..100 (primeiros 50)
"""

from __future__ import annotations

import os
import sys
import traceback

# Permite rodar o arquivo direto sem instalar como pacote.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.abspath(os.path.join(_THIS_DIR, "..", ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from tests.fakes.sefaz_fake import FakeSefazClient, BATCH_SIZE  # noqa: E402


CNPJ = "12345678000199"
TIPO = "nfe"


def _assert(cond: bool, msg: str = "") -> None:
    if not cond:
        raise AssertionError(msg)


def test_01_seed_10_single_batch() -> None:
    fake = FakeSefazClient()
    fake.seed_documents(CNPJ, TIPO, count=10)

    resp = fake.consultar_distribuicao(
        cnpj=CNPJ, tipo=TIPO, ult_nsu="000000000000000",
    )
    _assert(resp.cstat == "138", f"esperado cstat=138, got {resp.cstat}")
    _assert(len(resp.documents) == 10, f"esperado 10 docs, got {len(resp.documents)}")
    _assert(resp.ult_nsu == "000000000000010", f"ult_nsu={resp.ult_nsu}")
    _assert(resp.max_nsu == "000000000000010", f"max_nsu={resp.max_nsu}")
    # Chave deve ter 44 dígitos
    for d in resp.documents:
        _assert(len(d.chave) == 44 and d.chave.isdigit(),
                f"chave inválida: {d.chave}")
    # XML deve conter chave e CNPJ
    _assert("<nfeProc" in resp.documents[0].xml_content, "xml sem nfeProc")


def test_02_seed_100_batches_of_50() -> None:
    fake = FakeSefazClient()
    fake.seed_documents(CNPJ, TIPO, count=100)

    # 1ª chamada
    r1 = fake.consultar_distribuicao(cnpj=CNPJ, tipo=TIPO, ult_nsu="0")
    _assert(r1.cstat == "138", f"batch1 cstat={r1.cstat}")
    _assert(len(r1.documents) == BATCH_SIZE, f"batch1 len={len(r1.documents)}")
    _assert(r1.ult_nsu == "000000000000050", f"batch1 ult_nsu={r1.ult_nsu}")
    _assert(r1.max_nsu == "000000000000100", f"batch1 max_nsu={r1.max_nsu}")

    # 2ª chamada com cursor atualizado
    r2 = fake.consultar_distribuicao(cnpj=CNPJ, tipo=TIPO, ult_nsu=r1.ult_nsu)
    _assert(r2.cstat == "138", f"batch2 cstat={r2.cstat}")
    _assert(len(r2.documents) == BATCH_SIZE, f"batch2 len={len(r2.documents)}")
    _assert(r2.ult_nsu == "000000000000100", f"batch2 ult_nsu={r2.ult_nsu}")
    _assert(r2.max_nsu == "000000000000100")
    # NSUs devem ser 51..100
    first_nsu = int(r2.documents[0].nsu)
    last_nsu = int(r2.documents[-1].nsu)
    _assert(first_nsu == 51 and last_nsu == 100,
            f"batch2 NSUs {first_nsu}..{last_nsu}")

    # 3ª chamada — fila esgotada
    r3 = fake.consultar_distribuicao(cnpj=CNPJ, tipo=TIPO, ult_nsu=r2.ult_nsu)
    _assert(r3.cstat == "137", f"batch3 cstat={r3.cstat}")
    _assert(len(r3.documents) == 0, f"batch3 len={len(r3.documents)}")
    _assert(r3.ult_nsu == r3.max_nsu == "000000000000100",
            f"batch3 nsus {r3.ult_nsu}/{r3.max_nsu}")


def test_03_empty_queue_returns_137() -> None:
    fake = FakeSefazClient()
    resp = fake.consultar_distribuicao(cnpj=CNPJ, tipo=TIPO, ult_nsu="0")
    _assert(resp.cstat == "137", f"esperado 137, got {resp.cstat}")
    _assert(len(resp.documents) == 0)
    _assert(resp.ult_nsu == "000000000000000")
    _assert(resp.max_nsu == "000000000000000")


def test_04_force_error_then_recovers() -> None:
    fake = FakeSefazClient()
    fake.seed_documents(CNPJ, TIPO, count=5)
    fake.force_error(CNPJ, TIPO, cstat="656", xmotivo="Consumo indevido")

    r1 = fake.consultar_distribuicao(cnpj=CNPJ, tipo=TIPO, ult_nsu="0")
    _assert(r1.cstat == "656", f"esperado 656, got {r1.cstat}")
    _assert(r1.xmotivo == "Consumo indevido")
    _assert(len(r1.documents) == 0, "erro não deve devolver docs")

    # Próxima chamada volta ao normal
    r2 = fake.consultar_distribuicao(cnpj=CNPJ, tipo=TIPO, ult_nsu="0")
    _assert(r2.cstat == "138", f"recovery cstat={r2.cstat}")
    _assert(len(r2.documents) == 5, f"recovery len={len(r2.documents)}")


def test_05_cursor_respected() -> None:
    fake = FakeSefazClient()
    fake.seed_documents(CNPJ, TIPO, count=100)

    resp = fake.consultar_distribuicao(
        cnpj=CNPJ, tipo=TIPO, ult_nsu="000000000000050",
    )
    _assert(resp.cstat == "138", f"cstat={resp.cstat}")
    _assert(len(resp.documents) == BATCH_SIZE,
            f"esperado {BATCH_SIZE} docs, got {len(resp.documents)}")
    nsus = [int(d.nsu) for d in resp.documents]
    _assert(nsus == list(range(51, 101)), f"NSUs errados: {nsus[:5]}...{nsus[-5:]}")
    _assert(resp.ult_nsu == "000000000000100")
    _assert(resp.max_nsu == "000000000000100")

    # Call log deve ter registrado a chamada
    calls = fake.get_calls(cnpj=CNPJ, tipo=TIPO)
    _assert(len(calls) == 1, f"esperado 1 call, got {len(calls)}")
    _assert(calls[0]["ult_nsu"] == 50, f"ult_nsu no log = {calls[0]['ult_nsu']}")


TESTS = [
    ("01_seed_10_single_batch", test_01_seed_10_single_batch),
    ("02_seed_100_batches_of_50", test_02_seed_100_batches_of_50),
    ("03_empty_queue_returns_137", test_03_empty_queue_returns_137),
    ("04_force_error_then_recovers", test_04_force_error_then_recovers),
    ("05_cursor_respected", test_05_cursor_respected),
]


def main() -> int:
    passed = 0
    failed = 0
    for name, fn in TESTS:
        try:
            fn()
            print(f"  PASS  {name}")
            passed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL  {name}: {exc}")
            traceback.print_exc()
            failed += 1
    total = passed + failed
    print(f"\n{passed}/{total} tests passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
