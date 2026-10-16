#!/usr/bin/env python3
"""Stdlib-only validator for a documented subset of JSON Schema 2020-12.

Written for schemas/handoff-envelope.schema.json (issue #33). It is not a
general JSON Schema implementation and claims no conformance to the test suite.

Supported keywords (anything else in a schema is a SchemaError, so a schema can
never silently rely on a keyword this validator ignores):

  assertions   type, enum, const, required, properties, additionalProperties,
               items (single-schema form), pattern, minLength, maxLength, minimum
  applicators  $ref (local "#..." JSON Pointers only), $defs, if / then / else
  annotations  $schema, $id, $comment, title, description, examples, default

Deliberate differences from 2020-12, all stricter or equal:
  * "integer" means a JSON number written without a fraction or exponent
    (Python int), so 1.0 is not an integer here; the 2020-12 data model "makes
    no distinction between integers and other numbers" (Core §4.2.1).
    Booleans are never numbers.
  * enum/const compare JSON values exactly: true is not equal to 1.
  * pattern uses Python `re` with re.ASCII. An unescaped "$" outside a
    character class is rewritten to "\\Z", so it matches only at the true end
    of the string, as in ECMA-262; Python's plain "$" would also match before
    a trailing newline.

Usage:
  python tools/schema_subset.py SCHEMA.json INSTANCE.json [INSTANCE.json ...]
Exit status: 0 all valid, 1 some instance invalid, 2 bad schema or usage.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ASSERTIONS = {"type", "enum", "const", "required", "properties", "additionalProperties",
              "items", "pattern", "minLength", "maxLength", "minimum"}
APPLICATORS = {"$ref", "$defs", "if", "then", "else"}
ANNOTATIONS = {"$schema", "$id", "$comment", "title", "description", "examples", "default"}
SUPPORTED = ASSERTIONS | APPLICATORS | ANNOTATIONS
TYPES = {"object", "array", "string", "integer", "number", "boolean", "null"}


class SchemaError(ValueError):
    """The schema uses something outside the supported subset or is malformed."""


def _ecma_pattern(pattern: str) -> re.Pattern[str]:
    out, i, in_class = [], 0, False
    while i < len(pattern):
        c = pattern[i]
        if c == "\\" and i + 1 < len(pattern):
            out.append(pattern[i:i + 2])
            i += 2
            continue
        if c == "[" and not in_class:
            in_class = True
        elif c == "]" and in_class:
            in_class = False
        elif c == "$" and not in_class:
            c = r"\Z"
        out.append(c)
        i += 1
    try:
        return re.compile("".join(out), re.ASCII)
    except re.error as exc:
        raise SchemaError(f"invalid pattern {pattern!r}: {exc}") from exc


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    raise TypeError(f"not a JSON value: {type(value).__name__}")


def _has_type(value: Any, name: str) -> bool:
    actual = _json_type(value)
    return actual == name or (name == "number" and actual == "integer")


def _json_equal(a: Any, b: Any) -> bool:
    ta, tb = _json_type(a), _json_type(b)
    if {ta, tb} <= {"integer", "number"}:
        return a == b
    if ta != tb:
        return False
    if ta == "array":
        return len(a) == len(b) and all(_json_equal(x, y) for x, y in zip(a, b))
    if ta == "object":
        return a.keys() == b.keys() and all(_json_equal(a[k], b[k]) for k in a)
    return a == b


def _pointer(path: tuple[Any, ...]) -> str:
    return "/" + "/".join(str(p).replace("~", "~0").replace("/", "~1") for p in path) if path else "(root)"


class Validator:
    def __init__(self, schema: Any):
        self.root = schema
        self._patterns: dict[str, re.Pattern[str]] = {}
        self.check_schema(schema, "#")

    # ------------------------------------------------------------------ schema checks
    def check_schema(self, schema: Any, where: str) -> None:
        if isinstance(schema, bool):
            return
        if not isinstance(schema, dict):
            raise SchemaError(f"{where}: a schema must be an object or a boolean")
        unknown = sorted(set(schema) - SUPPORTED)
        if unknown:
            raise SchemaError(f"{where}: unsupported keyword(s) {unknown}")
        t = schema.get("type")
        if t is not None:
            names = t if isinstance(t, list) else [t]
            if not names or any(n not in TYPES for n in names):
                raise SchemaError(f"{where}: invalid type {t!r}")
        if "required" in schema and not (isinstance(schema["required"], list)
                                         and all(isinstance(k, str) for k in schema["required"])):
            raise SchemaError(f"{where}: required must be a list of strings")
        if "enum" in schema and not isinstance(schema["enum"], list):
            raise SchemaError(f"{where}: enum must be a list")
        for key in ("minLength", "maxLength"):
            if key in schema and not (type(schema[key]) is int and schema[key] >= 0):
                raise SchemaError(f"{where}: {key} must be a non-negative integer")
        if "minimum" in schema and _json_type(schema["minimum"]) not in ("integer", "number"):
            raise SchemaError(f"{where}: minimum must be a number")
        if "pattern" in schema:
            if not isinstance(schema["pattern"], str):
                raise SchemaError(f"{where}: pattern must be a string")
            self._patterns.setdefault(schema["pattern"], _ecma_pattern(schema["pattern"]))
        if "$ref" in schema:
            self._resolve(schema["$ref"], where)
        for key in ("properties", "$defs"):
            if key in schema:
                if not isinstance(schema[key], dict):
                    raise SchemaError(f"{where}: {key} must be an object")
                for name, sub in schema[key].items():
                    self.check_schema(sub, f"{where}/{key}/{name}")
        for key in ("additionalProperties", "items", "if", "then", "else"):
            if key in schema:
                if key == "items" and isinstance(schema[key], list):
                    raise SchemaError(f"{where}: array-form items is not supported")
                self.check_schema(schema[key], f"{where}/{key}")

    def _resolve(self, ref: Any, where: str) -> Any:
        if not isinstance(ref, str) or not (ref == "#" or ref.startswith("#/")):
            raise SchemaError(f"{where}: only local '#/...' $ref is supported, got {ref!r}")
        node: Any = self.root
        for part in ref[2:].split("/") if ref != "#" else []:
            part = part.replace("~1", "/").replace("~0", "~")
            if not isinstance(node, dict) or part not in node:
                raise SchemaError(f"{where}: unresolvable $ref {ref!r}")
            node = node[part]
        return node

    # ------------------------------------------------------------------ validation
    def errors(self, instance: Any) -> list[str]:
        out: list[str] = []
        self._validate(instance, self.root, (), out, depth=0)
        return out

    def is_valid(self, instance: Any) -> bool:
        return not self.errors(instance)

    def _validate(self, value: Any, schema: Any, path: tuple[Any, ...], out: list[str], depth: int) -> None:
        if depth > 64:
            raise SchemaError("$ref recursion deeper than 64 levels")
        at = _pointer(path)
        if schema is True:
            return
        if schema is False:
            out.append(f"{at}: no value is allowed here")
            return
        if "$ref" in schema:
            self._validate(value, self._resolve(schema["$ref"], at), path, out, depth + 1)
        if "type" in schema:
            names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
            if not any(_has_type(value, n) for n in names):
                out.append(f"{at}: expected type {' or '.join(names)}, got {_json_type(value)}")
                return
        if "const" in schema and not _json_equal(value, schema["const"]):
            out.append(f"{at}: must equal {json.dumps(schema['const'])}")
        if "enum" in schema and not any(_json_equal(value, e) for e in schema["enum"]):
            out.append(f"{at}: must be one of {json.dumps(schema['enum'])}")
        if isinstance(value, str):
            if "minLength" in schema and len(value) < schema["minLength"]:
                out.append(f"{at}: shorter than minLength {schema['minLength']}")
            if "maxLength" in schema and len(value) > schema["maxLength"]:
                out.append(f"{at}: longer than maxLength {schema['maxLength']}")
            if "pattern" in schema and not self._patterns[schema["pattern"]].search(value):
                out.append(f"{at}: does not match pattern {schema['pattern']!r}")
        if _json_type(value) in ("integer", "number") and "minimum" in schema and value < schema["minimum"]:
            out.append(f"{at}: below minimum {schema['minimum']}")
        if isinstance(value, dict):
            for key in schema.get("required", []):
                if key not in value:
                    out.append(f"{at}: missing required property {key!r}")
            props = schema.get("properties", {})
            for key, sub in value.items():
                if key in props:
                    self._validate(sub, props[key], path + (key,), out, depth)
                elif "additionalProperties" in schema:
                    extra = schema["additionalProperties"]
                    if extra is False:
                        out.append(f"{at}: unexpected property {key!r}")
                    else:
                        self._validate(sub, extra, path + (key,), out, depth)
        if isinstance(value, list) and "items" in schema:
            for i, item in enumerate(value):
                self._validate(item, schema["items"], path + (i,), out, depth)
        if "if" in schema:
            probe: list[str] = []
            self._validate(value, schema["if"], path, probe, depth)
            branch = schema.get("then" if not probe else "else")
            if branch is not None:
                self._validate(value, branch, path, out, depth)


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__.split("Usage:")[1].strip().splitlines()[0].strip(), file=sys.stderr)
        return 2
    try:
        validator = Validator(load_json(argv[0]))
    except (OSError, ValueError) as exc:
        print(f"schema error: {exc}", file=sys.stderr)
        return 2
    status = 0
    for name in argv[1:]:
        try:
            errs = validator.errors(load_json(name))
        except (OSError, ValueError) as exc:
            errs = [f"cannot read instance: {exc}"]
        print(f"{'valid  ' if not errs else 'INVALID'} {name}")
        for e in errs:
            print(f"  {e}")
        status = status or (1 if errs else 0)
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
