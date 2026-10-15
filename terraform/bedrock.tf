# One application inference profile per model alias.
#
# A system-defined profile (e.g. a geographic "eu." profile) routes requests
# across the regions of that geography. Wrapping it in an application
# inference profile changes nothing about routing, but gives this stack its
# own tagged ARN to invoke. Model charges are billed through AWS Marketplace
# and don't carry the caller's tags; invoking a tagged application profile
# lets Cost Explorer and tag-scoped budgets attribute model spend to this
# stack (BUILD_PLAN.md D13).

data "aws_bedrock_inference_profile" "source" {
  for_each             = var.models
  inference_profile_id = each.value.source_inference_profile_id
}

resource "aws_bedrock_inference_profile" "alias" {
  for_each = var.models
  name     = "${local.name}-${each.key}"
  # Bedrock restricts descriptions to letters, digits, ':' and '.', with single
  # spaces, '_' or '-' between them - no quotes, arrows or other punctuation.
  description = "${local.name} ${each.key} alias for ${each.value.source_inference_profile_id}"

  model_source {
    copy_from = data.aws_bedrock_inference_profile.source[each.key].inference_profile_arn
  }
}

locals {
  # Everything the Lambda role must be allowed to invoke: the application
  # profiles it calls, the system profiles behind them, and the foundation
  # models in every region those profiles can route to.
  bedrock_invoke_arns = distinct(concat(
    [for p in aws_bedrock_inference_profile.alias : p.arn],
    [for p in data.aws_bedrock_inference_profile.source : p.inference_profile_arn],
    flatten([for p in data.aws_bedrock_inference_profile.source : [for m in p.models : m.model_arn]]),
  ))
}
