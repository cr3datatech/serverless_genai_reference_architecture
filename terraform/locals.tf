locals {
  name       = "${var.project}-${var.component}"
  account_id = data.aws_caller_identity.current.account_id
  partition  = data.aws_partition.current.partition

  permissions_boundary_arn = "arn:${local.partition}:iam::${local.account_id}:policy/${var.permissions_boundary_name}"

  lambda_function_name = "${local.name}-chat"
  lambda_log_group_arn = "arn:${local.partition}:logs:${var.aws_region}:${local.account_id}:log-group:/aws/lambda/${local.lambda_function_name}"

  # Route name -> HTTP method, under /v1.
  api_routes = {
    chat   = "POST"
    models = "GET"
  }

  cognito_user_pool_arn = "arn:${local.partition}:cognito-idp:${var.aws_region}:${local.account_id}:userpool/${var.cognito_user_pool_id}"
}
