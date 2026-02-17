# Text-to-SQL Agent

A production-ready, enterprise-grade system for converting natural language queries to SQL using ConnectChain (AMEX enterprise AI framework) and Google BigQuery.

## Features

### Core Capabilities
- **Natural Language to SQL**: Convert user queries to optimized BigQuery SQL
- **Semantic Join Inference**: Automatically infer table joins without explicit foreign keys
- **Multi-Step Reasoning**: Break down complex queries into exploration steps
- **Human-in-the-Loop**: Interactive clarification when ambiguity is detected
- **Session Management**: Full session persistence with resume capability
- **Error Recovery**: Automatic retry with exponential backoff for API failures

### Enterprise Features
- **LLM Integration**: **ConnectChain** (AMEX enterprise framework) - EAS authentication, proxy config, and certificate management
- **Retry Logic**: Production-ready with exponential backoff and checkpointing
- **BigQuery Support**: Optimized for Google BigQuery with cost estimation
- **Schema Management**: Load table/column metadata from Excel files
- **Correction System**: Learn from user corrections to improve accuracy
- **Comprehensive Logging**: Enterprise-grade logging with sensitive data masking
- **Configuration Management**: Flexible config via YAML and environment variables

## Architecture

```
text2sql/
├── src/
│   ├── config/          # Configuration management
│   ├── core/            # Session and state machine
│   ├── schema/          # Schema parsing and management
│   ├── llm/             # ConnectChain client with retry
│   ├── database/        # BigQuery client
│   ├── reasoning/       # Join inference and query understanding
│   ├── correction/      # User correction parsing
│   ├── tools/           # LangChain custom tools
│   └── utils/           # Utilities (logging, retry, exceptions)
├── sessions/            # Session storage directory
├── cache/               # Schema cache
├── examples/            # Usage examples
└── tests/               # Unit tests
```

## Installation

### Prerequisites
- Python 3.9+
- ConnectChain configuration (for LLM access in enterprise environment)
- Google Cloud Platform account with BigQuery enabled
- Service account with BigQuery read permissions

### Setup

1. Clone the repository:
```bash
cd text2sql
```

2. Create and activate virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Install the package:
```bash
pip install -e .
```

5. Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your credentials
```

Required environment variables:
- `HTTP_PROXY`: Enterprise proxy server (required for corporate network)
- `HTTPS_PROXY`: Enterprise HTTPS proxy server
- `CONFIG_PATH`: Path to ConnectChain configuration file (default: `connectchain.config.yml`)
- `WORKDIR`: Working directory for ConnectChain (default: `.`)
- `GCP_PROJECT_ID`: Your GCP project ID
- `BIGQUERY_DATASET`: Your BigQuery dataset name
- `GOOGLE_APPLICATION_CREDENTIALS`: Path to service account JSON
- `SCHEMA_DIRECTORY`: Path to directory containing schema Excel files

### ConnectChain Setup (AMEX Enterprise - REQUIRED)

The system uses **ConnectChain** for all LLM interactions in the enterprise environment:

1. Configure `connectchain.config.yml` with your model settings
2. Add proxy configuration to `.env` (HTTP_PROXY, HTTPS_PROXY)
3. Add EAS credentials if required (see [CONNECTCHAIN_SETUP.md](CONNECTCHAIN_SETUP.md))
4. The system automatically uses ConnectChain - no code changes needed!

For detailed ConnectChain setup instructions, see **[CONNECTCHAIN_SETUP.md](CONNECTCHAIN_SETUP.md)**

ConnectChain provides:
- ✅ **EAS (Enterprise Auth Service)** integration
- ✅ **Proxy configuration** support
- ✅ **Certificate management**
- ✅ **Centralized LLM configuration**

For more on ConnectChain: https://github.com/americanexpress/connectchain

## Excel Schema Format

The system loads schema from a **directory containing multiple Excel files**, where:
- **Each Excel file = ONE table**
- **Filename (without .xlsx) = Table name in BigQuery**

### Directory Structure
```
schema_directory/
├── Customers.xlsx          # Table: Customers
├── Orders.xlsx             # Table: Orders
├── Products.xlsx           # Table: Products
└── ...
```

### Each Excel File Contains Two Sheets:

#### Sheet 1: "General Information" (Optional)
Table-level metadata:
- Description
- Business Context

#### Sheet 2: "Variables" (Required)
Column-level metadata with these columns:
- **Name**: Column name (required)
- **Attribute Business Name**: Business-friendly name (optional)
- **Description**: Column description (optional)
- **TYPE**: Data type - STRING, INTEGER, FLOAT, DATE, BOOLEAN, etc. (required)
- **PII**: Y/N - Is this personally identifiable information?
- **Entitlement**: Access control information (optional)
- **MANDATORY**: Y/N - Is this column mandatory?
- **PARTITION**: Y/N - Is this a partition column?
- **PRIMARY**: Y/N - Is this a primary key?

**Note**: "Table Name" column is NOT needed - the filename is the table name.

📘 **See [SCHEMA_FORMAT.md](SCHEMA_FORMAT.md) for detailed schema documentation and examples.**

## Quick Start

### Basic Usage

```python
from src import schema_loader, bigquery_client, llm_client, JoinInference
from src.reasoning.join_inference import JoinInference

