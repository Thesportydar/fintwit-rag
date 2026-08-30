# ============================================================================
# AWS Monthly Cost Budget with Email Alerts
# ============================================================================

resource "aws_budgets_budget" "monthly" {
  name         = "${var.project}-${var.env}-monthly-budget"
  budget_type  = "COST"
  limit_amount = var.budget_limit_amount
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_types {
    include_credit             = false
    include_discount           = true
    include_other_subscription = true
    include_recurring          = true
    include_refund             = false
    include_subscription       = true
    include_support            = true
    include_tax                = true
    include_upfront            = true
    use_blended                = false
  }

  # 1. Alerta temprana preventiva: Costo real supera el 80%
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = var.budget_subscriber_emails
  }

  # 2. Alerta crítica: Costo real supera el 100%
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = var.budget_subscriber_emails
  }

  # 3. Alerta predictiva: Consumo proyectado superará el 100% del mes
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = var.budget_subscriber_emails
  }
}
