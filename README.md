# aranza-cloud-costs

`aranza-cloud-costs` is a Python library for retrieving month-to-date cloud spend, evaluating per-provider or global budgets, and sending threshold alerts to Slack and Telegram. AWS, Azure, GCP, and Cloudflare results share one normalized report.

The library does not run a worker on its own. Call it from your backend, a cron job, GitHub Actions, a Kubernetes CronJob, or your preferred scheduler. That keeps the package stateless and does not impose additional infrastructure.

## Installation

Install the package once. It includes the AWS, Azure, and GCP adapters; the configuration determines which providers are queried.

Until the package is published on PyPI, install it directly from GitHub:

```bash
pip install git+https://github.com/aranzatech/aranza-cloud-cost.git
```

After publishing the package on PyPI, the command becomes:

```bash
pip install aranza-cloud-costs
```

For local development:

```bash
cd AranzaTech/aranza-cloud-costs
python3 -m pip install -e ".[dev]"
```

## Configuration

Configuration is intentionally split into two files:

- [`config/cloud-costs.toml`](config/cloud-costs.example.toml) contains non-sensitive settings: providers, budgets, thresholds, account identifiers, and enabled notification targets. It is safe to version.
- [`.env`](.env.example) contains the TOML path and secrets. Do not commit it.

```bash
cp config/cloud-costs.example.toml config/cloud-costs.toml
cp .env.example .env
set -a; source .env; set +a
aranza-cloud-costs check
```

```toml
# config/cloud-costs.toml
[monitor]
providers = ["aws", "azure", "gcp"]
currency = "USD"
thresholds = [0.80, 0.90, 1.00]

[budgets]
global = 1000
aws = 300

[notifications]
slack = true
telegram = false
```

```dotenv
# .env
ARANZA_CLOUD_CONFIG_FILE=config/cloud-costs.toml
ARANZA_CLOUD_SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

Any non-empty `ARANZA_CLOUD_*` environment variable overrides the equivalent TOML option. For example, `ARANZA_CLOUD_BUDGET=500` overrides `budgets.global` for one deployment without duplicating the configuration file.

See [the full configuration reference](docs/CONFIGURATION.md) for every TOML option, environment variable, credential requirement, default, and validation rule.

## Python usage

The application code is the same for any supported cloud. Its configuration selects the provider adapter.

```python
from aranza_cloud_costs import CloudCostMonitor

report = CloudCostMonitor.from_env().check()

for snapshot in report.snapshots:
    print(f"{snapshot.provider.value}: {snapshot.amount} {snapshot.currency}")

for alert in report.alerts:
    print(f"{alert.provider.value}: {alert.utilization:.1%} of budget")

if report.errors:
    print(report.errors)
```

`check()` continues when one provider fails: successful data remains in `report.snapshots`, while failures are recorded in `report.errors`.

## Provider examples

### GCP Billing export to BigQuery

Configure Application Default Credentials. In production, prefer Workload Identity; locally, `GOOGLE_APPLICATION_CREDENTIALS` can point to a service-account JSON file outside the repository.

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/secure/path/gcp-billing-reader.json
```

```toml
# config/cloud-costs.toml
[monitor]
providers = ["gcp"]
thresholds = [0.80, 1.00]

[budgets]
gcp = 500

[gcp]
billing_export_table = "my-project.billing.gcp_billing_export_v1_XXXXXX"

[notifications]
slack = false
telegram = false
```

```python
from aranza_cloud_costs import CloudCostMonitor

report = CloudCostMonitor.from_env().check(notify=False)
gcp_cost = report.snapshots[0]
print(f"GCP month-to-date: {gcp_cost.amount} {gcp_cost.currency}")
```

GCP requires Cloud Billing export to BigQuery and read access to that table. The query returns cost net of credits reported in the export; cloud billing data can have provider-side reporting delay.

### Azure Cost Management

`DefaultAzureCredential` resolves managed identity, workload identity, Azure CLI credentials, or service-principal environment variables in its standard order.

```bash
export AZURE_TENANT_ID=<tenant-id>
export AZURE_CLIENT_ID=<client-id>
export AZURE_CLIENT_SECRET=<client-secret>
```

```toml
# config/cloud-costs.toml
[monitor]
providers = ["azure"]
thresholds = [0.80, 1.00]

[budgets]
azure = 400

[azure]
subscription_id = "00000000-0000-0000-0000-000000000000"

[notifications]
slack = false
telegram = false
```

```python
from aranza_cloud_costs import CloudCostMonitor

report = CloudCostMonitor.from_env().check(notify=False)
azure_cost = report.snapshots[0]
print(f"Azure month-to-date: {azure_cost.amount} {azure_cost.currency}")
```

The configured identity needs permission to query Cost Management at the subscription scope.

### AWS Cost Explorer

The boto3 credential chain is used, so a workload IAM role is preferred; local development can use a named AWS profile.

```bash
export AWS_PROFILE=cost-reader
```

```toml
# config/cloud-costs.toml
[monitor]
providers = ["aws"]
thresholds = [0.80, 1.00]

[budgets]
aws = 300

[aws]
region = "us-east-1"

[notifications]
slack = false
telegram = false
```

```python
from aranza_cloud_costs import CloudCostMonitor

report = CloudCostMonitor.from_env().check(notify=False)
aws_cost = report.snapshots[0]
print(f"AWS month-to-date: {aws_cost.amount} {aws_cost.currency}")
```

AWS Cost Explorer must be enabled, and the identity needs `ce:GetCostAndUsage`.

## Command-line usage

```bash
aranza-cloud-costs check
aranza-cloud-costs check --no-notify
```

The command prints JSON and returns exit code `1` when it cannot obtain a selected provider or deliver a notification. A daily cron invocation might look like this:

```cron
0 9 * * * /path/to/venv/bin/aranza-cloud-costs check
```

## Provider support

| Provider | Month-to-date cost source | Requirement |
| --- | --- | --- |
| AWS | Cost Explorer `UnblendedCost` | Enable Cost Explorer and grant `ce:GetCostAndUsage` |
| Azure | Cost Management Query `PreTaxCost` | Azure identity with Cost Management access |
| GCP | Cloud Billing export in BigQuery, net of credits | Enable export and grant BigQuery read access |
| Cloudflare | An external collector value | Set `cloudflare.month_to_date_cost` |

Cloudflare currently exposes Alpha, deprecated, or restricted billable-usage endpoints rather than a stable general equivalent of Cost Explorer or Cost Management. To avoid misleading alerts, its adapter only accepts a month-to-date amount already calculated by your own usage or invoice collector.

## Notifications

Set `notifications.slack = true` and provide the `ARANZA_CLOUD_SLACK_WEBHOOK_URL` secret for Slack. For Telegram, set `notifications.telegram = true`, define `notifications.telegram_chat_id` in TOML, and provide the `ARANZA_CLOUD_TELEGRAM_BOT_TOKEN` secret. Both targets can be enabled.

An alert is emitted for every configured threshold reached by a provider. Threshold deduplication across separate executions is intentionally left to the calling application or scheduler storage, keeping the core library serverless-friendly.

## Integration references

- [AWS Cost Explorer: GetCostAndUsage](https://docs.aws.amazon.com/cli/latest/reference/ce/get-cost-and-usage.html)
- [Azure Cost Management: Query Usage](https://learn.microsoft.com/en-us/rest/api/cost-management/query/usage?view=rest-cost-management-2025-03-01)
- [Export Cloud Billing data to BigQuery](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-setup)
- [Cloudflare Billing API](https://developers.cloudflare.com/api/resources/billing/)

## Development

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```
