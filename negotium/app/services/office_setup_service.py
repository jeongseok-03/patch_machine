"""Initial office setup service boundary."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from negotium.app.initial_setup import ParsedSetupFile
    from negotium.app.schemas import CompanyProfilePayload, InitialOfficeSetupResult


def build_initial_office_setup_prompt(
    *,
    message: str,
    intent: str,
    parsed_files: list[ParsedSetupFile],
    company_profile: CompanyProfilePayload | None = None,
) -> str:
    from negotium.app.api import _initial_office_setup_prompt

    return _initial_office_setup_prompt(
        message=message,
        intent=intent,
        parsed_files=parsed_files,
        company_profile=company_profile,
    )


def parse_initial_setup_result(
    raw: str,
    *,
    parsed_files: list[ParsedSetupFile],
    company_profile: CompanyProfilePayload | None = None,
) -> InitialOfficeSetupResult:
    from negotium.app.api import _parse_initial_setup_result

    return _parse_initial_setup_result(
        raw,
        parsed_files=parsed_files,
        company_profile=company_profile,
    )


def try_load_json_object(raw: str) -> dict[str, Any] | None:
    from negotium.app.api import _try_load_json_object

    return _try_load_json_object(raw)
