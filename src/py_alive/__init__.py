from .alive import BaseAlive
from .agent_decorator import alive_agent
from .tools_registry import alive_tool, AliveTag
from .memory import AliveMemory, AliveField


def main() -> None:
    print("Hello from py-alive!")
