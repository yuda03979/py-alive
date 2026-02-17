import asyncio
import inspect
from functools import wraps
from typing import get_type_hints, Callable

from pydantic import BaseModel
from pydantic_ai import Agent, FunctionToolset, UserContent, CachePoint
from pydantic_ai.mcp import MCPServerStreamableHTTP
from pydantic_ai.messages import MULTI_MODAL_CONTENT_TYPES

from pydantic_ai import models
from collections.abc import Sequence
from typing import Any
from typing import get_type_hints, get_origin, get_args
from dataclasses import dataclass
from collections.abc import Callable as ABCCallable


from .tools_registry import alive_tool, AliveTag
from .utils import extract_no_angle_doc


@dataclass
class AliveAgentParams:
    llm: list[models.Model | str] | models.Model | str
    """pydantic-ai llm model"""
    instance: Any
    """the actual instance"""
    func: Any
    """agent config"""
    include: list | None = None
    """methods to include"""
    exclude: Any = None
    """methods to exclude"""
    actual_tools: Any = None
    """ready pydantic-ai toolset / tools"""
    toolsets: list | None = None
    parallel_run: bool = False
    # deps: None = None


class AliveAgentRun:
    
    def __init__(self, params: AliveAgentParams):
        self.params = params
    
    async def run_agent_async(self, *args, **kwargs):
        user_prompt = self.normalize_to_user_content(args=args, kwargs=kwargs)
        output_type, prompt = self.parse_agent_func()
        toolsets: list = self.params.instance._alive_agent_registry__.export_toolsets(self.params.include, self.params.exclude, self.params.func.__name__, self.params.actual_tools)
        agent = Agent(
            self.params.llm,
            system_prompt=prompt,
            output_type=output_type,
            toolsets=toolsets,
        )
        response = await agent.run(user_prompt=user_prompt)
        return response.output
    
    @staticmethod
    def normalize_to_user_content(
            args: tuple[Any, ...],
            kwargs: dict[str, Any],
    ) -> Sequence[UserContent]:
        def is_user_content(value: Any) -> bool:
            return isinstance(value, (str, CachePoint, *MULTI_MODAL_CONTENT_TYPES))
        
        result: list[UserContent] = []
        
        # ---- positional args ----
        for arg in args:
            if arg is None:
                continue
            
            if is_user_content(arg):
                result.append(arg)
            
            elif isinstance(arg, Sequence) and not isinstance(arg, (str, bytes)):
                for item in arg:
                    if is_user_content(item):
                        result.append(item)
                    else:
                        result.append(str(item))
            else:
                result.append(str(arg))
        
        # ---- keyword args ----
        for key, value in kwargs.items():
            if value is None:
                continue
            
            if is_user_content(value):
                result.append(value)
            else:
                # 👇 תמיד כיחידה אחת
                result.append(f"{key}={value}")
        
        if not result:
            result.append("follow the instructions")
        return result
    
    def parse_agent_func(self):
        hints = get_type_hints(self.params.func)
        declared_return = hints.get("return")
        
        if declared_return is None:
            raise TypeError(f"{self.params.func.__name__} must define a return type")
        
        output_type = declared_return
        
        if self.params.parallel_run:
            origin = get_origin(declared_return)
            args = get_args(declared_return)
            
            # supports: list[T] (and optionally List[T] depending on evaluation)
            if origin is not list or len(args) != 1:
                raise TypeError(
                    f"agent '{self.params.func.__name__}' must declare return type as list[T] when parallel_run=True, got: {declared_return!r}"
                )
            
            output_type = args[0]  # T (what the function actually returns)
        
        prompt = extract_no_angle_doc(self.params.func.__doc__)
        return output_type, prompt
    

################
# simple helpers
################


async def alive_agent_run_one(instance, func, llm, include, exclude, actual_tools, parallel_run: bool, *args, **kwargs):
    params = AliveAgentParams(
        instance=instance,
        func=func,
        llm=llm,
        include=include,
        exclude=exclude,
        actual_tools=actual_tools,
        parallel_run=parallel_run,
    )
    run = AliveAgentRun(params)
    output = await run.run_agent_async(*args, **kwargs)
    return output


async def alive_agent_run(instance, func, llms, include, exclude, actual_tools, *args, **kwargs):
    llms = llms if isinstance(llms, list) else [llms]
    parallel_run = len(llms) > 1
    # single -> keep old behavior (return single result)
    if len(llms) == 1:
        return await alive_agent_run_one(instance, func, llms[0], include, exclude, actual_tools, parallel_run, *args, **kwargs)
    # multi -> run concurrently, return list of results in same order as llms
    else:
        tasks = [
            alive_agent_run_one(instance, func, model, include, exclude, actual_tools, parallel_run, *args, **kwargs)
            for model in llms
        ]
        return await asyncio.gather(*tasks)


###############


def alive_agent(llms: list[models.Model | str] | models.Model | str, include: list[str | AliveTag | ABCCallable] | None = None, exclude: list[str | AliveTag] | None = None, actual_tools: list[MCPServerStreamableHTTP | Any] | None = None):
    """
    llm: pydantic-supported llm
    include / exclude:
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
    mcps: list of urls / mcp schema / MCPServerStreamableHTTP.
    """
    
    def decorator(func):
        if inspect.iscoroutinefunction(func):
            @alive_tool(tags=AliveTag("agent"))
            @wraps(func)
            async def async_wrapper(self, *args, **kwargs):
                return await alive_agent_run(self, func, llms, include, exclude, actual_tools, *args, **kwargs)
            
            async_wrapper.__is_alive_agent__ = True
            async_wrapper.__alive_agent_llm__ = llms
            return async_wrapper
        
        else:
            raise f"ERROR {func.__name__}: alive agents must be async"
        
    return decorator

        