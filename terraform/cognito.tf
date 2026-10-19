# Client authentication (D2): OAuth 2.0 client-credentials flow.
#
# The user pool itself is created once in bootstrap/iam (the deploy role may
# manage only that pool). Terraform adds what this API needs to it:
#   - a domain, which hosts the token endpoint clients call
#   - a resource server defining the API's scope
#   - one app client (client ID + secret) per entry in var.api_clients
#
# A client exchanges its ID and secret for a short-lived access token and
# sends it as `Authorization: Bearer <token>`; API Gateway validates it.

resource "aws_cognito_user_pool_domain" "this" {
  # Domain prefixes are unique per region across all accounts, so a short
  # hash of the account ID is added. Prefixes can't contain "aws", "amazon"
  # or "cognito".
  domain       = "${local.name}-${substr(sha1(local.account_id), 0, 8)}"
  user_pool_id = var.cognito_user_pool_id
}

resource "aws_cognito_resource_server" "api" {
  identifier   = local.name
  name         = local.name
  user_pool_id = var.cognito_user_pool_id

  scope {
    scope_name        = "invoke"
    scope_description = "Call the GenAI API"
  }
}

resource "aws_cognito_user_pool_client" "api" {
  for_each     = var.api_clients
  name         = "${local.name}-${each.key}"
  user_pool_id = var.cognito_user_pool_id

  generate_secret                      = true
  allowed_oauth_flows                  = ["client_credentials"]
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_scopes                 = aws_cognito_resource_server.api.scope_identifiers

  # Short-lived tokens limit the damage if one leaks (Security). Clients
  # reuse a token until it expires; Cognito bills per token issued.
  access_token_validity = 60
  token_validity_units {
    access_token = "minutes"
  }
}
