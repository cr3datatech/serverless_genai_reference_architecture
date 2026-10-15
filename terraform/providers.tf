provider "aws" {
  region = var.aws_region

  # Applied to every resource this provider creates. Project=powerlab scopes
  # cost reports, budgets and the Well-Architected review to this stack.
  default_tags {
    tags = {
      Project   = var.project
      Component = var.component
      ManagedBy = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