# 1. Load schema from directory (one Excel file per table)
schema = schema_loader.load_from_excel(
    schema_dir="path/to/schema_directory"
)

# 2. Initialize components
join_inference = JoinInference(schema)

# 3. Infer joins between tables
joins = join_inference.infer_joins("Sales", "Customers")
print(f"Found {len(joins)} possible joins")
for join in joins:
    print(f"  {join} - confidence: {join.confidence:.2f}")

# 4. Execute a query
result = bigquery_client.execute_query("""
    SELECT c.customer_name, SUM(s.amount) as total
    FROM Sales s
    JOIN Customers c ON s.customer_id = c.id
    GROUP BY c.customer_name
""")

if result["success"]:
    print(f"Query returned {result['row_count']} rows")
    for row in result["rows"]:
        print(row)
```

### Session Management

```python
from src.core import session_manager, Session, AgentState

# Create a new session
session = session_manager.create_session("Show me sales by region")

# Add messages and track progress
session.add_message("user", "Show me sales by region")
session.state_machine.transition_to(AgentState.QUERY_UNDERSTANDING)

# Save session
session_manager.save_session(session)

# List sessions
sessions = session_manager.list_sessions()
for s in sessions:
    print(f"{s['session_id']}: {s['query']} - {s['status']}")

# Resume a session
resumed = session_manager.load_session(session.session_id)
print(f"Resumed session at state: {resumed.state_machine.current_state.value}")
```

### Handling Corrections

```python
from src.correction import CorrectionParser

# Parse user correction
correction = CorrectionParser.parse(
    "join Sales.customer_id with Customers.id"
)

# Add to session
session.add_correction(correction)

# Or use structured format
correction_dict = {
    "type": "join",
    "tables": ["Sales", "Customers"],
    "join_condition": "Sales.customer_id = Customers.id"
}
correction = CorrectionParser.parse_dict(correction_dict)
```

### Retry and Error Handling

```python
from src.llm import azure_client
from src.utils import RetryExhaustedError, FatalError

try:
    response = azure_client.chat_completion(
        messages=[
            {"role": "user", "content": "Explain this schema"}
        ],
        session=session
    )
    print(response)

except RetryExhaustedError as e:
    print(f"API unavailable: {e}")
    print(f"Session saved: {session.session_id}")
    print("You can resume later with: session_manager.load_session(session_id)")

except FatalError as e:
    print(f"Non-recoverable error: {e}")
