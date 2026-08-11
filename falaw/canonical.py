"""One canonical byte-form for everything falaw hashes (falaw#17).

falaw derives money-bearing identities from JSON: the per-call cache key
(:func:`falaw.cache._key`), the whole-plan idempotency handle
(:func:`falaw.plan.plan_hash`), and the dry-run artifact id
(``falaw.plan._synthetic_artifact``). Before this module each site called
``json.dumps(..., sort_keys=True, default=str)`` — and ``default=str`` is a
**give-up-quietly branch inside a key-composition function**, which fails in
both directions at once:

* two structurally different values whose ``str()`` coincide collapse to one
  key — ``Decimal("0.5")`` vs ``"0.5"``, ``Path("/a/b")`` vs ``"/a/b"`` — a
  silent *wrong hit*: the caller is handed someone else's artifact and billed
  it as a saving;
* an object without a stable ``str()`` (the default ``<Ref object at 0x...>``
  repr) mints a fresh key per instance — a *permanent miss* plus unbounded
  cache growth.

JSON's silent key coercion has the same collision property from the other
side: ``{1: "x"}`` and ``{"1": "x"}`` dump to identical bytes, so two
different argument dicts share a key. (``lacing`` rejects the same case in
its digests, for the same reason.)

The rule this module enforces: **a key-composition function must never have a
"give up quietly" branch.** :func:`canonical_blob` serializes with
``sort_keys=True``, **no** ``default``, ``allow_nan=False``, and string-only
mapping keys — anything else raises :class:`falaw.errors.FalNonCanonicalArgument`
naming the offending path and type, so the failure is a diagnosable refusal at
plan time rather than a wrong artifact at collect time.

Two payload projections live here **side by side, on purpose**:

* :func:`cache_key_payload` — ``{app, args}``, the per-call content-addressed
  cache key;
* :func:`plan_identity_payload` — ``{app, args, tool}``, the structural
  idempotency form shared by ``plan_hash`` and the dry-run artifact id.

The field sets differ deliberately (``tool`` is a falaw-side label; the
underlying fal call is the same whatever the tool was called), but a field
that changes *what the call produces* must go into **both** — in this module,
in one commit. That is the discipline falaw#15's ``CallPlan.backend`` needs:
a backend added to ``plan_hash`` but not the cache key would let one backend
return another backend's artifact as a wrong hit.

Byte-compatibility: for JSON-native payloads the output of
:func:`canonical_blob` is identical to the old form, so every cache entry
whose arguments were already JSON-native keeps its key. Invalidated —
deliberately, because their keys were unreliable or unportable — are entries
whose arguments needed any of JSON's laxities: the ``default=str``
stringification, a bare ``NaN``/``Infinity`` (previously serialized natively),
or silently-coerced non-string mapping keys. ``tests/test_canonical.py`` pins
the stability half with literal digests.
"""

from __future__ import annotations

import json
import math
from typing import Any, Iterator, Mapping, Optional

from .errors import FalNonCanonicalArgument

__all__ = [
    "canonical_blob",
    "ensure_canonical",
    "cache_key_payload",
    "plan_identity_payload",
]


_EXIT = object()
"""Stack sentinel: 'every child of this container has been visited'."""


