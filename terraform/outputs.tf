output "lambda_role_arn" {
  description = "Execution role for the chat Lambda function."
  value       = aws_iam_role.lambda.arn
}

output "model_aliases" {
  description = "Alias -> application inference profile ARN invoked by the API."
  value       = { for k, p in aws_bedrock_inference_profile.alias : k => p.arn }
}
