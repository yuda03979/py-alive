from typing import Any

from .memory import AliveMemory
from .tools_registry import ToolsRegistry, alive_tool, AliveTag


class BaseAlive:
    
    def __init__(self):
        self._alive_agent_registry__ = ToolsRegistry(self)
        self._alive_memory: dict[str, AliveMemory[Any]] = {}
    
    ########################################
    
    @alive_tool(tags=AliveTag("memory"))
    async def read_memory(self, name: str) -> str:
        """
        Read ONE memory value (single memory).
        - If memory is an AliveField: returns its value
        - Otherwise: getattr fallback (normal memorys)
        """
        if name in self._alive_memory:
            val = self._alive_memory[name].value
        else:
            val = getattr(self, name)
        return str(val)
    
    @alive_tool(tags=AliveTag("memory"))
    async def get_memories_overview(self) -> list[dict[str, str]]:
        """
        Overview of Alive memories (AliveField-backed attributes).
        Returns list items: {"name","type","hint","size_kb","description","preview"}
        """
        out: list[dict[str, str]] = []
        for name in sorted(self._alive_memory.keys()):
            mem = self._alive_memory[name]
            out.append(
                {
                    "name": str(name),
                    "type": str(mem.type_name),
                    "hint": str(mem.hint),
                    "size_kb": str(mem.size_kb),
                    "description": str(mem.description),
                    "preview": str(mem.preview),
                }
            )
        return out
    