terraform {
  backend "azurerm" {
  }
  required_providers {
    azurerm = {
      source = "hashicorp/azurerm"
    }
    azuread = {
      source = "hashicorp/azuread"
    }
  }
}

provider "azurerm" {
  features {}
}

data "azurerm_client_config" "current" {}

# Reference core infrastructure from fin_az_core Terraform state
data "terraform_remote_state" "core_infra" {
  backend = "azurerm"
  config = {
    resource_group_name  = var.core_infra_rg
    storage_account_name = var.core_infra_sa
    container_name       = var.core_infra_container
    key                  = var.core_infra_key
    use_azuread_auth     = true
  }
}

# Data source for fin_chatbot's OWN resource group
data "azurerm_resource_group" "app_rg" {
  name = var.rg_name
}

# Data source for Key Vault secrets
data "azurerm_key_vault_secret" "sql_password" {
  name         = "sql-app-password"
  key_vault_id = data.terraform_remote_state.core_infra.outputs.key_vault_id
}

data "azurerm_key_vault_secret" "openai_api_key" {
  name         = "openai-api-key"
  key_vault_id = data.terraform_remote_state.core_infra.outputs.key_vault_id
}

data "azurerm_key_vault_secret" "chatbot_auth_user" {
  name         = "chatbot-auth-user"
  key_vault_id = data.terraform_remote_state.core_infra.outputs.key_vault_id
}

data "azurerm_key_vault_secret" "chatbot_auth_pass" {
  name         = "chatbot-auth-pass"
  key_vault_id = data.terraform_remote_state.core_infra.outputs.key_vault_id
}

# Local variables for core infrastructure references
locals {
  # App resource group
  app_rg_name     = data.azurerm_resource_group.app_rg.name
  app_rg_location = data.azurerm_resource_group.app_rg.location

  # Core infrastructure references (from fin_az_core remote state)
  key_vault_url    = data.terraform_remote_state.core_infra.outputs.key_vault_url
  key_vault_id     = data.terraform_remote_state.core_infra.outputs.key_vault_id
  acr_login_server = data.terraform_remote_state.core_infra.outputs.container_registry_login_server
  acr_id           = data.terraform_remote_state.core_infra.outputs.container_registry_id

  # SQL Database references (from fin_az_core remote state)
  sql_server_fqdn   = data.terraform_remote_state.core_infra.outputs.sql_server_fqdn
  sql_database_name = data.terraform_remote_state.core_infra.outputs.sql_database_name
  sql_username      = "app_user"
  sql_password      = data.azurerm_key_vault_secret.sql_password.value

  # Azure OpenAI references (from fin_az_core remote state)
  openai_endpoint        = data.terraform_remote_state.core_infra.outputs.openai_endpoint
  openai_deployment_name = data.terraform_remote_state.core_infra.outputs.openai_deployment_name
  openai_api_key         = data.azurerm_key_vault_secret.openai_api_key.value

  # Chatbot authentication credentials
  chatbot_auth_user = data.azurerm_key_vault_secret.chatbot_auth_user.value
  chatbot_auth_pass = data.azurerm_key_vault_secret.chatbot_auth_pass.value

  # Shared application identity (from fin_az_core)
  app_identity_id           = data.terraform_remote_state.core_infra.outputs.app_identity_id
  app_identity_client_id    = data.terraform_remote_state.core_infra.outputs.app_identity_client_id
  app_identity_principal_id = data.terraform_remote_state.core_infra.outputs.app_identity_principal_id
  app_identity_tenant_id    = data.terraform_remote_state.core_infra.outputs.app_identity_tenant_id
}

resource "azurerm_container_app_environment" "c_app_env" {
  name                = "${var.project_name_no_dash}cae"
  location            = local.app_rg_location
  resource_group_name = local.app_rg_name
}

resource "null_resource" "always_run" {
  triggers = {
    timestamp = "${timestamp()}"
  }
}
