from __future__ import annotations

import csv
from pathlib import Path

from openpyxl import Workbook

from negotium.app.initial_setup import parse_setup_file


def test_parse_setup_csv_extracts_rows_and_sensitive_hint(tmp_path: Path) -> None:
    path = tmp_path / "인사_명단.csv"
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["이름", "직함", "부서"])
        writer.writeheader()
        writer.writerow({"이름": "김대표", "직함": "대표", "부서": "경영"})

    parsed = parse_setup_file(path, archive_root=tmp_path)
    assert parsed.kind == "csv"
    assert parsed.rows[0]["이름"] == "김대표"
    assert parsed.sensitive_hint is True


def test_parse_setup_xlsx_extracts_rows(tmp_path: Path) -> None:
    path = tmp_path / "employees.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["name", "title", "department"])
    ws.append(["Alice", "Manager", "Ops"])
    wb.save(path)

    parsed = parse_setup_file(path, archive_root=tmp_path)
    assert parsed.kind == "xlsx"
    assert parsed.rows[0]["name"] == "Alice"
    assert "Alice" in parsed.text


def test_parse_setup_text_reads_content(tmp_path: Path) -> None:
    path = tmp_path / "policy.md"
    path.write_text("# 보안 정책\n고객 정보는 로컬에서만 처리", encoding="utf-8")
    parsed = parse_setup_file(path, archive_root=tmp_path)
    assert parsed.kind == "md"
    assert "보안 정책" in parsed.text
    assert parsed.sensitive_hint is True
