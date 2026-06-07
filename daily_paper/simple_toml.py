import ast
from typing import Any, Dict


def load(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return loads(handle.read())


def loads(text: str) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    current: Dict[str, Any] = data
    for raw_line in _logical_lines(text):
        line = _strip_comment(raw_line).strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            current = data
            for part in section.split("."):
                key = _parse_key(part.strip())
                current = current.setdefault(key, {})
            continue
        if "=" not in line:
            raise ValueError("Invalid TOML line: %s" % raw_line)
        key, value = line.split("=", 1)
        current[_parse_key(key.strip())] = _parse_value(value.strip())
    return data


def _logical_lines(text: str):
    buffered = []
    balance = 0
    for raw_line in text.splitlines():
        stripped = _strip_comment(raw_line).strip()
        if not stripped and not buffered:
            yield raw_line
            continue
        balance += stripped.count("[") - stripped.count("]")
        if buffered or balance > 0:
            buffered.append(stripped)
            if balance <= 0:
                yield " ".join(buffered)
                buffered = []
                balance = 0
            continue
        yield raw_line
    if buffered:
        yield " ".join(buffered)


def _strip_comment(line: str) -> str:
    in_quote = False
    quote = ""
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char in ("'", '"'):
            if in_quote and char == quote:
                in_quote = False
                quote = ""
            elif not in_quote:
                in_quote = True
                quote = char
        if char == "#" and not in_quote:
            return line[:index]
    return line


def _parse_key(value: str) -> str:
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return ast.literal_eval(value)
    return value


def _parse_value(value: str) -> Any:
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    try:
        return ast.literal_eval(value)
    except (ValueError, SyntaxError):
        pass
    try:
        return int(value)
    except ValueError:
        return value
