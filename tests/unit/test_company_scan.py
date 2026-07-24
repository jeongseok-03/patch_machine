"""Tests for the company filesystem scanner used by auto-discovery onboarding."""

from __future__ import annotations

import os
from pathlib import Path

from negotium.app.company_scan import (
    ScanConfig,
    normalize_scan_path,
    parse_scanned_files,
    scan_company_paths,
)


def _build_company_tree(root: Path) -> None:
    (root / "docs").mkdir()
    (root / "docs" / "회사소개.md").write_text(
        "우리 회사는 금형 가공 제조업입니다.", encoding="utf-8"
    )
    (root / "docs" / "업무규정.txt").write_text("결재 절차: 팀장 -> 본부장", encoding="utf-8")
    (root / "직원명단.csv").write_text("이름,부서\n김철수,생산\n", encoding="utf-8")
    (root / "logo.png").write_bytes(b"\x89PNG fake")
    (root / ".env").write_text("NG_SOLAR_API_KEY=up_realkey", encoding="utf-8")
    (root / "server.pem").write_text("-----BEGIN PRIVATE KEY-----", encoding="utf-8")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "pkg.md").write_text("dependency readme", encoding="utf-8")
    (root / "급여").mkdir()
    (root / "급여" / "연봉표.csv").write_text("이름,연봉\n", encoding="utf-8")


def test_scan_includes_whitelisted_documents_only(tmp_path: Path) -> None:
    _build_company_tree(tmp_path)
    report = scan_company_paths(ScanConfig(root_paths=[str(tmp_path)]))
    included = {Path(item.path).name for item in report.files if item.included}
    assert included == {"회사소개.md", "업무규정.txt", "직원명단.csv", "연봉표.csv"}
    reasons = report.skipped_counts
    assert reasons.get("extension_not_allowed", 0) >= 1  # logo.png
    assert reasons.get("sensitive_name", 0) >= 2  # .env, server.pem
    skipped_paths = {Path(item.path).name for item in report.files if not item.included}
    assert "pkg.md" not in included
    assert "pkg.md" not in skipped_paths  # node_modules pruned entirely


def test_scan_user_blacklist_excludes_directory(tmp_path: Path) -> None:
    _build_company_tree(tmp_path)
    report = scan_company_paths(
        ScanConfig(root_paths=[str(tmp_path)], excluded_paths=[str(tmp_path / "급여")])
    )
    included = {Path(item.path).name for item in report.files if item.included}
    assert "연봉표.csv" not in included
    assert "회사소개.md" in included


def test_scan_respects_size_and_count_caps(tmp_path: Path) -> None:
    _build_company_tree(tmp_path)
    (tmp_path / "huge.txt").write_text("x" * 5000, encoding="utf-8")
    report = scan_company_paths(
        ScanConfig(root_paths=[str(tmp_path)], max_file_bytes=1000, max_files=2)
    )
    assert report.included_count <= 2
    assert report.skipped_counts.get("too_large", 0) >= 1
    assert report.truncated


def test_scan_skips_symlinks(tmp_path: Path) -> None:
    _build_company_tree(tmp_path)
    outside = tmp_path.parent / "outside_secret.txt"
    outside.write_text("do not read", encoding="utf-8")
    link = tmp_path / "link.txt"
    try:
        os.symlink(outside, link)
    except OSError:
        return  # filesystem without symlink support
    report = scan_company_paths(ScanConfig(root_paths=[str(tmp_path)]))
    included = {Path(item.path).name for item in report.files if item.included}
    assert "link.txt" not in included


def test_scan_reports_missing_roots(tmp_path: Path) -> None:
    report = scan_company_paths(ScanConfig(root_paths=[str(tmp_path / "없는폴더")]))
    assert report.missing_roots
    assert report.included_count == 0


def test_parse_scanned_files_prioritizes_company_docs(tmp_path: Path) -> None:
    _build_company_tree(tmp_path)
    report = scan_company_paths(ScanConfig(root_paths=[str(tmp_path)]))
    parsed = parse_scanned_files(report, max_files=2)
    names = [item.filename for item in parsed]
    assert len(names) == 2
    assert "회사소개.md" in names  # priority keyword ranks first
    joined = " ".join(item.text for item in parsed)
    assert "금형 가공" in joined


def test_parse_scanned_files_respects_char_budget(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("가" * 500, encoding="utf-8")
    (tmp_path / "b.txt").write_text("나" * 500, encoding="utf-8")
    report = scan_company_paths(ScanConfig(root_paths=[str(tmp_path)]))
    parsed = parse_scanned_files(report, max_total_chars=600)
    total = sum(len(item.text) for item in parsed)
    assert total <= 600


def test_normalize_scan_path_translates_windows_style() -> None:
    assert normalize_scan_path("C:\\Users\\gimpo\\Desktop") in {
        "/mnt/c/Users/gimpo/Desktop",
        "C:/Users/gimpo/Desktop",
    }
    assert normalize_scan_path("  /srv/data  ") == "/srv/data"
    assert normalize_scan_path("") == ""
