import re
import sys
from typing import Any


def _is_dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


def _safe_getattr(obj: Any, name: str) -> Any:
    try:
        return getattr(obj, name)
    except Exception as e:
        return e


def _type_repr(tp: Any) -> str:
    try:
        return tp.__name__  # type: ignore[attr-defined]
    except Exception:
        return str(tp)


def _shallow_size_kb(value: Any) -> float:
    try:
        return sys.getsizeof(value) / 1024.0
    except Exception:
        return float("nan")


def is_alive_agent_method(member: Any) -> bool:
    return bool(getattr(member, "__is_alive_agent__", False))


def extract_angle_doc(doc: str | None) -> str | None:
    ANGLE_RE = re.compile(r"<([^<>]+)>")
    if not doc:
        return None
    m = ANGLE_RE.search(doc)
    return m.group(1).strip() if m else doc  # fallback: whole doc if no <...>


def extract_no_angle_doc(doc: str | None) -> str:
    ANGLE_BLOCK_RE = re.compile(r"<(.*?)>", re.DOTALL)
    return ANGLE_BLOCK_RE.sub("", doc).strip() or ""
