# Observability and cost visibility (BUILD_PLAN.md phase 4).
#
#   Metrics  - free service metrics (API Gateway, Lambda) plus model tokens,
#              cost and latency per alias, written by the function as
#              Embedded Metric Format log lines (lambda/src/metrics.ts)
#   Traces   - X-Ray on the function (lambda.tf); on the API stage, optional
#   Logs     - function log (metadata only, lambda.tf); API access log, optional
#   Alarms   - four alarms to one SNS topic, email optional
#
# Kept small on purpose: custom metrics and alarms are billed per metric and
# per alarm, so only what an operator would act on is created (Cost).

# --- Alarm notifications ----------------------------------------------------

# Not encrypted with KMS: CloudWatch can't publish to a topic encrypted with
# the AWS managed SNS key, and a customer managed key costs $1/month. The
# topic carries alarm state changes only, no request data.
resource "aws_sns_topic" "alarms" {
  name = "${local.name}-alarms"
}

# Email delivery starts only after the recipient clicks the confirmation
# link AWS sends. The address lives in terraform.tfvars (gitignored).
resource "aws_sns_topic_subscription" "alarm_email" {
  count     = var.alarm_email == null ? 0 : 1
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

locals {
  alarm_actions = [aws_sns_topic.alarms.arn]

  api_dimensions = {
    ApiName = aws_api_gateway_rest_api.api.name
    Stage   = aws_api_gateway_stage.api.stage_name
  }

  # Metric math IDs must start with a lower-case letter and contain only
  # letters, digits and underscores.
  cost_metric_ids = { for alias in keys(var.models) : alias => "cost_${replace(lower(alias), "/[^a-z0-9_]/", "_")}" }
}

# --- Alarms -----------------------------------------------------------------

# Server-side failures seen by clients: function errors, model errors mapped
# to 5xx, and integration timeouts (Reliability).
resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  alarm_name          = "${local.name}-5xx"
  alarm_description   = "API returned ${var.alarms.server_errors_5min} or more 5xx responses in 5 minutes. Check the function log for error_type and error_name."
  namespace           = "AWS/ApiGateway"
  metric_name         = "5XXError"
  dimensions          = local.api_dimensions
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = var.alarms.server_errors_5min
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions
}

# Slow responses: p95 rather than average, so a few slow calls aren't hidden
# by many fast ones (Performance Efficiency).
resource "aws_cloudwatch_metric_alarm" "api_latency_p95" {
  alarm_name          = "${local.name}-latency-p95"
  alarm_description   = "API p95 latency above ${var.alarms.p95_latency_ms} ms for 15 minutes. Compare with the ModelLatency metric to see whether the model is the cause."
  namespace           = "AWS/ApiGateway"
  metric_name         = "Latency"
  dimensions          = local.api_dimensions
  extended_statistic  = "p95"
  period              = 300
  evaluation_periods  = 3
  datapoints_to_alarm = 3
  threshold           = var.alarms.p95_latency_ms
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions
}

# The function was refused an execution slot. Lambda concurrency is shared
# by every function in the account and region (Reliability).
resource "aws_cloudwatch_metric_alarm" "lambda_throttles" {
  alarm_name          = "${local.name}-lambda-throttles"
  alarm_description   = "The chat function was throttled. Account Lambda concurrency is shared; check other workloads or request a quota increase."
  namespace           = "AWS/Lambda"
  metric_name         = "Throttles"
  dimensions          = { FunctionName = aws_lambda_function.chat.function_name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions
}

# Estimated model spend per day, all aliases together: the sum of the
# function's CostUSD metric for each alias (Cost Optimization). Complements
# the account budget (bootstrap/budget), which reports actual charges hours
# later; this alarm reacts within minutes.
resource "aws_cloudwatch_metric_alarm" "daily_cost" {
  alarm_name          = "${local.name}-daily-cost"
  alarm_description   = "Estimated model cost above ${var.alarms.daily_cost_usd} USD in a day. Check which Model dimension of the CostUSD metric is rising, and which client_id in the function log."
  evaluation_periods  = 1
  threshold           = var.alarms.daily_cost_usd
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions

  metric_query {
    id          = "total"
    expression  = "SUM([${join(", ", values(local.cost_metric_ids))}])"
    label       = "Estimated model cost (USD)"
    return_data = true
  }

  dynamic "metric_query" {
    for_each = local.cost_metric_ids
    content {
      id = metric_query.value
      metric {
        namespace   = var.metrics_namespace
        metric_name = "CostUSD"
        dimensions  = { Model = metric_query.key }
        stat        = "Sum"
        period      = 86400
      }
    }
  }
}

# --- API access log (optional) ------------------------------------------------

# One line per request as API Gateway saw it, including requests the function
# never receives (rejected by the authorizer, the API key check or
# throttling). Needs the account-wide API Gateway CloudWatch role, which only
# an administrator can set (docs/PREFLIGHT_CHECKS.md 5.1), so it's off by
# default.
resource "aws_cloudwatch_log_group" "api_access" {
  count             = var.enable_access_logs ? 1 : 0
  name              = "/aws/apigateway/${local.name}-access"
  retention_in_days = var.log_retention_days
}

# --- Dashboard (optional) ---------------------------------------------------

# Off by default: a dashboard costs about $3 per month. The same metrics can
# be viewed ad hoc in CloudWatch -> Metrics at no charge.
resource "aws_cloudwatch_dashboard" "api" {
  count          = var.enable_dashboard ? 1 : 0
  dashboard_name = local.name

  dashboard_body = jsonencode({
    widgets = [
      {
        type = "metric", x = 0, y = 0, width = 12, height = 6
        properties = {
          title  = "Requests and errors"
          region = var.aws_region
          stat   = "Sum"
          period = 300
          metrics = [
            ["AWS/ApiGateway", "Count", "ApiName", local.api_dimensions.ApiName, "Stage", local.api_dimensions.Stage],
            [".", "4XXError", ".", ".", ".", "."],
            [".", "5XXError", ".", ".", ".", "."],
          ]
        }
      },
      {
        type = "metric", x = 12, y = 0, width = 12, height = 6
        properties = {
          title  = "Latency p95 (ms)"
          region = var.aws_region
          stat   = "p95"
          period = 300
          metrics = concat(
            [["AWS/ApiGateway", "Latency", "ApiName", local.api_dimensions.ApiName, "Stage", local.api_dimensions.Stage]],
            [for alias in keys(var.models) : [var.metrics_namespace, "ModelLatency", "Model", alias]],
          )
        }
      },
      {
        type = "metric", x = 0, y = 6, width = 12, height = 6
        properties = {
          title   = "Tokens by model"
          region  = var.aws_region
          stat    = "Sum"
          period  = 3600
          stacked = true
          metrics = flatten([for alias in keys(var.models) : [
            [var.metrics_namespace, "InputTokens", "Model", alias],
            [var.metrics_namespace, "OutputTokens", "Model", alias],
          ]])
        }
      },
      {
        type = "metric", x = 12, y = 6, width = 12, height = 6
        properties = {
          title   = "Estimated cost by model (USD per hour)"
          region  = var.aws_region
          stat    = "Sum"
          period  = 3600
          stacked = true
          metrics = [for alias in keys(var.models) : [var.metrics_namespace, "CostUSD", "Model", alias]]
        }
      },
    ]
  })
}
