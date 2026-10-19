output "lambda_role_arn" {
  description = "Execution role for the chat Lambda function."
  value       = aws_iam_role.lambda.arn
}

output "model_aliases" {
  description = "Alias -> application inference profile ARN invoked by the API."
  value       = { for k, p in aws_bedrock_inference_profile.alias : k => p.arn }
}

output "api_url" {
  description = "Base URL of the API stage; endpoints are <api_url>/v1/chat and <api_url>/v1/models."
  value       = aws_api_gateway_stage.api.invoke_url
}

output "token_url" {
  description = "Cognito OAuth 2.0 token endpoint (client-credentials grant)."
  value       = "https://${aws_cognito_user_pool_domain.this.domain}.auth.${var.aws_region}.amazoncognito.com/oauth2/token"
}

output "oauth_scope" {
  description = "Scope to request in the token call."
  value       = one(aws_cognito_resource_server.api.scope_identifiers)
}

output "client_ids" {
  description = "Cognito app client ID per API client."
  value       = { for k, c in aws_cognito_user_pool_client.api : k => c.id }
}

output "client_secrets" {
  description = "Cognito app client secret per API client. Read with `terraform output -json client_secrets`."
  value       = { for k, c in aws_cognito_user_pool_client.api : k => c.client_secret }
  sensitive   = true
}

output "api_keys" {
  description = "API key per API client. Read with `terraform output -json api_keys`."
  value       = { for k, key in aws_api_gateway_api_key.client : k => key.value }
  sensitive   = true
}

output "alarm_topic_arn" {
  description = "SNS topic the alarms notify. Subscribe more endpoints to it as needed."
  value       = aws_sns_topic.alarms.arn
}
