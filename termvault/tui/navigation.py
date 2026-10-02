"""Vim-style list navigation helpers for Phase 5 Part 2.

These helpers keep cursor math out of the app class so Pilot tests and
future keybindings (page jumps, half-page, wrap) stay easy to unit-test.
"""

from __future__ import annotations

from typing import Sequence, TypeVar

T = TypeVar("T")


def move_index(current: int | None, *, delta: int, size: int) -> int | None:
    """Move a list index by delta, clamped to available rows."""
    if size <= 0:
        return None
    base = 0 if current is None else current
    return max(0, min(size - 1, base + delta))


def move_index_wrap(current: int | None, *, delta: int, size: int) -> int | None:
    """Move a list index by delta, wrapping at the ends."""
    if size <= 0:
        return None
    base = 0 if current is None else current
    return (base + delta) % size


def top_index(size: int) -> int | None:
    return 0 if size > 0 else None


def bottom_index(size: int) -> int | None:
    return size - 1 if size > 0 else None


def page_delta(*, page_size: int = 10) -> int:
    """Default page jump used by Ctrl+d / Ctrl+u style motions."""
    return max(1, page_size)


def page_down(current: int | None, *, size: int, page_size: int = 10) -> int | None:
    return move_index(current, delta=page_delta(page_size=page_size), size=size)


def page_up(current: int | None, *, size: int, page_size: int = 10) -> int | None:
    return move_index(current, delta=-page_delta(page_size=page_size), size=size)


def half_page_down(current: int | None, *, size: int, viewport: int = 20) -> int | None:
    return move_index(current, delta=max(1, viewport // 2), size=size)


def half_page_up(current: int | None, *, size: int, viewport: int = 20) -> int | None:
    return move_index(current, delta=-max(1, viewport // 2), size=size)


def clamp_index(index: int | None, size: int) -> int | None:
    """Ensure an index is valid for a list of the given size."""
    if size <= 0:
        return None
    if index is None:
        return 0
    return max(0, min(size - 1, index))


def index_of_id(items: Sequence[T], item_id: int, *, id_attr: str = "id") -> int | None:
    """Find the list index of an object with a matching id attribute."""
    for index, item in enumerate(items):
        if getattr(item, id_attr, None) == item_id:
            return index
    return None


def select_relative(
    items: Sequence[T],
    current_id: int | None,
    *,
    delta: int,
    id_attr: str = "id",
) -> T | None:
    """Return the item delta steps away from current_id (clamped)."""
    if not items:
        return None
    if current_id is None:
        return items[0]
    current = index_of_id(items, current_id, id_attr=id_attr)
    next_index = move_index(current, delta=delta, size=len(items))
    if next_index is None:
        return None
    return items[next_index]


def describe_position(index: int | None, size: int) -> str:
    """Human-readable cursor position for status lines."""
    if size <= 0 or index is None:
        return "0/0"
    return f"{index + 1}/{size}"
