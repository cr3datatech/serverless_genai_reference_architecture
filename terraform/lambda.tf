# The chat function: validates requests, resolves aliases, calls Bedrock.
#
# Build before planning: `npm ci` and `npm run build` in lambda/
# (docs/DEPLOYMENT.md). The build compiles lambda/src to plain JavaScript in
# lambda/dist, one file per source file, so the code stays readable in the
# Lambda console. Terraform zips lambda/dist and redeploys whenever it changes.

data "archive_file" "lambda" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/dist"
  output_path = "${path.module}/.build/lambda.zip"
}

# Created by Terraform rather than on first invocation, so retention and
# tags are set and `terraform destroy` removes it (nothing left behind).
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.lambda_function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "chat" {
  function_name = local.lambda_function_name
  description   = "GenAI API chat handler"
  role          = aws_iam_role.lambda.arn

  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256
  handler          = "index.handler"
  runtime          = "nodejs22.x"
  architectures    = ["arm64"] # D4: Graviton, cheaper and more energy-efficient

  memory_size = 256
  # Just above the in-code Bedrock timeout and the 29 s API Gateway limit.
  timeout = 30

  # No reserved concurrency: it would need spare account concurrency, and
  # throttling at API Gateway (stage and usage plan) already caps load (D9).

  environment {
    variables = {
      MODELS = jsonencode({
        for alias, p in aws_bedrock_inference_profile.alias : alias => {
          arn           = p.arn
          modelId       = var.models[alias].source_inference_profile_id
          inputPerMtok  = try(var.models[alias].price_per_mtok.input, null)
          outputPerMtok = try(var.models[alias].price_per_mtok.output, null)
        }
      })
      DEFAULT_MODEL  = var.default_model
      MAX_TOKENS_CAP = tostring(var.max_tokens_cap)
    }
  }

  lifecycle {
    precondition {
      condition     = contains(keys(var.models), var.default_model)
      error_message = "default_model must be one of the aliases in var.models."
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda, aws_iam_role_policy.lambda]
}

# Only this API, on its own routes, may invoke the function.
resource "aws_lambda_permission" "api" {
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.chat.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.api.execution_arn}/*/*/v1/*"
}
