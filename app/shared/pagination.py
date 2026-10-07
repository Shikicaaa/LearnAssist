from dataclasses import dataclass

from fastapi import Query
from pydantic import BaseModel


@dataclass
class PageParams:
    limit: int = Query(10, ge=1, le=50)
    offset: int = Query(0, ge=0)


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int