```

## Configuration

### YAML Configuration
Edit `src/config/config.yaml` to customize:
- Retry policy (max attempts, delays, backoff)
- Session retention periods
- Agent behavior (max iterations, confidence thresholds)
- Logging settings

### Environment Variables
Environment variables override YAML settings:
- `AZURE_OPENAI_*`: Azure OpenAI settings
- `GCP_PROJECT_ID`, `BIGQUERY_DATASET`: BigQuery settings
- `SCHEMA_EXCEL_PATH`: Schema file path

## Advanced Usage

### Custom Confidence Threshold

```python
from src.reasoning import JoinInference

# Use custom confidence threshold for join inference
join_inference = JoinInference(
    schema=schema,
    confidence_threshold=0.85  # Higher threshold = more strict
)
```

### Query Cost Estimation

```python
# Estimate query cost before execution
cost_info = bigquery_client.estimate_query_cost(sql_query)
print(f"Estimated cost: ${cost_info['estimated_cost_usd']:.4f}")
print(f"Bytes to process: {cost_info['readable_size']}")

# Execute with max bytes limit (safety)
result = bigquery_client.execute_query(
    sql_query,
    max_results=1000  # Limit results
)
```

### Session Cleanup

```python
# Clean up old sessions based on retention policy
deleted_count = session_manager.cleanup_old_sessions()
print(f"Cleaned up {deleted_count} old sessions")
```

## Testing

Run unit tests:
```bash
pytest tests/
```

Run with coverage:
```bash
pytest --cov=src --cov-report=html tests/
```

## Best Practices

### Security
1. Never commit `.env` file or credentials
2. Use service accounts with minimal required permissions
3. Enable sensitive data masking in logs (default: enabled)
4. Review PII flags in schema before querying

### Performance
1. Cache parsed schemas (default: enabled)
2. Set appropriate query timeouts
3. Use cost estimation for expensive queries
4. Limit exploration query results

### Error Handling
1. Always use try-except for API calls
2. Check session status before resuming
3. Implement proper logging
4. Handle ambiguity errors with user clarification

## Troubleshooting

### Common Issues

**Azure OpenAI Connection Errors**
- Verify endpoint and API key in `.env`
- Check network connectivity
- Ensure deployment name is correct

**BigQuery Permission Errors**
- Verify service account has BigQuery Data Viewer role
- Check project ID and dataset name
- Ensure credentials file path is correct

**Schema Parsing Errors**
- Verify Excel file has correct sheet names
- Check required columns exist in Variables sheet
- Ensure no empty table/column names

**Session Not Found**
- Check session storage path exists
- Verify session ID is correct
- Look for session files in `sessions/` directory

## Architecture Decisions

### Why File-Based Sessions?
- Simple deployment (no database required)
- Easy debugging (human-readable JSON)
- Suitable for moderate scale
- Can migrate to database later if needed

### Why Semantic Join Inference?
- Real-world schemas often lack explicit foreign keys
- Business names and descriptions provide valuable context
- LLM can understand semantic relationships
- Fallback to heuristics when LLM unavailable

### Why Multi-Step Reasoning?
- Complex queries benefit from exploration
- Reduces hallucination by validating assumptions
- Allows iterative refinement
- Better handles ambiguous requests

## Future Enhancements

- [ ] Web UI for interactive query building
- [ ] Query history and favorites
- [ ] Multi-table join optimization
- [ ] Query result caching
- [ ] Advanced analytics on query patterns
- [ ] Support for other LLM providers
- [ ] Database backend for sessions (PostgreSQL)
- [ ] Real-time collaboration features

## License

[Your License Here]

## Support

For issues, questions, or contributions, please contact the AMEX Data Engineering Team.

## Acknowledgments

Built with:
- [LangChain](https://github.com/langchain-ai/langchain) v0.3.0
- [Azure OpenAI](https://azure.microsoft.com/en-us/products/ai-services/openai-service)
- [Google Cloud BigQuery](https://cloud.google.com/bigquery)
