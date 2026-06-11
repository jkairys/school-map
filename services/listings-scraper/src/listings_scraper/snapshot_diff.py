"""Snapshot diff engine — pure, no IO.

Decides whether a new observation of an OTH listing differs materially from
the previous snapshot, and reports which fields changed.

This module deliberately has no DB, no httpx, and no camoufox dependencies.
A test in `tests/test_snapshot_diff.py` enforces that statically.

Cross-issue note (07 lands ahead of 05/08):

- Issue 05 owns `OTHListing` (the parsed search-API row).
- Issue 08 owns `ListingSnapshot` (the persisted DB row).

Both are expected to expose the material-field attributes listed in the
`SnapshotLike` Protocol below. Until those modules land, callers may pass any
object that satisfies the Protocol structurally; the reconciler in issue 08
will adapt its own types to fit.
"""

import re
from dataclasses import dataclass
from typing import Iterable, Iterator, Protocol, runtime_checkable

__all__ = ["ChangedFields", "INITIAL_SENTINEL", "MATERIAL_FIELDS", "SnapshotLike", "diff"]


INITIAL_SENTINEL = "__initial__"

MATERIAL_FIELDS: tuple[str, ...] = (
    "price",
    "price_display",
    "price_kind",
    "title",
    "blurb",
    "bedrooms",
    "bathrooms",
    "parking",
    "land_size_sqm",
    "property_type",
    "status",
)


@runtime_checkable
class SnapshotLike(Protocol):
    """Structural shape diff() compares.

    Only the material fields are part of the contract. Agent/agency live on
    the Listing row and are reconciled elsewhere (issue 08), not here.
    """

    price: int | None
    price_display: str | None
    price_kind: str | None
    title: str | None
    blurb: str | None
    bedrooms: int | None
    bathrooms: int | None
    parking: int | None
    land_size_sqm: int | None
    property_type: str | None
    status: str | None


@dataclass(frozen=True)
class ChangedFields:
    """Ordered, immutable list of changed material field names.

    The first element may be `INITIAL_SENTINEL` ("__initial__") to indicate
    the new observation has no prior snapshot.
    """

    fields: tuple[str, ...]

    def __init__(self, fields: Iterable[str]) -> None:
        object.__setattr__(self, "fields", tuple(fields))

    def __iter__(self) -> Iterator[str]:
        return iter(self.fields)

    def __contains__(self, item: object) -> bool:
        return item in self.fields

    def __len__(self) -> int:
        return len(self.fields)


_WHITESPACE = re.compile(r"\s+")
_STRING_FIELDS = frozenset({"title", "blurb", "status"})


def _normalise(field: str, value: object) -> object:
    if value is None:
        return None
    if field == "property_type":
        if not isinstance(value, str):
            return value
        return _WHITESPACE.sub(" ", value.strip()).lower()
    if field in _STRING_FIELDS:
        if not isinstance(value, str):
            return value
        return _WHITESPACE.sub(" ", value.strip())
    return value


def diff(prev: SnapshotLike | None, new: SnapshotLike) -> ChangedFields | None:
    """Return the material fields that differ between prev and new.

    - `prev is None` → `ChangedFields([INITIAL_SENTINEL, *observed_material_fields])`
      where `observed_material_fields` are those present (non-None) on `new`,
      in the canonical `MATERIAL_FIELDS` order.
    - All material fields equal under normalisation → `None`.
    - Otherwise → `ChangedFields([field_name, ...])` in canonical order.
    """
    if prev is None:
        observed = [f for f in MATERIAL_FIELDS if getattr(new, f, None) is not None]
        return ChangedFields([INITIAL_SENTINEL, *observed])

    changes: list[str] = []
    for field in MATERIAL_FIELDS:
        prev_val = _normalise(field, getattr(prev, field, None))
        new_val = _normalise(field, getattr(new, field, None))
        if prev_val != new_val:
            changes.append(field)

    return ChangedFields(changes) if changes else None
