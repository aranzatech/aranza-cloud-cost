from __future__ import annotations

from datetime import date
from decimal import Decimal

from ..config import CloudCostConfig
from ..models import CostSnapshot, ProviderName
from .base import CostProvider, ProviderError


class GcpCostProvider(CostProvider):
    name = ProviderName.GCP

    def __init__(self, config: CloudCostConfig) -> None:
        self.config = config

    def fetch_month_to_date_cost(self) -> CostSnapshot:
        try:
            from google.cloud import bigquery
        except ImportError as exc:
            raise ProviderError("google-cloud-bigquery is missing. Reinstall aranza-cloud-costs.") from exc

        assert self.config.gcp_billing_export_table
        today = date.today()
        period_start = today.replace(day=1)
        query = f"""
            SELECT
              COALESCE(SUM(cost + IFNULL((SELECT SUM(credit.amount) FROM UNNEST(credits) credit), 0)), 0)
                AS total_cost,
              ANY_VALUE(currency) AS currency
            FROM `{self.config.gcp_billing_export_table}`
            WHERE DATE(usage_start_time) >= @period_start
              AND DATE(usage_start_time) <= @period_end
        """
        try:
            client = bigquery.Client()
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("period_start", "DATE", period_start),
                    bigquery.ScalarQueryParameter("period_end", "DATE", today),
                ]
            )
            row = next(iter(client.query(query, job_config=job_config).result()))
            return CostSnapshot(
                provider=self.name,
                amount=Decimal(str(row.total_cost)),
                currency=str(row.currency or self.config.currency),
                period_start=period_start,
                period_end=today,
                source="GCP Cloud Billing export in BigQuery (cost net of credits)",
            )
        except Exception as exc:  # BigQuery's exception hierarchy is optional at import time.
            raise ProviderError(f"GCP BigQuery billing query failed: {exc}") from exc
