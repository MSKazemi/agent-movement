"""Deterministic JSON canonicalization: a documented subset of RFC 8785 (JCS).

Supported values: objects with string keys, arrays, strings, booleans, null and
integers in the I-JSON safe range |n| <= 2**53 - 1. Floating-point numbers are
REJECTED instead of serialized, which removes the only part of RFC 8785 that
needs ECMAScript number formatting. Inside this subset the output is
byte-identical to RFC 8785:

* object members are sorted by the UTF-16 code units of their names
  (not by Python code points; they differ for characters above U+FFFF);
* no insignificant whitespace;
* strings escape only ``"``, ``\\`` and U+0000..U+001F, using ``\\b \\f \\n
  \\r \\t`` where available and lowercase ``\\u00xx`` otherwise; all other
  characters are emitted literally as UTF-8;
* lone surrogates are rejected (they cannot be encoded as UTF-8).

This module is dependency-free and does not claim full RFC 8785 conformance.
"""

from __future__ import annotations

import hashlib
from typing import Any

MAX_SAFE_INTEGER = 2 ** 53 - 1
_SHORT_ESCAPES = {'"': '\\"', "\\": "\\\\", "\b": "\\b", "\f": "\\f",
                  "\n": "\\n", "\r": "\\r", "\t": "\\t"}


class CanonicalizationError(ValueError):
    """Value lies outside the documented canonical JSON subset."""


def _string(value: str) -> str:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise CanonicalizationError("string contains a lone surrogate") from exc
    out = ['"']
    for char in value:
        if char in _SHORT_ESCAPES:
            out.append(_SHORT_ESCAPES[char])
        elif ord(char) < 0x20:
            out.append(f"\\u{ord(char):04x}")
        else:
            out.append(char)
    out.append('"')
    return "".join(out)


def _utf16_key(name: str) -> bytes:
    # Big-endian UTF-16 bytes compare lexicographically exactly like code units.
    return name.encode("utf-16-be", "surrogatepass")


def _serialize(value: Any, out: list[str], depth: int) -> None:
    if depth > 64:
        raise CanonicalizationError("nesting too deep")
    if value is None:
        out.append("null")
    elif value is True:
        out.append("true")
    elif value is False:
        out.append("false")
    elif isinstance(value, int):
        if abs(value) > MAX_SAFE_INTEGER:
            raise CanonicalizationError("integer outside the I-JSON safe range")
        out.append(str(int(value)))
    elif isinstance(value, float):
        raise CanonicalizationError("floating-point numbers are outside the canonical subset")
    elif isinstance(value, str):
        out.append(_string(value))
    elif isinstance(value, (list, tuple)):
        out.append("[")
        for index, item in enumerate(value):
            if index:
                out.append(",")
            _serialize(item, out, depth + 1)
        out.append("]")
    elif isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise CanonicalizationError("object keys must be strings")
        out.append("{")
        for index, key in enumerate(sorted(value, key=_utf16_key)):
            if index:
                out.append(",")
            out.append(_string(key))
            out.append(":")
            _serialize(value[key], out, depth + 1)
        out.append("}")
    else:
        raise CanonicalizationError(f"unsupported type {type(value).__name__}")


def canonicalize(value: Any) -> bytes:
    """Return the canonical UTF-8 bytes of ``value``."""
    out: list[str] = []
    _serialize(value, out, 0)
    return "".join(out).encode("utf-8")


def jcs_digest(value: Any) -> str:
    """``sha256:<hex>`` over the canonical bytes."""
    return "sha256:" + hashlib.sha256(canonicalize(value)).hexdigest()
