from pydantic import BaseModel, ConfigDict


class BaseModelAlive(BaseModel):
    """"""
    model_config = ConfigDict(use_attribute_docstrings=True)
