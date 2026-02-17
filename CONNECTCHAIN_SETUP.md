# ConnectChain Setup Guide

## Overview

This Text-to-SQL system now supports **ConnectChain**, AMEX's enterprise-grade generative AI framework. ConnectChain provides:

- ✅ **Enterprise Auth Service (EAS)** integration
- ✅ **Proxy configuration** support for security compliance
- ✅ **Certificate management** for secure connections
- ✅ **Centralized LLM configuration** via YAML
- ✅ **Provider-agnostic** interface

For more information about ConnectChain, visit: https://github.com/americanexpress/connectchain

## Installation

### Step 1: Install ConnectChain

```bash
pip install connectchain
```

Or if using the complete requirements:

```bash
pip install -r requirements.txt
```

### Step 2: Configure Environment Variables

Create or update your `.env` file in the project root:

```bash
# Enable ConnectChain
USE_CONNECTCHAIN=true

# ConnectChain Configuration
CONFIG_PATH=connectchain.config.yml
WORKDIR=.

# Azure OpenAI Endpoint (referenced in connectchain.config.yml)
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/

# Optional: EAS (Enterprise Auth Service) Credentials
# Uncomment if using EAS authentication
# CONSUMER_ID=your-consumer-id
# CONSUMER_SECRET=your-consumer-secret

# Optional: Certificate Path
# REQUESTS_CA_BUNDLE=/path/to/ca-bundle.crt

# BigQuery Configuration (unchanged)
GCP_PROJECT_ID=your-gcp-project-id
BIGQUERY_DATASET=your_dataset_name
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json

# Schema Configuration (unchanged)
SCHEMA_DIRECTORY=/path/to/your/schema_directory
```

### Step 3: Configure ConnectChain Models

The project includes a `connectchain.config.yml` file. Update it with your model configuration:

```yaml
# ConnectChain Configuration for Text-to-SQL Agent

# Global EAS (Enterprise Auth Service) Configuration
# Uncomment and configure if using EAS authentication
# eas:
#   id_key: CONSUMER_ID
#   secret_key: CONSUMER_SECRET

# Global Proxy Configuration (optional)
# Uncomment if your enterprise requires proxy settings
# proxy:
#   http: http://proxy.example.com:8080
#   https: https://proxy.example.com:8080

# Models Configuration
models:
  '1':
    provider: openai
    type: chat
    engine: gpt-4
    model_name: gpt-4
    api_version: 2024-02-15-preview
    api_base: ${AZURE_OPENAI_ENDPOINT}
```

### Step 4: Update Application Configuration

The system automatically uses ConnectChain when `USE_CONNECTCHAIN=true`. You can also configure it in `src/config/config.yaml`:

```yaml
llm:
  use_connectchain: true  # Enable ConnectChain

connectchain:
  config_path: "connectchain.config.yml"
  model_index: "1"  # Which model from connectchain.config.yml
  temperature: 0.0
  max_tokens: 4000
```

## Configuration Options

### Option 1: Direct API Access (No EAS)

If you're using Azure OpenAI with direct API key authentication (no EAS), simply provide the API key via environment variable or Azure authentication:

**In `.env`:**
```bash
USE_CONNECTCHAIN=true
CONFIG_PATH=connectchain.config.yml
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
# Azure will use default credential chain or AZURE_OPENAI_API_KEY if set
```

**In `connectchain.config.yml`:**
```yaml
models:
  '1':
    provider: openai
    type: chat
    engine: gpt-4
    model_name: gpt-4
    api_version: 2024-02-15-preview
    api_base: ${AZURE_OPENAI_ENDPOINT}
    # No EAS configuration = direct API access
```

### Option 2: EAS (Enterprise Auth Service) Authentication

If your organization uses EAS for authentication:

**In `.env`:**
```bash
USE_CONNECTCHAIN=true
CONFIG_PATH=connectchain.config.yml
CONSUMER_ID=your-consumer-id
CONSUMER_SECRET=your-consumer-secret
AZURE_OPENAI_ENDPOINT=https://your-eas-gateway.com/api
```

**In `connectchain.config.yml`:**
```yaml
# Global EAS configuration (applies to all models)
eas:
  id_key: CONSUMER_ID
  secret_key: CONSUMER_SECRET

models:
  '1':
    provider: openai
    type: chat
    engine: gpt-4
    model_name: gpt-4
    api_version: 2024-02-15-preview
    api_base: ${AZURE_OPENAI_ENDPOINT}
```

### Option 3: With Proxy Configuration

If your enterprise requires outbound proxy:

**In `connectchain.config.yml`:**
```yaml
# Global proxy configuration
proxy:
  http: http://proxy.example.com:8080
  https: https://proxy.example.com:8080

models:
  '1':
    provider: openai
    type: chat
    engine: gpt-4
    model_name: gpt-4
    api_version: 2024-02-15-preview
    api_base: ${AZURE_OPENAI_ENDPOINT}
```

