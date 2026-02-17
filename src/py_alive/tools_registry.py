from __future__ import annotations

from collections.abc import Callable as ABCCallable
from dataclasses import dataclass

import inspect
from typing import Any, Awaitable, Callable, get_type_hints, Literal

from pydantic import BaseModel, ConfigDict
from pydantic_ai import Agent, RunContext, FunctionToolset, AbstractToolset
from pydantic_ai.mcp import MCPServerStreamableHTTP

from .internal import BaseList
from .utils import _is_dunder, _safe_getattr, _shallow_size_kb, _type_repr, is_alive_agent_method, extract_angle_doc
from typing import Callable, Iterable, Optional, Union

from typing import Callable, Iterable


class AliveTag:
    def __init__(self, value: str):
        self.value = value
    
    def __str__(self):
        return self.value
    
    def __repr__(self):
        return f"AliveTag({self.value!r})"
    
    def __hash__(self):
        return hash(self.value)
    
    def __eq__(self, other):
        if isinstance(other, AliveTag):
            return self.value == other.value
        if isinstance(other, str):
            return self.value == other
        return False


Tag = AliveTag | str
TagsInput = set[Tag] | list[Tag] | Tag | None


def _normalize_tags(tags: TagsInput) -> set[AliveTag]:
    if tags is None:
        return set()
    
    # single tag
    if isinstance(tags, (str, AliveTag)):
        return {tags if isinstance(tags, AliveTag) else AliveTag(tags)}
    
    # iterable of tags
    out: set[AliveTag] = set()
    for t in tags:
        if isinstance(t, AliveTag):
            out.add(t)
        elif isinstance(t, str):
            out.add(AliveTag(t))
        else:
            raise TypeError(f"Tag must be AliveTag or str, got {type(t).__name__}")
    return out


def alive_tool(
        func: Callable | None = None,
        *,
        tags: TagsInput = None,
        exclude: bool = False,
        name: str | None = None,
        name_prefix: str | None = None,
):
    normalized_tags = _normalize_tags(tags)
    # print(f"@alive_tool: reminder! -> name and name_prefix are not implemented yet!")
    
    def deco(f: Callable):
        # --- tags ---
        current_tags = set(getattr(f, "_alive_agent_tags__", set()))
        current_tags.update(normalized_tags)
        f._alive_agent_tags__ = current_tags
        
        # --- name prefix (string) ---
        current_prefix = getattr(f, "_alive_agent_name_prefix__", "")
        if name_prefix:
            # prepend new prefix (so newest decorator appears first)
            current_prefix = f"{name_prefix}_{current_prefix}" if current_prefix else f"{name_prefix}_"
        f._alive_agent_name_prefix__ = current_prefix
        
        # --- name (string) ---
        current_name = getattr(f, "_alive_agent_name__", None)
        final_name = name or current_name or f.__name__
        f._alive_agent_name__ = final_name
        
        return f
    
    # Support both @alive_tool and @alive_tool(...)
    return deco(func) if func is not None else deco


##############


class ToolConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    func: ABCCallable | Any
    doc: str
    name: str
    name_prefix: str = ""


def build_registry(class_instance):
    tools: BaseList[ToolConfig] = BaseList[ToolConfig]([])
    
    for name in sorted(dir(class_instance)):
        if _is_dunder(name):
            continue
        
        member = _safe_getattr(class_instance, name)
        if isinstance(member, Exception) or not callable(member):
            continue
        func = member if not getattr(member, "__func__", None) else member.__func__
        func._alive_agent_tags__ = getattr(func, "_alive_agent_tags__", set())
        
        doc = extract_angle_doc(inspect.getdoc(member)) or ""
        
        tools.append(ToolConfig(func=member, doc=doc, name=name))
    
    return tools


