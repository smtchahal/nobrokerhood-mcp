"""
Shared response-filtering utilities.
"""

from typing import Any


def pick_fields(data: Any, fields: list[str] | None) -> Any:
    """
    Return a subset of *data* containing only the dot-notation *fields*.

    Each field is a dot-separated key path, e.g. ``"data.apartments.apartment.id"``.
    When a key maps to a list, the remainder of the path is applied to every
    element of that list so the list structure is preserved.

    Multiple paths that share a common prefix are merged, so:

        pick_fields(resp, ["data.apartments.apartment.id",
                           "data.apartments.apartment.name"])

    returns a dict whose ``data.apartments`` list contains objects with only
    ``apartment.id`` and ``apartment.name``.

    If *fields* is ``None`` or empty the original *data* is returned unchanged.

    Args:
        data:   The response dict (or any JSON-compatible value) to filter.
        fields: List of dot-notation paths to keep.  ``None`` → no filtering.

    Returns:
        Filtered copy of *data*, or *data* itself when *fields* is falsy.
    """
    if not fields:
        return data
    result: dict = {}
    for field in fields:
        _apply_path(result, data, field.split("."))
    return result


def _apply_path(target: Any, source: Any, parts: list[str]) -> None:
    """Recursively project *parts* from *source* into *target*."""
    if not parts or source is None:
        return

    # When descending into a list, zip target and source element-wise.
    if isinstance(source, list):
        if not isinstance(target, list):
            return
        for t_item, s_item in zip(target, source, strict=False):
            _apply_path(t_item, s_item, parts)
        return

    if not isinstance(source, dict):
        return

    key = parts[0]
    rest = parts[1:]

    if key not in source:
        return

    val = source[key]

    if not rest:
        # Terminal: copy the whole value as-is.
        target[key] = val
        return

    if isinstance(val, list):
        # Initialise the target list with empty dicts on first visit; subsequent
        # field paths will merge into those same dicts.
        if key not in target:
            target[key] = [{} for _ in val]
        for t_item, s_item in zip(target[key], val, strict=False):
            _apply_path(t_item, s_item, rest)
    elif isinstance(val, dict):
        if key not in target:
            target[key] = {}
        _apply_path(target[key], val, rest)
    else:
        # Scalar at a non-terminal path — include the whole value.
        target[key] = val
