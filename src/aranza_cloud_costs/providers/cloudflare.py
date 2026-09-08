from __future__ import annotations

from datetime import date

from ..config import CloudCostConfig
from ..models import CostSnapshot, ProviderName
from .base import CostProvider


class CloudflareCostProvider(CostProvider):
    """Uses an externally collected amount until Cloudflare exposes a usable MTD cost API."""

    name = ProviderName.CLOUDFLARE

    def __init__(self, config: CloudCostConfig) -> None:
        self.config = config

    def fetch_month_to_date_cost(self) -> CostSnapshot:
        assert self.config.cloudflare_month_to_date_cost is not None
        today = date.today()
        return CostSnapshot(
            provider=self.name,
            amount=self.config.cloudflare_month_to_date_cost,
            currency=self.config.cloudflare_currency,
            period_start=today.replace(day=1),
            period_end=today,
            source="Cloudflare external month-to-date collector",
        )
