# Remote state in S3 with native locking. Settings are supplied at init time
# from a gitignored backend.hcl (see backend.hcl.example), so no bucket name or
# account details live in this repository:
#
#   terraform init "-backend-config=backend.hcl"
terraform {
  backend "s3" {}
}
