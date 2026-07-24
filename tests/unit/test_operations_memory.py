"""Operations memory persistence tests."""

from __future__ import annotations

from pathlib import Path

from negotium.archive.operations_memory import OperationsMemory, OperationsMemoryStore


def test_operations_memory_starts_empty(archive_tmp: Path) -> None:
    store = OperationsMemoryStore(archive_tmp)

    memory = store.read()

    assert memory.company_name == ""
    assert memory.office_project == ""
    assert memory.active_plan == ""
    assert not store.path.exists()


def test_operations_memory_round_trips(archive_tmp: Path) -> None:
    store = OperationsMemoryStore(archive_tmp)

    store.write(
        OperationsMemory(
            company_name="Acme Retail",
            office_project="환불 자동화",
            active_plan="중복 환불 방지 계획",
        )
    )

    memory = store.read()
    assert memory.company_name == "Acme Retail"
    assert memory.office_project == "환불 자동화"
    assert memory.active_plan == "중복 환불 방지 계획"
    assert "Acme Retail" in memory.to_markdown()
