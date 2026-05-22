terraform {
  required_providers { datadog = { source = "DataDog/datadog", version = "~> 3.40" } }
}
provider "datadog" { api_key = var.datadog_api_key app_key = var.datadog_app_key }

resource "datadog_monitor" "error_rate" {
  name                = "${var.service_name} - Error rate >2% (5m)"
  type                = "query alert"
  query               = "sum(last_5m):sum:service.gerald_gateway.errors{*}.as_count() / sum:service.gerald_gateway.requests{*}.as_count() * 100 > 2"
  message             = "High error rate on ${var.service_name}. Check bank API health and gateway logs (request_id)."
  tags                = ["service:${var.service_name}", "team:bnpl"]
  notify_no_data      = false
  require_full_window = true
}

resource "datadog_monitor" "approval_rate_drop" {
  name                = "${var.service_name} - Approval rate drop >20% vs 24h"
  type                = "query alert"
  query               = "sum(last_5m):sum:gerald.approved{*}.as_count() / (sum(last_5m):sum:gerald.approved{*}.as_count() + sum(last_5m):sum:gerald.declined{*}.as_count()) < (avg(last_24h):sum:gerald.approved{*}.as_count() / (avg(last_24h):sum:gerald.approved{*}.as_count() + avg(last_24h):sum:gerald.declined{*}.as_count())) * 0.8"
  message             = "Approval rate dropped >20% vs 24h baseline. Compare bank.fetch.failures and credit_limit.bucket metrics before changing risk thresholds."
  tags                = ["service:${var.service_name}", "team:bnpl"]
  notify_no_data      = false
  require_full_window = true
}

resource "datadog_monitor" "decision_latency_p95" {
  name                = "${var.service_name} - Decision latency p95 >2s (10m)"
  type                = "query alert"
  query               = "avg(last_10m):p95:service.gerald_gateway.request_duration.seconds{endpoint:/v1/decision} > 2"
  message             = "BNPL decision p95 latency elevated — users may abandon checkout."
  tags                = ["service:${var.service_name}", "team:bnpl"]
  notify_no_data      = false
  require_full_window = true
}

resource "datadog_monitor" "bank_fetch_failures" {
  name                = "${var.service_name} - Bank fetch failures spike"
  type                = "query alert"
  query               = "sum(last_10m):sum:bank.fetch.failures{*}.as_count() > 10"
  message             = "Bank API failures spiking; risk scores may be stale or decisions erroring."
  tags                = ["service:${var.service_name}", "team:bnpl"]
  notify_no_data      = false
  require_full_window = true
}