class ToolsRegistry:
    
    def __init__(self, class_instance):
        self.tools_registry: BaseList[ToolConfig] = build_registry(class_instance=class_instance)
    
    def export_toolsets(
            self,
            include: list[str | AliveTag | Callable] | None = None,
            exclude: list[str | AliveTag] | None = None,
            calling_method_name: str | None = None,
            actual_tools: list[MCPServerStreamableHTTP | Any] | None = None,
    ) -> list[FunctionToolset | AbstractToolset]:
        tools_config = self.get_tools_config(include, exclude, calling_method_name)
        
        # ---- build toolset ----
        toolset = FunctionToolset(tools=[])
        
        # registry tools in registry order
        for t in tools_config:
            toolset.add_function(func=t.func, description=t.doc)
        
        # print(f"{toolset.tools=}")
        
        ########## final ###########
        
        toolsets = []
        toolsets.append(toolset)
        
        for m in actual_tools or []:
            toolsets.append(m)
        
        return toolsets
    
    def get_tools_config(
            self,
            include: list[str | AliveTag | Callable] | None = None,
            exclude: list[str | AliveTag] | None = None,
            calling_method_name: str | None = None,
    ) -> list[ToolConfig]:
        """
        Semantics:
        - "*" is a fallback (weak):
          - include=["*"], exclude=[...] => include all EXCEPT excluded
          - exclude=["*"], include=[...] => exclude all EXCEPT included (include wins over "*")
        - Precedence:
          - explicit name exclude always excludes (even if tag included or name included)
          - tag-based exclude excludes unless explicitly name-included
          - explicit name include can override tag-exclude
        - Calling method rule:
          - calling_method_name is NOT callable unless explicitly included by NAME
            (i.e., include contains the string calling_method_name). "*" does not count. Tags do not count.
        """
        include_raw = include or ["*"]
        exclude_raw = list(exclude or [])
        
        # ---- helpers ----
        def _tool_tags(tool) -> set[AliveTag]:
            tags = getattr(tool.func, "_alive_agent_tags__", set())
            if tags is None:
                return set()
            if isinstance(tags, AliveTag):
                return {tags}
            return set(tags)
        
        all_names: set[str] = {t.name for t in self.tools_registry}
        
        # ---- split by type ----
        include_funcs: set[ABCCallable] = {x for x in include_raw if isinstance(x, ABCCallable)}
        include_strs: set[str] = {x for x in include_raw if isinstance(x, str)}
        include_tags: set[AliveTag] = {x for x in include_raw if isinstance(x, AliveTag)}
        
        exclude_strs: set[str] = {x for x in exclude_raw if isinstance(x, str)}
        exclude_tags: set[AliveTag] = {x for x in exclude_raw if isinstance(x, AliveTag)}
        
        include_has_star = "*" in include_strs
        exclude_has_star = "*" in exclude_strs
        
        explicit_include_names: set[str] = {s for s in include_strs if s != "*"}
        explicit_exclude_names: set[str] = {s for s in exclude_strs if s != "*"}
        
        # ---- expand "*" (weak semantics) ----
        if include_has_star:
            include_strs = (include_strs - {"*"}) | all_names
        if exclude_has_star:
            exclude_strs = (exclude_strs - {"*"}) | all_names
        
        # ---- resolve tags -> names ----
        include_by_tag: set[str] = set()
        if include_tags:
            for t in self.tools_registry:
                if _tool_tags(t) & include_tags:
                    include_by_tag.add(t.name)
        
        exclude_by_tag: set[str] = set()
        if exclude_tags:
            for t in self.tools_registry:
                if _tool_tags(t) & exclude_tags:
                    exclude_by_tag.add(t.name)
        
        include_set: set[str] = (include_strs | include_by_tag) & all_names
        
        # ---- compute final names with precedence ----
        # If exclude=["*"], start with only explicitly included items
        # Otherwise, start with all included items and apply excludes
        if exclude_has_star:
            # exclude=["*"] => only explicitly included items survive
            candidates = explicit_include_names | include_by_tag
        else:
            # Normal case: include all matched, then apply excludes
            candidates = include_set
        
        final_names: set[str] = set()
        for name in candidates:
            # 1) explicit name-exclude always wins
            if name in explicit_exclude_names:
                continue
            # 2) tag-exclude blocks unless explicitly name-included
            if (name in exclude_by_tag) and (name not in explicit_include_names):
                continue
            
            final_names.add(name)
        
        # ---- calling method rule (name-only explicit allow; "*" and tags do NOT allow) ----
        if calling_method_name and calling_method_name not in explicit_include_names:
            final_names.discard(calling_method_name)
        
        # print(f"toolsets: [{final_names=}]")
        
        tools_configs = self.tools_registry.where(lambda x: x.name in final_names)
        
        for fn in set(include_funcs):
            tools_configs.append(ToolConfig(func=fn, name=fn.__name__, doc=fn.__doc__))
        
        return tools_configs


