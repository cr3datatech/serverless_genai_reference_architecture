variable "aws_region" {
  description = "Region to deploy into. Must offer the inference profiles named in var.models."
  type        = string
}

variable "project" {
  description = "Project tag and resource name prefix. IAM permissions in bootstrap/iam only allow resources named <project>-*."
  type        = string
  default     = "powerlab"
}

variable "component" {
  description = "Component tag and second part of resource names."
  type        = string
  default     = "genai-api"
}

variable "permissions_boundary_name" {
  description = "Path and name of the permissions boundary every workload role must carry (created in bootstrap/iam)."
  type        = string
  default     = "control/powerlab-boundary"
}

variable "models" {
  description = <<-EOT
    Model aliases exposed by the API. Each alias maps to a system-defined
    cross-region inference profile ID (list them with
    `aws bedrock list-inference-profiles`). Clients only ever see the alias.
  EOT
  type = map(object({
    source_inference_profile_id = string
    # USD per million tokens, used for the per-request cost estimate (D7).
    # Omit to return cost_estimate_usd = null for that alias.
    price_per_mtok = optional(object({
      input  = number
      output = number
    }))
  }))

  validation {
    condition     = length(var.models) > 0
    error_message = "Define at least one model alias."
  }
}

variable "default_model" {
  description = "Alias used when a request doesn't name one."
  type        = string
  default     = "fast"
}

variable "max_tokens_cap" {
  description = "Server-side ceiling on max_tokens per request (D9). Keeps non-streaming responses inside the 29 s API Gateway timeout and bounds cost."
  type        = number
  default     = 1024
}

variable "cognito_user_pool_id" {
  description = "ID of the user pool created in bootstrap/iam (the deploy role may manage only this pool)."
  type        = string
}

variable "api_clients" {
  description = "Client applications allowed to call the API. Each gets its own Cognito app client (credentials) and API key (usage plan)."
  type        = set(string)
  default     = ["demo"]
}

variable "stage_name" {
  description = "API Gateway stage name; part of the invoke URL."
  type        = string
  default     = "lab"
}

variable "stage_throttle" {
  description = "Stage-wide throttle, all clients combined (D9)."
  type = object({
    rate_limit  = number
    burst_limit = number
  })
  default = { rate_limit = 5, burst_limit = 10 }
}

variable "client_throttle" {
  description = "Per-client throttle and daily request quota, enforced by the usage plan (D9)."
  type = object({
    rate_limit    = number
    burst_limit   = number
    daily_request = number
  })
  default = { rate_limit = 2, burst_limit = 5, daily_request = 500 }
}

variable "log_retention_days" {
  description = "Retention for the function's log group. Short by default: logs are for troubleshooting, not archive (Cost, Sustainability)."
  type        = number
  default     = 14
}
