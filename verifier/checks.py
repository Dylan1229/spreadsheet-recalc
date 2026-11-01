"""Verdict helpers shared by the verifier modules. Pure functions of their arguments and the files on disk."""

import hashlib
import json
import math
from pathlib import Path

MAX_FILE_BYTES = 64 * 1024  # far above any saved values file (about 1 KB)


def result(valid, message, *, score=None, **details):
    return {
        "valid": valid,
        "score": float(valid) if score is None else score,
        "message": message,
        "details": details,
    }


def plain(value):
    """A value as JSON a verdict can hold: non-finite floats as text."""
    if isinstance(value, float) and not math.isfinite(value):
        return repr(value)
    if isinstance(value, list | tuple):
        return [plain(item) for item in value]
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items()}
    return value


def check(identifier, ok, expected=None, actual=None, message=""):
    """One named check: ok is True (holds), False (fails) or None (not checked: a check it needs failed)."""
    return {
        "id": identifier,
        "ok": ok,
        "expected": plain(expected),
        "actual": plain(actual),
        "message": "" if ok is True else message,
    }


def not_checked(identifier, needs):
    return check(identifier, None, message=f"not checked: {needs} failed")


def verdict(checks, success, score, **details):
    """valid when every check holds; the message is the first failing check (else the first not checked) and how
    many more fail."""
    failed = [entry for entry in checks if entry["ok"] is False]
    if all(entry["ok"] is True for entry in checks):
        return result(True, success, score=score, checks=checks, **details)
    first = failed[0] if failed else next(entry for entry in checks if entry["ok"] is not True)
    more = f" (+{len(failed) - 1} more failing)" if len(failed) > 1 else ""
    return result(False, f"{first['id']}: {first['message']}{more}", score=score, checks=checks, **details)


def values_path(workbook, targets):
    """Where save_values saves a task's values: values/<workbook>-<first 10 hex digits of the sha256 of the
    targets joined by ','>.json."""
    digest = hashlib.sha256(",".join(targets).encode()).hexdigest()[:10]
    return f"values/{workbook}-{digest}.json"


def read_saved(workspace, path, expected):
    """(the JSON object saved at ``path``, None) or (None, why it is not the file save_values saved): ``path``
    must be ``expected``, inside the workspace, a file of at most 64 KB holding a JSON object."""
    if path != expected:
        if not path or path.startswith("/") or ".." in path.split("/"):
            return None, f"path {path!r} is not a relative path inside the workspace"
        return None, f"path {path!r} is not {expected}, where save_values saves this task's values"
    try:
        root = Path(workspace).resolve()
        file = (root / path).resolve()
        if not file.is_relative_to(root):
            return None, f"{path} leads outside the workspace"
        if not file.is_file():
            return None, f"no file at {path}: call save_values before submitting"
        if file.stat().st_size > MAX_FILE_BYTES:
            return None, f"{path} holds over {MAX_FILE_BYTES} bytes, more than any saved values file"
        data = json.loads(file.read_text(encoding="utf-8"))
    except RecursionError:
        return None, f"{path} nests too deeply to be a saved values file"
    except (OSError, RuntimeError):
        return None, f"{path} cannot be read"
    except ValueError:
        return None, f"{path} is not UTF-8 JSON"
    if not isinstance(data, dict):
        return None, f"{path} holds no JSON object"
    return data, None


def differences(saved, submitted):
    """The fields in which a saved file and a submission differ, sorted. JSON text is compared, so 1 and 1.0
    or true never pass for each other."""

    def text(value):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)

    keys = set(saved) | set(submitted)
    try:
        return sorted(
            key for key in keys if key not in saved or key not in submitted or text(saved[key]) != text(submitted[key])
        )
    except RecursionError:
        return ["(a field nests too deeply to compare)"]
