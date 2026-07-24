"""Memory service boundary."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from negotium.app.container import Container
    from negotium.domain.ports import LlmMessage


def build_chat_messages(
    container: Container, user_message: str, *, user_id: str = "default"
) -> list[LlmMessage]:
    from negotium.app.api import _build_chat_messages

    messages, _ = _build_chat_messages(container, user_message, user_id=user_id)
    return messages


def update_user_volatile_memory_after_chat(
    container: Container,
    *,
    actor: str,
    user_message: str,
    answer: str,
) -> None:
    from negotium.app.api import _update_user_volatile_memory_after_chat

    _update_user_volatile_memory_after_chat(
        container, actor=actor, user_message=user_message, answer=answer
    )
