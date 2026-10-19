# REST API front door (D1).
#
#   POST /v1/chat     -> chat function
#   GET  /v1/models   -> chat function (lists aliases)
#
# Every method requires both a Cognito access token with the API's scope
# (who is calling) and an API key (which usage plan applies). Throttling
# happens here, before the function or the model is paid for (D9).

resource "aws_api_gateway_rest_api" "api" {
  name        = local.name
  description = "Serverless GenAI reference API"

  endpoint_configuration {
    types = ["REGIONAL"]
  }
}

resource "aws_api_gateway_resource" "v1" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  parent_id   = aws_api_gateway_rest_api.api.root_resource_id
  path_part   = "v1"
}

resource "aws_api_gateway_resource" "route" {
  for_each    = local.api_routes
  rest_api_id = aws_api_gateway_rest_api.api.id
  parent_id   = aws_api_gateway_resource.v1.id
  path_part   = each.key
}

resource "aws_api_gateway_authorizer" "cognito" {
  name            = "cognito"
  rest_api_id     = aws_api_gateway_rest_api.api.id
  type            = "COGNITO_USER_POOLS"
  provider_arns   = [local.cognito_user_pool_arn]
  identity_source = "method.request.header.Authorization"
}

resource "aws_api_gateway_method" "route" {
  for_each             = local.api_routes
  rest_api_id          = aws_api_gateway_rest_api.api.id
  resource_id          = aws_api_gateway_resource.route[each.key].id
  http_method          = each.value
  authorization        = "COGNITO_USER_POOLS"
  authorizer_id        = aws_api_gateway_authorizer.cognito.id
  authorization_scopes = aws_cognito_resource_server.api.scope_identifiers
  api_key_required     = true
}

# Lambda proxy integration: the function receives the whole request and
# builds the whole response.
resource "aws_api_gateway_integration" "route" {
  for_each                = local.api_routes
  rest_api_id             = aws_api_gateway_rest_api.api.id
  resource_id             = aws_api_gateway_resource.route[each.key].id
  http_method             = aws_api_gateway_method.route[each.key].http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.chat.invoke_arn
}

# Errors raised by API Gateway itself (missing token, bad API key, throttled)
# use the same JSON shape as the function's errors.
resource "aws_api_gateway_gateway_response" "json" {
  for_each      = toset(["DEFAULT_4XX", "DEFAULT_5XX"])
  rest_api_id   = aws_api_gateway_rest_api.api.id
  response_type = each.key

  response_templates = {
    "application/json" = "{\"error\":{\"type\":\"$context.error.responseType\",\"message\":$context.error.messageString,\"request_id\":\"$context.requestId\"}}"
  }
}

# API Gateway reports an unknown path as a 403 "missing authentication token"
# with a confusing message; return a plain 404 instead.
resource "aws_api_gateway_gateway_response" "not_found" {
  rest_api_id   = aws_api_gateway_rest_api.api.id
  response_type = "MISSING_AUTHENTICATION_TOKEN"
  status_code   = "404"

  response_templates = {
    "application/json" = "{\"error\":{\"type\":\"not_found\",\"message\":\"Route not found.\",\"request_id\":\"$context.requestId\"}}"
  }
}

resource "aws_api_gateway_deployment" "api" {
  rest_api_id = aws_api_gateway_rest_api.api.id

  # A deployment is a snapshot; redeploy whenever the API definition changes.
  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.v1,
      aws_api_gateway_resource.route,
      aws_api_gateway_method.route,
      aws_api_gateway_integration.route,
      aws_api_gateway_authorizer.cognito,
      aws_api_gateway_gateway_response.json,
      aws_api_gateway_gateway_response.not_found,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_stage" "api" {
  rest_api_id   = aws_api_gateway_rest_api.api.id
  deployment_id = aws_api_gateway_deployment.api.id
  stage_name    = var.stage_name

  # X-Ray on the stage is optional: enabling it needs permission to create
  # API Gateway's service-linked role, which the deploy role doesn't have
  # (docs/DEPLOYMENT.md, Monitoring). The function is traced either way.
  xray_tracing_enabled = var.enable_api_tracing

  dynamic "access_log_settings" {
    for_each = var.enable_access_logs ? [1] : []
    content {
      destination_arn = aws_cloudwatch_log_group.api_access[0].arn
      # Who called, what happened and how long it took; no request or
      # response bodies.
      format = jsonencode({
        request_id          = "$context.requestId"
        time                = "$context.requestTime"
        ip                  = "$context.identity.sourceIp"
        client_id           = "$context.authorizer.claims.client_id"
        api_key_id          = "$context.identity.apiKeyId"
        method              = "$context.httpMethod"
        path                = "$context.resourcePath"
        status              = "$context.status"
        error_type          = "$context.error.responseType"
        latency_ms          = "$context.responseLatency"
        integration_latency = "$context.integration.latency"
        response_bytes      = "$context.responseLength"
      })
    }
  }
}

# Stage-wide ceiling for all clients together.
resource "aws_api_gateway_method_settings" "all" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  stage_name  = aws_api_gateway_stage.api.stage_name
  method_path = "*/*"

  settings {
    throttling_rate_limit  = var.stage_throttle.rate_limit
    throttling_burst_limit = var.stage_throttle.burst_limit
  }
}

# Per-client ceiling: each client's API key belongs to this plan.
resource "aws_api_gateway_usage_plan" "clients" {
  name        = "${local.name}-clients"
  description = "Per-client throttle and daily quota"

  api_stages {
    api_id = aws_api_gateway_rest_api.api.id
    stage  = aws_api_gateway_stage.api.stage_name
  }

  throttle_settings {
    rate_limit  = var.client_throttle.rate_limit
    burst_limit = var.client_throttle.burst_limit
  }

  quota_settings {
    limit  = var.client_throttle.daily_request
    period = "DAY"
  }
}

resource "aws_api_gateway_api_key" "client" {
  for_each = var.api_clients
  name     = "${local.name}-${each.key}"
}

resource "aws_api_gateway_usage_plan_key" "client" {
  for_each      = var.api_clients
  key_id        = aws_api_gateway_api_key.client[each.key].id
  key_type      = "API_KEY"
  usage_plan_id = aws_api_gateway_usage_plan.clients.id
}
