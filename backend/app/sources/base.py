from abc import ABC, abstractmethod
from typing import List

from backend.app.models import SourceDoc


class SourceProvider(ABC):
    @abstractmethod
    async def search(self, query: str, limit: int) -> List[SourceDoc]:
        raise NotImplementedError
