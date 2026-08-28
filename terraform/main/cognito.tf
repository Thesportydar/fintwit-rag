# ============================================================================
# Amazon Cognito User Pool & Client for FinTwit Agent
# ============================================================================

resource "aws_cognito_user_pool" "pool" {
  name = "${var.project}-${var.env}-user-pool"

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  password_policy {
    minimum_length    = 8
    require_lowercase = true
    require_numbers   = true
    require_symbols   = true
    require_uppercase = true
  }

  admin_create_user_config {
    allow_admin_create_user_only = false
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  tags = {
    Name = "${var.project}-${var.env}-cognito-pool"
  }
}

resource "aws_cognito_user_pool_client" "client" {
  name         = "${var.project}-${var.env}-web-client"
  user_pool_id = aws_cognito_user_pool.pool.id

  generate_secret = false

  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_SRP_AUTH"
  ]

  prevent_user_existence_errors = "ENABLED"
}

# Usuario demo inicial con contraseña permanente para pruebas directas y portfolio
resource "aws_cognito_user" "demo_user" {
  user_pool_id = aws_cognito_user_pool.pool.id
  username     = "demo@fintwit.com"
  password     = var.cognito_demo_password

  message_action = "SUPPRESS"

  attributes = {
    email          = "demo@fintwit.com"
    email_verified = "true"
  }
}

# Usuario administrador para desarrollo local (sin rate limit)
resource "aws_cognito_user" "admin_user" {
  user_pool_id = aws_cognito_user_pool.pool.id
  username     = var.cognito_admin_email
  password     = var.cognito_admin_password

  message_action = "SUPPRESS"

  attributes = {
    email          = var.cognito_admin_email
    email_verified = "true"
  }
}