def _offenders(value: Any, path: str) -> Iterator[tuple[str, str]]:
    """Yield ``(path, why)`` for every non-canonicalisable node under ``value``.

    The acceptance set is **exactly** what ``json.dumps`` (no ``default``)
    serializes, because anything the walk accepts and the serializer then
    rejects escapes as an untyped ``TypeError`` — which is the give-up-quietly
    hole this module exists to close, reopened one layer down. Two
    consequences that look pedantic and are not:

    * only ``dict`` recurses — a non-``dict`` ``Mapping`` (``MappingProxyType``,
      ``ChainMap``) is refused even though it walks like a dict, because
      ``json.dumps`` refuses it;
    * a **circular** value is refused here, as a typed error, where
      ``json.dumps`` would raise its own ``ValueError``.

    Iterative (explicit stack) rather than recursive: the serializer's C
    encoder handles thousands of nesting levels, and the validator must not
    have a lower ceiling than the thing it guards (a ``RecursionError`` at
    depth 1000 would be an untyped crash for a payload the old code hashed).
    ``on_path`` tracks ancestors only, so a diamond — the same object reached
    twice non-cyclically — walks fine, exactly as ``json`` treats it.
    """
    on_path: set[int] = set()
    stack: list = [(value, path)]
    while stack:
        top = stack.pop()
        if top[0] is _EXIT:
            on_path.discard(top[1])
            continue
        node, node_path = top
        # bool before int: bool is an int subclass and is fine either way, but
        # the explicit branch documents that True/False are canonical JSON.
        if node is None or isinstance(node, (str, bool, int)):
            continue
        if isinstance(node, float):
            if not math.isfinite(node):
                yield node_path, f"non-finite float {node!r}"
            continue
        if isinstance(node, dict):
            if id(node) in on_path:
                yield node_path, "circular reference (the value contains itself)"
                continue
            on_path.add(id(node))
            stack.append((_EXIT, id(node)))
            for k, v in node.items():
                if not isinstance(k, str):
                    yield (
                        f"{node_path}.{k!r}",
                        f"non-string mapping key {k!r} of type {type(k).__name__} "
                        "(JSON key coercion can collide: {1: ...} and {'1': ...} "
                        "would share a key)",
                    )
                else:
                    stack.append((v, f"{node_path}.{k}"))
            continue
        if isinstance(node, Mapping):
            yield (
                node_path,
                f"mapping of type {type(node).__name__} is not a dict — "
                "json.dumps refuses non-dict mappings; convert with dict(...) "
                "at the boundary",
            )
            continue
        if isinstance(node, (list, tuple)):
            if id(node) in on_path:
                yield node_path, "circular reference (the value contains itself)"
                continue
            on_path.add(id(node))
            stack.append((_EXIT, id(node)))
            for i, item in enumerate(node):
                stack.append((item, f"{node_path}[{i}]"))
            continue
        yield (
            node_path,
            f"value of type {type(node).__name__} is not JSON-canonicalisable",
        )


def ensure_canonical(payload: Any, *, context: str = "arguments") -> None:
    """Raise :class:`FalNonCanonicalArgument` unless ``payload`` is canonical JSON.

    Canonical means: ``str`` / ``bool`` / ``int`` / finite ``float`` / ``None``
    scalars, ``list`` / ``tuple`` sequences, and mappings with **string** keys,
    recursively. Call this at a boundary (``make_call_plan``,
    ``cached_call_fal``) so the refusal happens while it is still free —
    before any network call, not on the way to one.
    """
    found = next(_offenders(payload, context), None)
    if found is not None:
        path, why = found
        raise FalNonCanonicalArgument(
            f"{path}: {why}. Cache keys and plan hashes require JSON-native "
            "values — convert at the plan_* boundary (e.g. str(path), "
            "float(decimal)) and say what you mean, rather than relying on a "
            "lossy implicit str().",
            path=path,
        )


def canonical_blob(payload: Any) -> bytes:
    """The one byte-form falaw hashes: sorted keys, no fallback, no NaN.

    Raises :class:`FalNonCanonicalArgument` for anything JSON cannot represent
    faithfully — there is deliberately no ``default=`` escape hatch, because a
    hashing function that guesses is a hashing function that collides.
    """
    ensure_canonical(payload, context="payload")
    return json.dumps(payload, sort_keys=True, allow_nan=False).encode("utf-8")


def cache_key_payload(application: str, arguments: Mapping[str, Any]) -> dict:
    """``{app, args}`` — what the per-call content-addressed cache keys on.

    No ``tool``: two CallPlans differing only in falaw-side labelling make the
    same fal call and *should* share a cache entry. A field that changes what
    the call **produces** (falaw#15's ``backend``) must be added here AND in
    :func:`plan_identity_payload`.
    """
    return {"app": application, "args": dict(arguments)}


def plan_identity_payload(
    application: str, arguments: Mapping[str, Any], *, tool: Optional[str]
) -> dict:
    """``{app, args, tool}`` — the structural form behind ``plan_hash`` and
    the dry-run artifact id.

    Includes ``tool`` so a re-plan of the same request is recognizable as the
    same *plan* even though the cache would treat the calls identically. The
    counterpart projection is :func:`cache_key_payload`; keep them adjacent so
    adding a field to one is an explicit decision about the other.
    """
    return {"app": application, "args": dict(arguments), "tool": tool}
