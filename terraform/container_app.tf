resource "azurerm_container_app" "chatbot" {
  name                         = "${var.project_name_no_dash}aca"
  container_app_environment_id = azurerm_container_app_environment.c_app_env.id
  resource_group_name          = data.azurerm_resource_group.app_rg.name
  revision_mode                = "Single"

  identity {
    type         = "UserAssigned"
    identity_ids = [local.app_identity_id]
  }

  lifecycle {
    replace_triggered_by = [
      null_resource.always_run
    ]
  }

  ingress {
    external_enabled           = true
    allow_insecure_connections = false  # CHANGED: Force HTTPS only
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
    target_port = 7860
  }

  registry {
    server   = local.acr_login_server
    identity = local.app_identity_id
  }

  # Secrets for sensitive values
  secret {
    name  = "sql-password"
    value = local.sql_password
  }

  secret {
    name  = "openai-api-key"
    value = local.openai_api_key
  }

  template {
    container {
      name   = replace(var.image_name, "_", "")
      image  = "${local.acr_login_server}/${var.image_name}:${var.environment}"
      cpu    = 0.5
      memory = "1Gi"

      # Azure OpenAI configuration
      env {
        name  = "AZURE_OPENAI_ENDPOINT"
        value = local.openai_endpoint
      }

      env {
        name  = "AZURE_OPENAI_DEPLOYMENT"
        value = local.openai_deployment_name
      }

      env {
        name        = "AZURE_OPENAI_API_KEY"
        secret_name = "openai-api-key"
      }

      # SQL Database configuration
      env {
        name  = "AZURE_SQL_SERVER"
        value = local.sql_server_fqdn
      }

      env {
        name  = "AZURE_SQL_DATABASE"
        value = local.sql_database_name
      }

      env {
        name  = "SQL_USERNAME"
        value = local.sql_username
      }

      env {
        name        = "SQL_PASSWORD"
        secret_name = "sql-password"
      }

      # Shared identity info (may be needed for future Azure SDK calls)
      env {
        name  = "AZURE_CLIENT_ID"
        value = local.app_identity_client_id
      }

      env {
        name  = "AZURE_TENANT_ID"
        value = local.app_identity_tenant_id
      }
    }

    min_replicas = 0
    max_replicas = 1
  }
}

output "chatbot_url" {
  description = "URL of the deployed chatbot"
  value       = "https://${azurerm_container_app.chatbot.ingress[0].fqdn}"
}
