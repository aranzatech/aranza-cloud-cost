from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from ..config import CloudCostConfig
from ..models import CostSnapshot, ProviderName
from .base import CostProvider, ProviderError


class AwsCostProvider(CostProvider):
    name = ProviderName.AWS

    def __init__(self, config: CloudCostConfig) -> None:
        self.config = config

    def fetch_month_to_date_cost(self) -> CostSnapshot:
        try:
            import boto3
        except ImportError as exc:
            raise ProviderError("AWS support requires: pip install 'aranza-cloud-costs[aws]'.") from exc

        today = date.today()
        period_start = today.replace(day=1)
        period_end = today + timedelta(days=1)  # AWS Cost Explorer's end date is exclusive.
        try:
            response = boto3.client("ce", region_name=self.config.aws_region).get_cost_and_usage(
                TimePeriod={"Start": period_start.isoformat(), "End": period_end.isoformat()},
                Granularity="MONTHLY",
                Metrics=["UnblendedCost"],
            )
            amount = response["ResultsByTime"][0]["Total"]["UnblendedCost"]
            return CostSnapshot(
                provider=self.name,
                amount=Decimal(amount["Amount"]),
                currency=amount["Unit"],
                period_start=period_start,
                period_end=today,
                source="AWS Cost Explorer / UnblendedCost",
            )
        except Exception as exc:  # SDK exposes many service-specific exception classes.
            raise ProviderError(f"AWS Cost Explorer request failed: {exc}") from exc
