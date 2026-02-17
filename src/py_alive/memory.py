

from __future__ import annotations

from typing import Any, Generic, TypeVar, get_args, get_origin

from pydantic import BaseModel, ConfigDict, computed_field

from .tools_registry import AliveTag

T = TypeVar("T")


"""

NEED UPDATE
- tags
- exclude
-

"""

# ----------------------------
# AliveMemory (Option 3 name)
# ----------------------------
class AliveMemory(BaseModel, Generic[T]):
    model_config = ConfigDict(
        use_attribute_docstrings=True,
        validate_assignment=True,
        arbitrary_types_allowed=True,
    )
    
    value: T
    """The stored value (typed)."""
    
    description: str = ""
    """Human-readable description of this memory slot."""
    
    hint_override: str | None = None
    """Optional manual hint override (rarely needed)."""
    
    tags: list | str | AliveTag | None = None
    
    # ---------- structural truth (generic param) ----------
    
    @computed_field(return_type=str | None)
    @property
    def hint(self) -> str | None:
        """
        Runtime structural truth: derived from AliveMemory[T] (generic parameter),
        not from type(value). Falls back to hint_override.
        """
        if self.hint_override:
            return self._normalize_hint(self.hint_override)
        
        ann = self._structural_annotation()
        return self._type_repr(ann) if ann is not None else None
    
    def _structural_annotation(self) -> Any | None:
        meta = getattr(self.__class__, "__pydantic_generic_metadata__", None)
        if isinstance(meta, dict):
            args = meta.get("args")
            if args and len(args) == 1:
                return args[0]
        
        meta2 = getattr(self, "__pydantic_generic_metadata__", None)
        if isinstance(meta2, dict):
            args = meta2.get("args")
            if args and len(args) == 1:
                return args[0]
        
        return None
    
    # ---------- computed fields ----------
    
    @computed_field(return_type=str)
    @property
    def type_name(self) -> str:
        """Concrete runtime instance type name."""
        try:
            return type(self.value).__name__
        except Exception:
            return "UNKNOWN"
    
    @computed_field(return_type=float | None)
    @property
    def size_kb(self) -> float | None:
        """Approx shallow size in KB (best-effort)."""
        try:
            import sys
            
            return round(sys.getsizeof(self.value) / 1024.0, 3)
        except Exception:
            return None
    
    @computed_field(return_type=str)
    @property
    def preview(self) -> str:
        """
        Safe preview string (truncated).
        If hint conflicts with runtime type, mention it.
        """
        base = self._safe_preview(self.value)
        h = self.hint
        if h and self._hint_conflicts_with_runtime(h, self.value):
            return f"{base}  [hint={h} ≠ runtime={self.type_name}]"
        return base
    
    # ---------- helpers ----------
    
    @staticmethod
    def _normalize_hint(h: str) -> str:
        return " ".join(h.strip().split())
    
    @staticmethod
    def _hint_conflicts_with_runtime(hint: str, value: Any) -> bool:
        """
        Conservative mismatch detection:
        - simple names: 'int' vs runtime type name
        - outer container mismatch: list[...] but not list, dict[...] but not dict
        """
        try:
            if value is None:
                return False
            
            rt_name = type(value).__name__
            s = hint.replace("typing.", "").strip()
            
            if "[" not in s and "|" not in s:
                return s != rt_name
            
            if s.startswith("list[") and not isinstance(value, list):
                return True
            if s.startswith("dict[") and not isinstance(value, dict):
                return True
            if s.startswith("tuple[") and not isinstance(value, tuple):
                return True
            if s.startswith("set[") and not isinstance(value, set):
                return True
            
            return False
        except Exception:
            return False
    
    @staticmethod
    def _safe_preview(value: Any, max_chars: int = 220, max_items: int = 20) -> str:
        try:
            if isinstance(value, Exception):
                s = f"{type(value).__name__}: {value}"
                return s[:max_chars] + ("…" if len(s) > max_chars else "")
            
            if value is None:
                return "None"
            
            if isinstance(value, (str, bytes, bytearray)):
                if isinstance(value, (bytes, bytearray)):
                    s = f"{type(value).__name__}(len={len(value)})"
                else:
                    s = value
                return s[:max_chars] + ("…" if len(s) > max_chars else "")
            
            if isinstance(value, dict):
                keys = list(value.keys())[:max_items]
                s = f"dict(len={len(value)}, keys={keys})"
                return s[:max_chars] + ("…" if len(s) > max_chars else "")
            
            if isinstance(value, (list, tuple, set, frozenset)):
                seq = list(value)[:max_items]
                s = f"{type(value).__name__}(len={len(value)}, head={seq})"
                return s[:max_chars] + ("…" if len(s) > max_chars else "")
            
            s = repr(value)
            return s[:max_chars] + ("…" if len(s) > max_chars else "")
        except Exception:
            return "<unpreviewable>"
    
    @staticmethod
    def _type_repr(tp: Any) -> str:
        """Human-friendly type representation from typing annotations."""
        try:
            if tp is None:
                return "None"
            if isinstance(tp, str):
                return tp
            
            origin = get_origin(tp)
            if origin is None:
                return getattr(tp, "__name__", repr(tp))
            
            args = get_args(tp)
            origin_name = getattr(origin, "__name__", str(origin).replace("typing.", ""))
            
            if origin_name in ("Union", "types.UnionType"):
                parts = [AliveMemory._type_repr(a) for a in args]
                return " | ".join(parts)
            
            parts = [AliveMemory._type_repr(a) for a in args]
            return f"{origin_name}[{', '.join(parts)}]"
        except Exception:
            return "UNKNOWN"


# ----------------------------
# AliveField (descriptor)
# ----------------------------
class AliveField(Generic[T]):
    def __init__(self, default: T, description: str = ""):
        self.default = default
        self.description = description
        self.name: str | None = None
    
    def __set_name__(self, owner, name: str) -> None:
        self.name = name
    
    def __get__(self, instance, owner):
        if instance is None:
            return self
        
        name = self.name
        if not name:
            raise RuntimeError("AliveField missing __set_name__ binding")
        
        mem = instance._alive_memory.get(name)
        if mem is None:
            mem = AliveMemory[T](value=self.default, description=self.description)
            instance._alive_memory[name] = mem
        return mem.value
    
    def __set__(self, instance, value: T) -> None:
        name = self.name
        if not name:
            raise RuntimeError("AliveField missing __set_name__ binding")
        
        mem = instance._alive_memory.get(name)
        if mem is None:
            instance._alive_memory[name] = AliveMemory[T](value=value, description=self.description)
        else:
            # keep existing metadata, update only value
            mem.value = value