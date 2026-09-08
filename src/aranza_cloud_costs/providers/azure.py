from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..config import CloudCostConfig
from ..models import CostSnapshot, ProviderName
from .base import CostProvider, ProviderError


class AzureCostProvider(CostProvider):
    name = ProviderName.AZURE

    def __init__(self, config: CloudCostConfig) -> None:
        self.config = config

    def fetch_month_to_date_cost(self) -> CostSnapshot:
        try:
            from azure.identity import DefaultAzureCredential
        except ImportError as exc:
            raise ProviderError("Azure support requires: pip install 'aranza-cloud-costs[azure]'.") from exc

        assert self.config.azure_subscription_id
        today = date.today()
        payload = {
            "type": "Usage",
            "timeframe": "MonthToDate",
            "dataset": {
                "granularity": "None",
                "aggregation": {"totalCost": {"name": "PreTaxCost", "function": "Sum"}},
            },
        }
        try:
            token = DefaultAzureCredential().get_token("https://management.azure.com/.default").token
            url = (
                "https://management.azure.com/subscriptions/"
                f"{self.config.azure_subscription_id}/providers/Microsoft.CostManagement/query"
                "?api-version=2023-11-01"
            )
            request = Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=30) as response:  # nosec B310 - URL is a fixed Azure API.
                if response.status == 204:
                    return CostSnapshot(
                        provider=self.name,
                        amount=Decimal("0"),
                        currency=self.config.currency,
                        period_start=today.replace(day=1),
                        period_end=today,
                        source="Azure Cost Management / PreTaxCost",
                    )
                data = json.load(response)
            columns = data["properties"]["columns"]
            row = data["properties"]["rows"][0]
            values = {column["name"]: row[index] for index, column in enumerate(columns)}
            return CostSnapshot(
                provider=self.name,
                amount=Decimal(str(values["PreTaxCost"])),
                currency=str(values.get("Currency", self.config.currency)),
                period_start=today.replace(day=1),
                period_end=today,
                source="Azure Cost Management / PreTaxCost",
            )
        except (HTTPError, URLError, KeyError, IndexError, ValueError) as exc:
            raise ProviderError(f"Azure Cost Management request failed: {exc}") from exc
