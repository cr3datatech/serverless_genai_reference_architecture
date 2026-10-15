# Execution role for the chat Lambda function.
#
# Least privilege in two layers:
#   1. The inline policy grants only what the function does: invoke the
#      allowlisted models, write its own logs, send traces.
#   2. The permissions boundary (bootstrap/iam) caps the role regardless of
#      what policies are attached. The deploy role can't create a role
#      without it.

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }

    # Only Lambda functions in this account may use the role (confused-deputy protection).
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name                 = "${local.name}-lambda"
  description          = "Execution role for ${local.lambda_function_name}"
  assume_role_policy   = data.aws_iam_policy_document.lambda_assume.json
  permissions_boundary = local.permissions_boundary_arn
}

data "aws_iam_policy_document" "lambda" {
  statement {
    sid = "InvokeAllowlistedModels"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
    ]
    resources = local.bedrock_invoke_arns
  }

  statement {
    sid       = "WriteOwnLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${local.lambda_log_group_arn}:*"]
  }

  statement {
    sid       = "WriteTraces"
    actions   = ["xray:PutTraceSegments", "xray:PutTelemetryRecords"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "${local.name}-lambda"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda.json
}
