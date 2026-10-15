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
  }))

  validation {
    condition     = length(var.models) > 0
    error_message = "Define at least one model alias."
  }
}
