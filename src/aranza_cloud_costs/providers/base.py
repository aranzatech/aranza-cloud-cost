from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import CostSnapshot, ProviderName


class ProviderError(RuntimeError):
    """Raised when a provider cannot supply a cost snapshot."""


class CostProvider(ABC):
    name: ProviderName

    @abstractmethod
    def fetch_month_to_date_cost(self) -> CostSnapshot:
        """Return the current calendar month's cost in the billing currency."""