### Option 4: With Custom Certificates

If you need custom SSL certificates:

**In `.env`:**
```bash
REQUESTS_CA_BUNDLE=/path/to/ca-bundle.crt
```

**In `connectchain.config.yml`:**
```yaml
cert:
  ca_bundle: ${REQUESTS_CA_BUNDLE}

models:
  '1':
    provider: openai
    type: chat
    engine: gpt-4
    model_name: gpt-4
    api_version: 2024-02-15-preview
    api_base: ${AZURE_OPENAI_ENDPOINT}
```

## Multiple Model Configurations

You can define multiple model configurations and switch between them:

**In `connectchain.config.yml`:**
```yaml
models:
  '1':  # Default model
    provider: openai
    type: chat
    engine: gpt-4
    model_name: gpt-4
    api_version: 2024-02-15-preview
    api_base: ${AZURE_OPENAI_ENDPOINT}

  '2':  # Alternative model (e.g., different deployment)
    provider: openai
    type: chat
    engine: gpt-4-turbo
    model_name: gpt-4-turbo
    api_version: 2024-02-15-preview
    api_base: ${AZURE_OPENAI_ENDPOINT_2}
    eas:
      id_key: CONSUMER_ID2
      secret_key: CONSUMER_SECRET2
```

**In `src/config/config.yaml`:**
```yaml
connectchain:
  model_index: "2"  # Use model '2' instead of '1'
```

## Usage

Once configured, the system automatically uses ConnectChain for all LLM calls. The API remains the same:

```python
from src import Text2SQLAgent

# Initialize agent (automatically uses ConnectChain)
agent = Text2SQLAgent()

# Query as usual - ConnectChain is used under the hood
result = agent.query("Show me top 5 customers by sales")

print(result["sql"])
print(result["results"])
```

## Switching Between ConnectChain and Direct Azure OpenAI

To switch between ConnectChain and direct Azure OpenAI:

### Use ConnectChain:

**In `.env`:**
```bash
USE_CONNECTCHAIN=true
```

**Or in `src/config/config.yaml`:**
```yaml
llm:
  use_connectchain: true
```

### Use Direct Azure OpenAI:

**In `.env`:**
```bash
USE_CONNECTCHAIN=false
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_DEPLOYMENT=gpt-4
```

**Or in `src/config/config.yaml`:**
```yaml
llm:
  use_connectchain: false

azure_openai:
  endpoint: "..."
  api_key: "..."
  deployment_name: "gpt-4"
```

## Troubleshooting

### Error: "Failed to create ConnectChain orchestrator"

**Solution:** Verify that `connectchain.config.yml` exists and is properly formatted. Check that all required fields are present.

### Error: "ConnectChain API unavailable"

**Solution:**
1. Check your network connectivity
2. Verify proxy settings if behind a corporate firewall
3. Ensure credentials (EAS or API key) are correct
4. Check certificate configuration if using custom certs

### Sessions are Saved on Failure

ConnectChain includes the same retry logic and session management as the Azure client. If API calls fail:
- Sessions are automatically saved
- You can resume with `agent.query_with_correction(session_id=...)`
- Check logs for detailed error information

### Temperature/Max Tokens Not Working

**Note:** ConnectChain may not support dynamic temperature and max_tokens overrides. These are configured in `connectchain.config.yml` or `config.yaml` and apply to all requests.

## Best Practices

1. **Use Environment Variables** for sensitive data (credentials, endpoints)
2. **Test Configuration** with a simple query before deploying
3. **Monitor Logs** for ConnectChain-specific messages
4. **Keep Config Files in Sync** - ensure `connectchain.config.yml` and `config.yaml` are consistent
5. **Use EAS** when available in your enterprise environment for better security

## Migration from Direct Azure OpenAI

If you're migrating from direct Azure OpenAI:

1. ✅ Install ConnectChain: `pip install connectchain`
2. ✅ Create `connectchain.config.yml` (template provided)
3. ✅ Update `.env` with `USE_CONNECTCHAIN=true`
4. ✅ Configure credentials (EAS or direct API)
5. ✅ Test with a simple query
6. ✅ No code changes required - same API!

## Support

- **ConnectChain Documentation:** https://github.com/americanexpress/connectchain
- **Text-to-SQL Documentation:** See `AGENT_GUIDE.md`
- **Issues:** Check logs in `logs/text2sql.log`

## Summary

ConnectChain integration provides enterprise-grade LLM access with:
- ✅ Same API as before - no code changes
- ✅ Enterprise authentication support
- ✅ Proxy and certificate management
- ✅ Centralized configuration
- ✅ Automatic retry logic and session management

The system seamlessly switches between ConnectChain and direct Azure OpenAI based on configuration.
