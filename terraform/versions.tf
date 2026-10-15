# Terraform >= 1.10 is required for native S3 state locking (use_lockfile),
# which removes the need for a DynamoDB lock table.
terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}
