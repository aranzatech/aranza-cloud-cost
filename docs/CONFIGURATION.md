# Configuration reference

`aranza-cloud-costs` deliberately keeps credentials out of its TOML file. Store policy and operational settings in `config/cloud-costs.toml`, and provide only secrets through the deployment environment or its secret manager.

Resolution order for every supported non-secret option is:

1. A non-empty `ARANZA_CLOUD_*` environment variable.
2. The equivalent setting in `cloud-costs.toml`.
3. The documented default, if one exists.

Secrets are accepted from environment variables only. TOML sections and options are validated strictly, including unsupported secret-looking fields, so a typo cannot silently disable monitoring. Keep unrelated application metadata in a different file.

## Quick setup

```bash
cp config/cloud-costs.example.toml config/cloud-costs.toml
cp .env.example .env
set -a; source .env; set +a
aranza-cloud-costs check
```

Never commit `.env`, a service-account JSON file, tokens, webhooks or access keys. The provided `.gitignore` already excludes `.env`; add your chosen credential-file path too if it is inside the repository.

## TOML file: non-secret settings

| TOML option | Required | Description |
| --- | --- | --- |
| `monitor.providers` | Yes | Array with one or more of `aws`, `azure`, `gcp`, `cloudflare`. |
| `monitor.currency` | No | Fallback currency for providers that omit it. Default: `USD`. |
| `monitor.thresholds` | No | Decimal fractions that trigger alerts, for example `[0.8, 1.0]`. Default: `[0.8, 1.0]`. |
| `budgets.global` | No | Default monthly budget for any provider without its own budget. |
| `budgets.aws` | No | AWS monthly budget; takes precedence over `budgets.global`. |
| `budgets.azure` | No | Azure monthly budget; takes precedence over `budgets.global`. |
| `budgets.gcp` | No | GCP monthly budget; takes precedence over `budgets.global`. |
| `budgets.cloudflare` | No | Cloudflare monthly budget; takes precedence over `budgets.global`. |
| `aws.region` | No | Region for the AWS Cost Explorer client. Default: `us-east-1`. |
| `azure.subscription_id` | If Azure is selected | Subscription scope queried through Azure Cost Management. It is an identifier, not a secret. |
| `gcp.billing_export_table` | If GCP is selected | Fully qualified BigQuery Cloud Billing export table: `project.dataset.table`. |
| `cloudflare.month_to_date_cost` | If Cloudflare is selected | Month-to-date cost produced by your own collector. This adapter does not calculate it from a Cloudflare token. |
| `cloudflare.currency` | No | Currency for the Cloudflare collector value. Default: `USD`. |
| `notifications.slack` | No | Enables Slack alerts. Requires `ARANZA_CLOUD_SLACK_WEBHOOK_URL` when `true`. Default: `true` only if the webhook exists. |
| `notifications.telegram` | No | Enables Telegram alerts. Requires bot token and chat ID when `true`. Default: `true` only if either Telegram value exists. |
| `notifications.telegram_chat_id` | If Telegram is enabled | Telegram target chat/group/channel ID. It is not a credential and can be overridden by environment. |

All budgets and amounts must use the provider billing currency. The library does not perform conversion; comparing or aggregating values in different currencies would be misleading.

## Environment variables owned by this library

| Variable | Secret | Description |
| --- | --- | --- |
| `ARANZA_CLOUD_CONFIG_FILE` | No | Path to the TOML file. If omitted, legacy environment-only configuration remains supported. |
| `ARANZA_CLOUD_PROVIDERS` | No | Comma-separated override for `monitor.providers`, e.g. `aws,gcp`. |
| `ARANZA_CLOUD_CURRENCY` | No | Override for `monitor.currency`. |
| `ARANZA_CLOUD_ALERT_THRESHOLDS` | No | Comma-separated override for `monitor.thresholds`, e.g. `0.8,0.9,1`. |
| `ARANZA_CLOUD_BUDGET` | No | Override for `budgets.global`. |
| `ARANZA_CLOUD_AWS_BUDGET` | No | Override for `budgets.aws`. |
| `ARANZA_CLOUD_AZURE_BUDGET` | No | Override for `budgets.azure`. |
| `ARANZA_CLOUD_GCP_BUDGET` | No | Override for `budgets.gcp`. |
| `ARANZA_CLOUD_CLOUDFLARE_BUDGET` | No | Override for `budgets.cloudflare`. |
| `ARANZA_CLOUD_AWS_REGION` | No | Override for `aws.region`. |
| `ARANZA_CLOUD_AZURE_SUBSCRIPTION_ID` | No | Override for `azure.subscription_id`. |
| `ARANZA_CLOUD_GCP_BILLING_EXPORT_TABLE` | No | Override for `gcp.billing_export_table`. |
| `ARANZA_CLOUD_CLOUDFLARE_MONTH_TO_DATE_COST` | No | Override for `cloudflare.month_to_date_cost`. |
| `ARANZA_CLOUD_CLOUDFLARE_CURRENCY` | No | Override for `cloudflare.currency`. |
| `ARANZA_CLOUD_SLACK_ENABLED` | No | `true` or `false`; overrides `notifications.slack`. |
| `ARANZA_CLOUD_SLACK_WEBHOOK_URL` | Yes | Slack incoming-webhook URL. It is read only from environment. |
| `ARANZA_CLOUD_TELEGRAM_ENABLED` | No | `true` or `false`; overrides `notifications.telegram`. |
| `ARANZA_CLOUD_TELEGRAM_CHAT_ID` | No | Override for `notifications.telegram_chat_id`. |
| `ARANZA_CLOUD_TELEGRAM_BOT_TOKEN` | Yes | Telegram Bot API token. It is read only from environment. |

An empty environment variable does not erase a TOML value; it is treated as unset. Use a deliberate override such as `ARANZA_CLOUD_SLACK_ENABLED=false` to disable a destination.

## Provider credential variables

These are consumed by the provider SDKs, not by this library. Do not copy values unnecessarily; prefer platform-native workload credentials in deployed backends.

| Provider | Typical variables | Recommended production approach |
| --- | --- | --- |
| AWS | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, `AWS_PROFILE` | IAM role attached to the workload; permission `ce:GetCostAndUsage`. |
| Azure | `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` | Managed Identity or workload identity; Cost Management read access at the selected scope. |
| GCP | `GOOGLE_APPLICATION_CREDENTIALS` | Workload Identity / Application Default Credentials; BigQuery read access to the Billing export table. |

## Validation behavior

Configuration fails before querying any cloud when a selected provider lacks its required identifier, an enabled notifier lacks its secret, a number is negative/invalid, or a provider name is unsupported. This failure is intentional: it prevents a backend from silently running with notifications disabled or querying the wrong scope.
