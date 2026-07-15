"""Abstract base for all ingestion source adapters."""
from abc import ABC, abstractmethod
from typing import Any


class SourceAdapter(ABC):
    """Contract every source adapter must satisfy.

    - `provider_name`: identifier stored in api_responses.provider or county_parcels.county
    - `fetch(**params)`: raw API call, may consume budget
    - `normalize(raw)`: transform raw response into rows for the normalized layer
    """

    provider_name: str

    @abstractmethod
    async def fetch(self, **params: Any) -> dict[str, Any]:
        """Fetch raw data from the source. Implementations should use budget.get_or_fetch."""

    @abstractmethod
    async def normalize(self, raw: dict[str, Any]) -> list[dict[str, Any]]:
        """Transform raw response into normalized rows suitable for upsert."""
