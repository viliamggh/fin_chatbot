#!/bin/bash
set -e

# Define variables
LOCATION="westeurope"
PROJECT_NAME="finchatbot260103"
PROJECT_NAME_NODASH="finchatbot260103"
REPO_NAME="viliamggh/fin_chatbot"

RESOURCE_GROUP_NAME="${PROJECT_NAME}-rg"
IDENTITY_NAME="${PROJECT_NAME}-uami"
STORAGE_ACCOUNT_NAME="${PROJECT_NAME_NODASH}sttf"
CONTAINER_NAME="terraform-state"

echo $STORAGE_ACCOUNT_NAME
echo $IDENTITY_NAME
echo $RESOURCE_GROUP_NAME

# 1. Create a resource group
echo "Creating Resource Group: $RESOURCE_GROUP_NAME"
az group create --name "$RESOURCE_GROUP_NAME" --location "$LOCATION"

# 2. Create a user-assigned managed identity
echo "Creating User-Assigned Managed Identity: $IDENTITY_NAME"
IDENTITY_ID=$(az identity create --name "$IDENTITY_NAME" --resource-group "$RESOURCE_GROUP_NAME" --query id -o tsv)

sleep 20

# 3. Assign the user-assigned managed identity as the owner of the resource group
echo "Assigning User-Assigned Managed Identity to Resource Group: $RESOURCE_GROUP_NAME"
az role assignment create --assignee $(az identity show --name $IDENTITY_NAME --resource-group $RESOURCE_GROUP_NAME --query principalId -o tsv) --role "Owner" --scope "/subscriptions/$(az account show --query id -o tsv)/resourceGroups/$RESOURCE_GROUP_NAME"

# 4. Create a storage account for terraform state
echo "Creating Storage Account: $STORAGE_ACCOUNT_NAME"
az storage account create \
    --name "$STORAGE_ACCOUNT_NAME" \
    --resource-group "$RESOURCE_GROUP_NAME" \
    --location "$LOCATION" \
    --sku Standard_LRS \
    --kind StorageV2

# 5. Create a container within the storage account
echo "Creating Container: $CONTAINER_NAME"
az storage container create --name "$CONTAINER_NAME" --account-name "$STORAGE_ACCOUNT_NAME"

echo "All base resources created successfully."

sleep 20

# 6. Create federated credentials for GitHub Actions
az identity federated-credential create \
  --resource-group $RESOURCE_GROUP_NAME \
  --identity-name $IDENTITY_NAME \
  --name gha-dev-env \
  --issuer https://token.actions.githubusercontent.com \
  --subject repo:${REPO_NAME}:environment:dev \
  --audiences api://AzureADTokenExchange

az identity federated-credential create \
  --resource-group $RESOURCE_GROUP_NAME \
  --identity-name $IDENTITY_NAME \
  --name gha-main-env \
  --issuer https://token.actions.githubusercontent.com \
  --subject repo:${REPO_NAME}:environment:main \
  --audiences api://AzureADTokenExchange

# 7. Set GitHub variables
# NOTE: Run first: export GH_TOKEN="<your-github-token>"
echo $(az identity show --name $IDENTITY_NAME --resource-group $RESOURCE_GROUP_NAME --query clientId -o tsv) | gh variable set UAMI_ID --repo $REPO_NAME
echo $(az identity show --name $IDENTITY_NAME --resource-group $RESOURCE_GROUP_NAME --query tenantId -o tsv) | gh variable set TENANT_ID --repo $REPO_NAME
echo $(az identity show --name $IDENTITY_NAME --resource-group $RESOURCE_GROUP_NAME | jq -r '.id | split("/")[2]') | gh variable set SUB_ID --repo $REPO_NAME
echo $RESOURCE_GROUP_NAME | gh variable set RG_NAME --repo $REPO_NAME
echo $IDENTITY_NAME | gh variable set IDENTITY_NAME --repo $REPO_NAME
echo $STORAGE_ACCOUNT_NAME | gh variable set STORAGE_ACCOUNT_NAME --repo $REPO_NAME
echo $CONTAINER_NAME | gh variable set CONTAINER_NAME --repo $REPO_NAME
echo $PROJECT_NAME_NODASH | gh variable set PROJECT_NAME_NODASH --repo $REPO_NAME

# 8. Create tfbackend.conf for local tf connection
cat > terraform/tfbackend.conf <<EOF
resource_group_name  = "$RESOURCE_GROUP_NAME"
storage_account_name = "$STORAGE_ACCOUNT_NAME"
container_name       = "$CONTAINER_NAME"
key                  = "terraform.tfstate"
EOF

echo ""
echo "=========================================="
echo "Setup complete! Next steps:"
echo "=========================================="
echo ""
echo "1. Get the UAMI principal ID (for fin_az_core registration):"
echo "   az identity show --name $IDENTITY_NAME --resource-group $RESOURCE_GROUP_NAME --query principalId -o tsv"
echo ""
echo "2. Add the principal ID to fin_az_core/terraform/terraform.tfvars:"
echo "   external_cicd_identities = {"
echo "     ...existing entries..."
echo "     \"fin_chatbot\" = \"<principal-id-from-step-1>\""
echo "   }"
echo ""
echo "3. Run terraform apply in fin_az_core to grant ACR + Key Vault access"
echo ""
echo "4. Push changes to fin_chatbot repo to trigger deployment"
echo ""
