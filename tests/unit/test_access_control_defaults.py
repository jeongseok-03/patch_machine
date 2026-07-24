from __future__ import annotations

import json
from pathlib import Path

from negotium.archive.access_control import (
    ALL_PERMISSIONS,
    AccessControlStore,
    DepartmentPermissionRecord,
    PositionRecord,
    UserRecord,
)


def test_admin_permissions_include_local_mcp_and_hr_controls() -> None:
    assert "admin:local_llm" in ALL_PERMISSIONS
    assert "admin:hr_evaluation" in ALL_PERMISSIONS
    assert "admin:mcp" in ALL_PERMISSIONS


def test_existing_owner_role_user_suppresses_synthetic_local_owner(tmp_path: Path) -> None:
    path = tmp_path / "access_control.json"
    path.write_text(
        json.dumps(
            {
                "roles": [
                    {"id": "owner", "name": "대표/관리자", "level": 100, "permissions": ["*"]},
                    {"id": "viewer", "name": "조회자", "level": 10, "permissions": ["work:read"]},
                ],
                "users": [
                    {
                        "id": "ceo",
                        "display_name": "대표 계정",
                        "title": "대표",
                        "role_id": "owner",
                        "active": True,
                    },
                ],
            },
        ),
        encoding="utf-8",
    )

    payload = AccessControlStore(tmp_path).read()
    user_ids = [str(user["id"]) for user in payload["users"]]
    display_names = [str(user["display_name"]) for user in payload["users"]]

    assert "ceo" in user_ids
    assert "owner" not in user_ids
    assert "Local Owner" not in display_names


def test_fresh_store_has_no_default_owner_account(tmp_path: Path) -> None:
    # No phantom owner account is fabricated; only the initial setup designer
    # should exist as administrator.
    payload = AccessControlStore(tmp_path).read()
    assert payload["users"] == []


def test_legacy_position_level_maps_to_permissions(tmp_path: Path) -> None:
    path = tmp_path / "access_control.json"
    path.write_text(
        json.dumps(
            {
                "roles": [
                    {"id": "owner", "name": "대표/관리자", "level": 100, "permissions": ["*"]}
                ],
                "users": [],
                "positions": [
                    {"id": "team_lead", "name": "팀장", "level": 70, "description": "legacy"}
                ],
            },
        ),
        encoding="utf-8",
    )

    payload = AccessControlStore(tmp_path).read()
    position = next(item for item in payload["positions"] if item["id"] == "team_lead")
    assert position["permissions"] == [
        "memory:write",
        "llm:chat",
        "documents:write",
        "documents:read",
        "uploads:write",
        "work:read",
        "patch_records:read",
        "patch_records:write",
    ]
    assert position["level"] == 70


def test_persisted_local_owner_is_normalized(tmp_path: Path) -> None:
    path = tmp_path / "access_control.json"
    path.write_text(
        json.dumps(
            {
                "roles": [
                    {"id": "owner", "name": "대표/관리자", "level": 100, "permissions": ["*"]}
                ],
                "users": [
                    {
                        "id": "owner",
                        "display_name": "Local Owner",
                        "title": "대표",
                        "role_id": "owner",
                        "active": True,
                    },
                ],
            },
        ),
        encoding="utf-8",
    )

    payload = AccessControlStore(tmp_path).read()
    owner = next(user for user in payload["users"] if user["id"] == "owner")
    assert owner["display_name"] == "시스템 관리자"
    assert owner["title"] == "시스템 관리자"


def test_position_default_and_department_permission_policy(tmp_path: Path) -> None:
    store = AccessControlStore(tmp_path)
    store.upsert_position(
        PositionRecord(
            id="staff_position",
            name="사원",
            permissions=["uploads:write"],
            display_order=10,
        )
    )
    store.upsert_user(
        UserRecord(
            id="alice",
            display_name="Alice",
            title="사원",
            role_id="viewer",
            department="sales",
            position_id="staff_position",
        )
    )

    assert store.has_permission("alice", "uploads:write") is True
    store.upsert_department_permission(
        DepartmentPermissionRecord(
            department_id="sales",
            position_id="staff_position",
            permissions=["work:read"],
        )
    )
    assert store.has_permission("alice", "work:read") is True
    assert store.has_permission("alice", "uploads:write") is False


def test_legacy_position_id_hydrates_permissions_and_order(tmp_path: Path) -> None:
    path = tmp_path / "access_control.json"
    path.write_text(
        json.dumps(
            {
                "roles": [
                    {"id": "owner", "name": "대표/관리자", "level": 100, "permissions": ["*"]},
                    {"id": "staff", "name": "직원", "level": 40, "permissions": ["work:read"]},
                ],
                "users": [],
                "positions": [{"id": "staff", "name": "사원", "level": 0, "description": ""}],
            },
        ),
        encoding="utf-8",
    )

    payload = AccessControlStore(tmp_path).read()
    position = next(item for item in payload["positions"] if item["id"] == "staff")
    assert position["permissions"] == ["work:read"]
    assert position["display_order"] == 40
