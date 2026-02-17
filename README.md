# PyAlive

Experimental runtime aware framework for Python.

⚠️ Early development version. API may change.


> Your Python class is the agent.

```python
from py_alive import BaseAlive, AliveTag, AliveField, alive_agent, alive_tool
import asyncio
from pydantic_ai import AudioUrl
from pydantic_ai.models.test import TestModel


class Translator(BaseAlive):
    """"""
    text: str = AliveField(default="", description="the text to translate")  # this is for the agents. for you its just normal str!
    
    def __init__(self, text: str):
        super().__init__()
        self.text = text
    
    @alive_agent(llms=TestModel(), exclude=["*"]) #include=[AliveTag("memory")]) <- this will cause error in TestModel(). it will call it with memory 'a' - which not exist
    async def translate(self, specific_instruction: str) -> str:
        """translate memory text to hebrew"""
    
    async def some_func(self) -> str:
        self.text += "its a nice day today. do you know that?"
        if len(self.text) > 100:
            return "oy vey"
        else:
            return await self.translate(specific_instruction="also translate it to arabic")
    
    @alive_agent(llms=TestModel(), exclude=['*'])
    async def transcribe_audio(self, url: AudioUrl) -> str:
        """transcript"""



print(asyncio.run(Translator("hello world").translate()))
print(asyncio.run(Translator("hello world").some_func()))
print(asyncio.run(Translator("hello world").transcribe_audio(url=AudioUrl(url=""))))
```

---

## install

```bash
uv add py-alive
```

---

## concepts

**`AliveField`** — the agent's memory. described, typed, visible to agents.  # memory cannot be modified now!
```python
name: str = AliveField[str](default="", description="the customer's name")
```

**`@alive_agent`** — turns a method into an agent. docstring is the prompt.
```python
@alive_agent(llm="openai:gpt-4o")
async def summarize(self) -> str:
    """return a 2 sentence summary of memory content"""
```

**`<tool description>`** — wrap part of the docstring to expose the method as a tool to other agents.
```python
async def clean(self) -> str:
    """<cleans and normalizes memory 'text'>
    remove punctuation, lowercase, strip whitespace
    """
```

**`AliveTag`** — group fields or methods, control agent visibility.
```python
# @AliveTag("memory") -> coming soon for memories. for now all memories are under include/exclude=[AliveTag("memory")] 
name: str = AliveField[str](...)

@alive_agent(llm="openai:gpt-4o", include=[AliveTag("memory")])
async def greet(self) -> None: ...
```

---

## multiple LLMs → list back

```python
@alive_agent(llm=["openai:gpt-4o", "anthropic:claude-sonnet-4-5"])
async def translate(self) -> list[str]:
    """translate memory 'text' to hebrew"""
```

---

##

- llms are pydantic-ai models. simple usage: [pydantic-ai models](https://ai.pydantic.dev/api/models/base/)
- don't forget to add your env vars,

```python
OPENAI_API_KEY=""
ANTHROPIC_API_KEY=""
GEMINI_API_KEY=""
```
etc..
(only what you use)


## coming soon

```python
t.auto(task="...", include/exclude=[...])  # autonomous agent over all tools
t.export_as_mcp(port=8000)         # instant MCP server
t.graph                            # visualize agent call graph
```

---

built on [pydantic-ai](https://github.com/pydantic/pydantic-ai)
````