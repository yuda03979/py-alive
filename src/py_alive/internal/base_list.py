from __future__ import annotations

from typing import Any, Generic, Iterable, TypeVar, get_args
from pydantic import BaseModel, GetCoreSchemaHandler
from pydantic_core import core_schema
from typing import Generic, TypeVar, Iterable, Callable, Optional
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class BaseList(list[T], Generic[T]):
    """
    List with functional, strict-by-default filtering.
    """
    
    def __init__(self, items: Iterable[T] = ()):
        super().__init__(items)
    
    @classmethod
    def __get_pydantic_core_schema__(
            cls,
            source_type: Any,
            handler: GetCoreSchemaHandler,
    ) -> core_schema.CoreSchema:
        # BaseList[StateDto] -> args = (StateDto,)
        (item_type,) = get_args(source_type) or (Any,)
        item_schema = handler.generate_schema(item_type)
        
        list_schema = core_schema.list_schema(item_schema)
        
        # Convert validated list -> BaseList
        return core_schema.no_info_after_validator_function(
            lambda v: cls(v),
            list_schema,
        )
    
    def where(
            self,
            predicate: Callable[[T], bool],
            *,
            strict: bool = True,
    ) -> BaseList[T]:
        """
        Filter items using a lambda / predicate.

        strict=True  -> any exception inside predicate is raised
        strict=False -> exceptions cause the item to be skipped
        """
        
        def safe(item: T) -> bool:
            try:
                return bool(predicate(item))
            except Exception:
                if strict:
                    raise
                return False
        
        return self.__class__(item for item in self if safe(item))
    
    def first(
            self,
            predicate: Callable[[T], bool],
            *,
            strict: bool = True,
    ) -> Optional[T]:
        for item in self:
            try:
                if predicate(item):
                    return item
            except Exception:
                if strict:
                    raise
        return None
    
    def require(
            self,
            predicate: Callable[[T], bool],
            *,
            strict: bool = True,
    ) -> T:
        item = self.first(predicate, strict=strict)
        if item is None:
            raise KeyError(f"{self.__class__.__name__}: no item matched predicate")
        return item
    
    # -----------
    
    def selected_fields(self, field_keys: set[str]) -> list[dict[str, Any]]:
        """Return dict for each model, with only the selected fields."""
        return [
            item.model_dump(include=field_keys)
            for item in self
        ]
        
