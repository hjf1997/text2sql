# Text-to-SQL Agent - Architecture Documentation

## System Overview

This document describes the architecture and design decisions for the Text-to-SQL Agent system.

## Design Principles

1. **Modularity**: Each component has a single responsibility and clear interfaces
2. **Extensibility**: Easy to add new features, databases, or LLM providers
3. **Resilience**: Graceful error handling with automatic retry and recovery
4. **Enterprise-Ready**: Production-grade logging, configuration, and security
5. **Testability**: Components designed for easy unit and integration testing

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Application                         │
│                    (2 lines of code)                            │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Text2SQLAgent Orchestrator                    │
│  (Coordinates entire workflow, manages state, handles errors)   │
└───────┬─────────┬──────────┬──────────┬────────────┬───────────┘
        │         │          │          │            │
        ▼         ▼          ▼          ▼            ▼
    ┌────────┐ ┌─────┐ ┌─────────┐ ┌────────┐ ┌──────────┐
    │Schema  │ │Query│ │  Join   │ │  SQL   │ │BigQuery  │
    │Loader  │ │Under│ │Inference│ │Generator│ │ Client   │
    │        │ │stand│ │         │ │        │ │          │
    └────────┘ └──┬──┘ └────┬────┘ └───┬────┘ └──────────┘
                  │         │          │
                  │         │          │
                  ▼         ▼          ▼
            ┌──────────────────────────────┐
            │     LLM Client (Multi-       │
            │     Provider Support)        │
            └────────┬──────────────────────┘
                     │
                     ▼
            ┌──────────────────────┐
            │    ConnectChain      │
            │  (EAS/Proxy/Certs)   │
            │ AMEX Enterprise Only │
            └──────────────────────┘
                     │
                     ▼
                 ┌─────────────────┐
                 │   LLM Backend   │
                 └─────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                   Cross-Session Memory System                    │
│     (Learns from past queries, transforms tables, informs LLM)  │
└───────────────────────────┬─────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
   ┌─────────┐      ┌──────────────┐    ┌──────────────┐
   │ Lesson  │      │Table Mapper  │    │Lesson Learner│
   │Repository│     │(Transforms)  │    │(Extracts)    │
   └─────────┘      └──────────────┘    └──────────────┘
        │                   │                   │
        ▼                   ▼                   ▼
┌──────────────┐   ┌───────────────┐   ┌───────────────┐
│Manual Lessons│   │Auto-Transform │   │Learn from     │
│(YAML)        │   │Tables         │   │Sessions       │
└──────────────┘   └───────────────┘   └───────────────┘
```

**Data Flow**:
1. User → Orchestrator: Natural language query
2. Orchestrator → Schema Loader: Get schema metadata
3. Orchestrator → Query Understanding (via LLM): Identify tables/columns
4. Orchestrator → Memory System: Transform table names (e.g., Customers → PROD_Customers)
5. Orchestrator → Join Inference: Find table relationships
6. Orchestrator → Memory System: Get relevant lessons for LLM context
7. Orchestrator → SQL Generator (via LLM): Generate BigQuery SQL with lessons
8. Orchestrator → BigQuery Client: Validate and execute
9. Orchestrator → Memory System: Learn patterns from session
10. Orchestrator → User: Return SQL + results

**LLM Provider**:
- ConnectChain (AMEX enterprise framework) - REQUIRED
- Provides: EAS authentication, proxy support, certificate management
- Configuration: `connectchain.config.yml`

---

## Architecture Layers

### 1. Configuration Layer (`src/config/`)

**Purpose**: Centralized configuration management

**Components**:
- `settings.py`: Singleton configuration manager
- `config.yaml`: Default configuration values

**Key Features**:
- Environment variable overrides
- Validation of required settings
- Dot-notation access (`settings.get("connectchain.config_path")`)

**Design Decision**: Singleton pattern ensures consistent configuration across the application.

---

### 2. Data Models Layer (`src/schema/`, `src/core/`, `src/correction/`)

**Purpose**: Domain models and data structures

**Key Models**:

#### Schema Models (`src/schema/models.py`)
- `Column`: Column metadata with business names, types, constraints
- `Table`: Table with columns and relationships
- `Schema`: Complete database schema
- `JoinCandidate`: Potential join with confidence score

#### Core Models (`src/core/`)
- `AgentState`: Enum of execution states
- `AgentStateMachine`: State transitions with validation
- `Session`: Complete session state with persistence

#### Correction Models (`src/correction/models.py`)
- `Correction`: Base correction class
- `JoinClarification`: Specific join corrections
- `ColumnMapping`: Column name mappings
- `NaturalLanguageCorrection`: Free-form corrections

**Design Decision**: Rich domain models with behavior (not just data classes) enable better encapsulation.

---

### 3. Infrastructure Layer

#### Schema Management (`src/schema/`)

**Purpose**: Load and manage database schema

**Flow**:
```
Excel File → ExcelSchemaParser → Schema Objects → SchemaLoader (with caching)
```

**Key Features**:
- Flexible column mapping (handles various Excel formats)
- Caching to avoid repeated parsing
- Support for table descriptions and business context

**Design Decision**: Excel as source allows non-technical users to maintain schema metadata.

#### Session Management (`src/core/session.py`)

**Purpose**: Persist and restore agent execution state

**Storage Strategy**: File-based JSON (Option A)
- Simple deployment (no database required)
- Human-readable for debugging
- Suitable for moderate scale

**Session Contents**:
- Original query and context
- Conversation history
- State machine state
- Intermediate results
- Corrections and constraints
- SQL attempts

**Design Decision**: File-based storage chosen for simplicity; can migrate to database later.

#### Database Layer (`src/database/`)

**Purpose**: Execute SQL queries on BigQuery

**Key Features**:
- Query validation (dry-run)
- Cost estimation
- Timeout and resource limits
- Comprehensive error handling

**Design Decision**: Abstracted client allows switching databases in the future.

---

### 4. LLM Integration Layer (`src/llm/`)

#### ConnectChain (Enterprise LLM Access - REQUIRED)

The system uses **ConnectChain** (AMEX enterprise framework) for all LLM interactions.

**Key Features**:
- EAS (Enterprise Auth Service) integration
- Proxy configuration support for corporate networks
- Certificate management
- Automatic retry with exponential backoff
- Session checkpointing before/after calls
- Recoverable vs. fatal error distinction

**Retry Strategy**:
```
Attempt 1: immediate
Attempt 2: 2s + jitter
Attempt 3: 4s + jitter
Attempt 4: 8s + jitter
Attempt 5: 16s + jitter
Max: 60s
```

#### ConnectChain Client (`connectchain_client.py`)

**Purpose**: Enterprise-grade LLM access via ConnectChain framework

**Architecture**:
```
Application → ResilientConnectChain → PortableOrchestrator → LLM Backend
```

**Design Decision**: Tight integration with session management enables seamless resume after API failures.

#### LLM Client Interface (`__init__.py`)

**Purpose**: Provide unified interface for LLM access

**Interface**:
```python
llm_client = connectchain_client  # ConnectChain is the only provider
response = llm_client.chat_completion(messages, session)
```

**Design Decision**: Single interface for both providers simplifies application code.

#### Prompts (`prompts.py`)

**Purpose**: Prompt templates for various tasks

**Templates**:
- Query understanding (table/column identification)
- Join inference
- SQL generation
- Ambiguity detection
- Failure summarization

**Design Decision**: Centralized prompts enable easy A/B testing and optimization.

---

### 5. Orchestration Layer (`src/agent/`)

#### Text2SQLAgent (`orchestrator.py`)

**Purpose**: Fully automated orchestration of the entire text-to-SQL workflow

**Key Features**:
- End-to-end automation (no manual steps)
- Single `query()` method interface
- Automatic table identification via LLM
- Automatic join inference
- Automatic SQL generation via LLM
- Session management and error handling
- Support for corrections and ambiguity resolution

**Main Methods**:

```python
class Text2SQLAgent:
    def query(
        user_query: str,
        execute: bool = True,
        return_session: bool = False
    ) -> Dict[str, Any]:
        """Execute complete text-to-SQL workflow."""
        # 1. Query Understanding (LLM)
        # 2. Join Inference (automatic)
        # 3. SQL Generation (LLM)
        # 4. Validation & Execution

    def query_with_correction(
        session_id: str,
        correction: str,
        execute: bool = True
    ) -> Dict[str, Any]:
        """Resume session with user correction."""
```

**Workflow Coordination**:
```
User Query
    ↓
QueryUnderstanding (LLM identifies tables/columns)
    ↓
JoinInference (automatic semantic matching)
    ↓
SQLGenerator (LLM generates BigQuery SQL)
    ↓
BigQueryClient (validate & execute)
    ↓
Results + Session
```

**Design Decision**: Orchestrator pattern encapsulates complexity, providing simple API while coordinating multiple subsystems.

---

### 6. Reasoning Layer (`src/reasoning/`)

#### Query Understanding (`query_understanding.py`)

**Purpose**: Analyze natural language queries to identify tables and columns

**Process**:
1. Send query + schema to LLM
2. LLM identifies:
   - Required tables
   - Required columns
   - Filter conditions
   - Join requirements
   - Aggregations needed
3. Parse LLM response into structured format

**Output Format**:
```python
{
    "tables": ["Customers", "Orders"],
    "columns": {
        "Customers": ["customer_id", "name"],
        "Orders": ["order_id", "customer_id", "total"]
    },
    "joins_needed": True,
    "aggregations": ["SUM(total)"],
    "filters": ["year = 2024"]
}
```

**Design Decision**: LLM-based understanding captures semantic intent better than pattern matching.

#### SQL Generator (`sql_generator.py`)

**Purpose**: Generate BigQuery SQL from query understanding and join information

**Process**:
1. Receive:
   - User query
   - Identified tables/columns
   - Join conditions
   - Constraints from corrections
2. Build prompt with full context
3. LLM generates BigQuery-compliant SQL
4. Extract and clean SQL from response

**Key Features**:
- Context-aware generation (uses schema metadata)
- Constraint application (from user corrections)
- BigQuery-specific syntax
- Handles complex queries (aggregations, subqueries, CTEs)

**Design Decision**: LLM generation provides flexibility for complex queries while maintaining correctness.

#### Join Inference (`join_inference.py`)

**Purpose**: Infer table joins without explicit foreign keys

**Two-Phase Approach**:

1. **Heuristic Phase**:
   - Column name similarity (SequenceMatcher)
   - Business name matching
   - Foreign key naming patterns
   - Primary key indicators
   - Type compatibility checking

2. **LLM Phase** (when needed):
   - Semantic understanding
   - Context from descriptions
   - User constraint application

**Confidence Calculation**:
```
confidence = (name_similarity × 0.4) +
             (business_name_similarity × 0.25) +
             (primary_key_bonus × 0.2) +
             (fk_pattern_bonus × 0.15)
```

**Ambiguity Handling**:
- Detects multiple high-confidence joins (≥0.7, within 0.1)
- Raises `AmbiguityError` with options
- User chooses correct join

**Design Decision**: Hybrid heuristic + LLM approach balances cost, latency, and accuracy.

---

### 7. Correction System (`src/correction/`)

**Purpose**: Parse and apply user corrections

**Supported Formats**:

1. **Structured**:
   ```python
   {
       "type": "join",
       "tables": ["A", "B"],
       "join_condition": "A.id = B.a_id"
   }
   ```

2. **Natural Language**:
   - "join A.id with B.a_id"
   - "region means Customers.geo_area"
   - "use customer_id, not account_number"

**Parsing Strategy**:
1. Try regex patterns for structured corrections
2. Fall back to natural language

**Application**:
- Corrections converted to constraint strings
- Added to session as "hard constraints"
- Included in LLM prompts with high priority

**Design Decision**: Flexible input formats improve user experience.

---

### 8. Cross-Session Memory System (`src/memory/`)

**Purpose**: Learn from past queries and build institutional knowledge over time

#### Problem Solved

**Scenario**: Company's BigQuery tables have prefixes (like `PROD_`, `DWH_`, etc.) that don't appear in the Excel schema files.

**Without Memory**:
1. User asks: "Show me all customers"
2. System generates: `SELECT * FROM Customers`
3. Error: "Table `Customers` not found" ❌
4. Manual correction needed every time

**With Memory**:
1. First time: Error occurs, user corrects or system retries with prefix
2. System learns: `Customers` → `PROD_Customers`
3. Next time: System automatically uses `PROD_Customers` ✅
4. Future queries: No errors, no manual corrections needed

#### Two-Tier Architecture

The memory system uses a hierarchical approach:

```
┌─────────────────────────────────────────────────────────────┐
│                     Memory System                            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Tier 1: Manual Lessons                                     │
│  ├─ File: config/lessons_learned.yaml                       │
│  ├─ Confidence: 0.90-1.00 (High)                           │
│  ├─ Source: Manually configured by admins                   │
│  └─ Use Case: Known, validated patterns                     │
│                                                              │
│  Tier 2: Auto-Learned Lessons                              │
│  ├─ File: memory/learned_lessons.json                       │
│  ├─ Confidence: 0.60-0.90 (Adaptive)                       │
│  ├─ Source: Automatically extracted from queries            │
│  └─ Use Case: Discovered patterns, evolving knowledge       │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Design Decision**: Two-tier system balances human expertise (manual) with automatic learning, enabling both immediate deployment of known patterns and continuous improvement.

#### Components

##### 1. Lesson Models (`models.py`)

**Purpose**: Define lesson types and behavior

**Lesson Types**:

```python
# Base lesson with confidence tracking
class Lesson(BaseModel):
    id: str
    type: LessonType
    content: str
    confidence: float = Field(ge=0.0, le=1.0)
    times_applied: int = 0
    times_successful: int = 0

    def record_usage(self, successful: bool = True):
        """Adjust confidence based on usage."""
        self.times_applied += 1
        if successful:
            self.times_successful += 1
            self.confidence = min(1.0, self.confidence + 0.02)
        else:
            self.confidence = max(0.0, self.confidence - 0.05)

# Table name transformations
class TableMappingLesson(Lesson):
    schema_name: str           # "Customers"
    actual_name: str           # "PROD_Customers"
    prefix: Optional[str]      # "PROD_"
    transformation_rule: str   # "Add 'PROD_' prefix"

# Column name mappings
class ColumnMappingLesson(Lesson):
    table_name: str
    schema_column: str         # "customer_id"
    actual_column: str         # "cust_id"

# Error patterns and fixes
class ErrorPatternLesson(Lesson):
    error_pattern: str         # "Table .* not found"
    suggested_fix: str         # "Add 'PROD_' prefix"

# Successful query patterns
class QueryPatternLesson(Lesson):
    query_type: str
    sql_template: str
    required_tables: List[str]
```

**Key Features**:
- Adaptive confidence scoring (increases with success, decreases with failure)
- Usage statistics tracking
- Pydantic validation for data integrity

##### 2. Lesson Repository (`repository.py`)

**Purpose**: Centralized storage and retrieval of lessons

**Key Methods**:

```python
class LessonRepository:
    def get_all_lessons(self) -> List[Lesson]:
        """Get all lessons (manual + learned)."""

    def get_table_mapping_lessons(
        self, table_name: str
    ) -> List[TableMappingLesson]:
        """Get table mapping lessons sorted by confidence."""

    def get_relevant_lessons(
        self, user_query: str,
        identified_tables: List[str],
        context: Optional[str] = None
    ) -> List[Lesson]:
        """Get lessons relevant to current query."""

    def add_lesson(self, lesson: Lesson, save: bool = True):
        """Add new lesson to repository."""

    def update_lesson_stats(
        self, lesson_id: str,
        successful: bool = True,
        save: bool = True
    ):
        """Update usage statistics for a lesson."""
```

**Storage**:
- Manual lessons: `config/lessons_learned.yaml` (version-controlled)
- Auto-learned: `memory/learned_lessons.json` (dynamically updated)
- Combined in-memory for fast access

**Design Decision**: Dual storage enables both human curation and automatic learning while maintaining single access point.

##### 3. Table Mapper (`table_mapper.py`)

**Purpose**: Apply learned transformations to table names

**Key Methods**:

```python
class TableMapper:
    def transform(self, table_name: str) -> str:
        """Transform table name using highest-confidence lesson."""
        lessons = repository.get_table_mapping_lessons(table_name)
        if lessons:
            best_lesson = lessons[0]  # Already sorted by confidence
            return best_lesson.apply(table_name)
        return table_name

    def transform_multiple(
        self, table_names: List[str]
    ) -> Dict[str, str]:
        """Transform multiple table names."""

    def preview_transformations(
        self, table_names: List[str]
    ) -> List[Dict]:
        """Preview what transformations would be applied."""
```

**Example Usage**:
```python
mapper = TableMapper()
transformed = mapper.transform("Customers")  # Returns: "PROD_Customers"
```

##### 4. Lesson Learner (`learner.py`)

**Purpose**: Automatically extract lessons from completed sessions

**Learning Sources**:

1. **Error Recovery**:
   ```
   Attempt 1: SELECT * FROM Customers → Error: "Table not found"
   Attempt 2: SELECT * FROM PROD_Customers → Success ✓

   → Learned: Customers → PROD_Customers (confidence: 0.80)
   ```

2. **User Corrections**:
   ```
   User: "Use PROD_ prefix for all tables"

   → Learned: Apply PROD_ prefix pattern (confidence: 0.85)
   ```

3. **Successful Patterns**:
   ```
   Query succeeds using PROD_Customers

   → Reinforced: Confidence increased from 0.80 → 0.82
   ```

**Key Methods**:

```python
class LessonLearner:
    def learn_from_session(self, session: Session) -> List[Lesson]:
        """Extract all lessons from a session."""
        lessons = []

        # Learn from error → success patterns
        if self._had_error_recovery(session):
            lessons.extend(self._learn_from_error_recovery(session))

        # Learn from user corrections
        if session.corrections:
            lessons.extend(self._learn_from_corrections(session))

        # Reinforce lessons that were successfully used
        if session.final_sql and session.state_machine.is_completed():
            self._reinforce_used_lessons(session)

        return lessons
```

**Pattern Extraction**:
- Analyzes SQL attempts to find transformations
- Parses correction text for patterns (regex + heuristics)
- Detects table prefixes automatically
- Infers column mappings from corrections

**Design Decision**: Automatic extraction reduces manual configuration while learning continuously from real usage.

#### Integration with Workflow

The memory system integrates seamlessly into the existing workflow:

```
User Query
    ↓
QueryUnderstanding (LLM identifies tables)
    ↓
┌─────────────────────────────────────────┐
│ TableMapper.transform_multiple()         │  ← Memory Applied
│ (Schema tables → Actual database tables) │
└─────────────────────────────────────────┘
    ↓
JoinInference (using transformed table names)
    ↓
┌─────────────────────────────────────────┐
│ LessonRepository.get_relevant_lessons()  │  ← Memory Applied
│ (Get lessons for prompt context)         │
└─────────────────────────────────────────┘
    ↓
SQLGenerator (with transformed tables + lessons in prompt)
    ↓
Validation & Execution
    ↓
┌─────────────────────────────────────────┐
│ LessonLearner.learn_from_session()       │  ← Memory Updated
│ (Extract new lessons)                    │
└─────────────────────────────────────────┘
    ↓
Results
```

**In SQL Generator** (`sql_generator.py`):

```python
def generate(self, user_query, identified_tables, ...):
    # Apply table transformations
    if self.apply_memory and self.table_mapper:
        transformations = self.table_mapper.transform_multiple(identified_tables)
        transformed_tables = list(transformations.values())

    # Get relevant lessons
    lessons = lesson_repository.get_relevant_lessons(
        user_query=user_query,
        identified_tables=identified_tables
    )

    # Include lessons in prompt
    prompt = PromptTemplates.sql_generation(
        ...,
        tables=transformed_tables,  # Use transformed names
        lessons=lessons,            # Include as context
    )
```

**In Orchestrator** (`orchestrator.py`):

```python
def query(self, user_query: str, ...):
    # ... process query ...

    # After successful completion, learn from session
    if success:
        lessons_learned = self.lesson_learner.learn_from_session(session)
        if lessons_learned:
            logger.info(f"Learned {len(lessons_learned)} new patterns")
```

**Design Decision**: Memory is applied automatically at key points without requiring explicit user action.

#### Confidence Scoring

Confidence adjusts dynamically based on usage:

**Initial Confidence** (by source):
- Manual lessons: 0.90-1.00
- Auto-learned from errors: 0.80
- Auto-learned from corrections: 0.85

**After Each Use**:
```python
if successful:
    confidence = min(1.0, confidence + 0.02)  # Increase
else:
    confidence = max(0.0, confidence - 0.05)  # Decrease (faster)
```

**Example Evolution**:
```
Use 1: Confidence = 0.80 → Success → 0.82
Use 2: Confidence = 0.82 → Success → 0.84
Use 3: Confidence = 0.84 → Success → 0.86
...
Use 10: Confidence = 0.94 → Success → 0.96
Use 11: Confidence = 0.96 → Failure → 0.91  (drops faster)
```

**Design Decision**: Confidence increases slowly with success but decreases faster with failure, ensuring bad patterns are quickly de-prioritized.

#### Learning Examples

##### Example 1: Error Recovery Learning

**Session Flow**:
```
1. Query: "Show all customers"
2. Attempt 1: SELECT * FROM Customers
   → Error: "Table `project.dataset.Customers` not found"
3. Attempt 2: SELECT * FROM PROD_Customers
   → Success ✓
```

**Lesson Learned**:
```python
TableMappingLesson(
    schema_name="Customers",
    actual_name="PROD_Customers",
    prefix="PROD_",
    transformation_rule="Add 'PROD_' prefix to table names",
    confidence=0.80,
    source="auto_learned"
)
```

**Next Query**: System automatically transforms `Customers` → `PROD_Customers`

##### Example 2: User Correction Learning

**Session Flow**:
```
1. Query: "Show sales data"
2. Generated: SELECT * FROM Sales
3. User correction: "Use DWH_ prefix for sales tables"
```

**Lesson Learned**:
```python
TableMappingLesson(
    schema_name="Sales",
    actual_name="DWH_Sales",
    prefix="DWH_",
    confidence=0.85,
    source="correction"
)
```

##### Example 3: Pattern Reinforcement

**Over Time**:
```
Query 1: Uses PROD_Customers → Success → Confidence 0.80 → 0.82
Query 2: Uses PROD_Customers → Success → Confidence 0.82 → 0.84
Query 3: Uses PROD_Customers → Success → Confidence 0.84 → 0.86
...
After 10 successful uses: Confidence reaches 0.96
```

**Pattern becomes highly trusted** and may be promoted to manual configuration.

#### Benefits

✅ **Solves table prefix problem**: Automatically maps schema to actual tables

✅ **Learns continuously**: Builds knowledge from every query

✅ **Self-improving**: Confidence adjusts based on success/failure

✅ **Transparent**: All patterns are visible and manageable

✅ **No code changes**: Works automatically with existing agent

✅ **Two-tier flexibility**: Manual rules + auto-learning

✅ **Reduces errors**: Common mistakes are remembered and avoided

✅ **Reduces manual work**: Automatic corrections eliminate repetitive fixes

#### Monitoring and Management

**View Learned Patterns**:
```python
from src.memory import lesson_repository

# Get all lessons
lessons = lesson_repository.get_all_lessons()

# Get table-specific lessons
customer_lessons = lesson_repository.get_table_mapping_lessons("Customers")

# Check confidence and usage
for lesson in customer_lessons:
    print(f"Confidence: {lesson.confidence:.0%}")
    print(f"Success Rate: {lesson.success_rate:.0%}")
```

**Promote Successful Patterns**:

When an auto-learned lesson has:
- High confidence (>0.90)
- High success rate (>95%)
- Many successful uses (>20)

Consider promoting it to `config/lessons_learned.yaml` for version control.

**Configuration Files**:
- **Manual lessons**: `config/lessons_learned.yaml` (version-controlled, high confidence)
- **Auto-learned lessons**: `memory/learned_lessons.json` (dynamically updated, adaptive confidence)

**Design Decision**: Separate files enable human curation of validated patterns while allowing system to learn continuously.

---

### 9. Utilities Layer (`src/utils/`)

#### Error Handling (`exceptions.py`)

**Exception Hierarchy**:
```
Text2SQLError (base)
├── ConfigurationError
├── SchemaError
├── SessionError
├── LLMError
│   ├── RecoverableError (triggers retry)
│   ├── FatalError (no retry)
│   └── RetryExhaustedError
├── BigQueryError
├── JoinInferenceError
├── AmbiguityError (special: requires user input)
├── MaxIterationsError
├── CorrectionError
└── ValidationError
```

**Design Decision**: Rich exception types enable fine-grained error handling.

#### Retry Logic (`retry.py`)

**Components**:
- `RetryConfig`: Configuration for retry behavior
- `@retry_with_backoff`: Decorator for simple cases
- `RetryContext`: Context manager for complex cases with state tracking

**Features**:
- Exponential backoff with jitter
- Configurable exception types
- Callback support (e.g., for logging)

**Design Decision**: Multiple interfaces (decorator, context manager) support different use cases.

#### Logging (`logger.py`)

**Features**:
- Structured logging with context
- Sensitive data masking (API keys, passwords)
- Console and file handlers
- Configurable log levels

**Design Decision**: Comprehensive logging crucial for enterprise debugging.

---

## Key Workflows

### Workflow 1: Automated Query Processing (via Orchestrator)

**User Perspective**:
```python
agent = Text2SQLAgent()
result = agent.query("Show me top 5 customers by sales")
```

**Internal Flow**:
```
1. User calls agent.query()
   ↓
2. Orchestrator initializes
   - Create Session
   - Load Schema (cached)
   - Transition to QUERY_UNDERSTANDING state
   ↓
3. Query Understanding Module (LLM)
   - Send query + schema to LLM
   - Parse response
   - Extract: tables, columns, filters, aggregations
   - Transition to JOIN_INFERENCE state
   ↓
4. Join Inference Module
   - Heuristic matching (column names, types)
   - LLM semantic analysis (if needed)
   - Detect ambiguity → raise AmbiguityError if multiple options
   - Transition to GENERATING_SQL state
   ↓
5. SQL Generator Module (LLM)
   - Build context: query + schema + tables + joins + constraints
   - Send to LLM
   - Parse and clean SQL
   - Transition to EXECUTING_QUERY state
   ↓
6. BigQuery Client
   - Validate SQL (dry-run)
   - Estimate cost
   - Execute query (if execute=True)
   ↓
7. Orchestrator returns result
   - Update session (COMPLETED)
   - Save session
   - Return: {success, sql, results, row_count}
```

**Design Note**: Orchestrator coordinates all steps automatically; user only needs one method call.

### Workflow 2: Handling Ambiguity (via Orchestrator)

**User Perspective**:
```python
# Initial query
result = agent.query("Show sales with customer data", return_session=True)

# If ambiguity detected: result["success"] == False, result["error"] == "ambiguity"
# User provides correction
result = agent.query_with_correction(
    session_id=result["session_id"],
    correction="Use customer_id to join tables"
)
```

**Internal Flow**:
```
1. Orchestrator calls Join Inference
   ↓
2. Join Inference detects multiple high-confidence options (≥0.7)
   ↓
3. Orchestrator catches AmbiguityError
   - Transition to AWAITING_CORRECTION state
   - Save session with options
   - Return: {success: False, error: "ambiguity", options: [...], session_id}
   ↓
4. User calls query_with_correction()
   ↓
5. Orchestrator loads session
   - Parse correction (CorrectionParser)
   - Convert to constraint string
   - Add to session.hard_constraints
   - Transition back to JOIN_INFERENCE state
   ↓
6. Join Inference (retry with constraint)
   - Heuristic matching now guided by constraint
   - Disambiguation achieved
   ↓
7. Continue to SQL Generation
   - Constraint included in LLM prompt
   - Generate SQL with correct join
   ↓
8. Return successful result
```

**Design Note**: Orchestrator manages state transitions and session persistence automatically.

### Workflow 3: API Failure Recovery

```
1. LLM API call fails (timeout)
   ↓
2. Checkpoint session
   ↓
3. Retry with exponential backoff
   - Attempt 2... 3... 4... 5
   ↓
4. All retries exhausted
   ↓
5. Save session with INTERRUPTED state
   ↓
6. Return recovery instructions to user

[Later, when API is restored]

7. User: "resume session_id"
   ↓
8. Load session from disk
   ↓
9. Restore state machine
   ↓
10. Continue from last successful checkpoint
```

### Workflow 4: Multi-Iteration Reasoning

```
1. Initial query attempt
   ↓
2. Need more information
   ↓
3. Generate exploration query
   - "SELECT DISTINCT category FROM products"
   ↓
4. Execute exploration query
   ↓
5. Store intermediate results
   ↓
6. Use results to refine approach
   ↓
7. Generate next query (iteration 2)
   ↓
8. Repeat until success OR max iterations
```

---

## Extensibility Points

### Adding New Database Support

1. Create new client in `src/database/`
2. Implement interface:
   - `execute_query(sql) → result`
   - `validate_query(sql) → bool`
   - `get_table_info(table) → info`
3. Update configuration
4. Add dialect-specific SQL generation

### Adding New LLM Provider

**Example**: ConnectChain integration demonstrates this pattern

1. Create new client in `src/llm/` (e.g., `my_provider_client.py`)
2. Implement common interface:
   ```python
   class ResilientMyProvider:
       def chat_completion(
           messages: List[Dict[str, str]],
           session: Optional[Session] = None,
           **kwargs
       ) -> str:
           """Make LLM call with retry logic."""
   ```
3. Add retry logic and session management:
   - Use `RetryContext` for exponential backoff
   - Checkpoint session before/after calls
   - Handle recoverable vs. fatal errors
4. Update `src/llm/__init__.py`:
   - Export new client
   - Add to `get_llm_client()` selection logic
5. Update configuration:
   - Add provider settings to `config.yaml`
   - Add environment variables to `.env.example`
6. Update orchestrator (if needed):
   - Usually no changes needed due to common interface

**Design Note**: Common interface enables transparent provider switching.

### Adding New Correction Types

1. Add enum value to `CorrectionType`
2. Create model class (extends `Correction`)
3. Add parsing logic to `CorrectionParser`
4. Add constraint string generation

---

## Configuration Philosophy

**Hierarchy** (highest to lowest priority):
1. Environment variables (runtime)
2. YAML configuration file (deployment)
3. Code defaults (fallback)

**Why?**
- Environment variables: Secrets, deployment-specific settings
- YAML: Shared configuration, tuning parameters
- Defaults: Sensible starting point

---

## Testing Strategy

### Unit Tests
- Schema parsing
- Data model behavior
- Utility functions
- Correction parsing

### Integration Tests
- Schema → BigQuery round-trip
- LLM → Parse response
- Session save → load

### End-to-End Tests
- Complete query workflows
- Error recovery scenarios
- Multi-iteration reasoning

---

## Security Considerations

1. **Credentials**: Never commit secrets; use environment variables
2. **PII**: Flag sensitive columns; mask in logs
3. **SQL Injection**: Parameterized queries (future enhancement)
4. **Access Control**: Respect entitlement flags
5. **Audit Logging**: Comprehensive query history

---

## Performance Optimization

1. **Schema Caching**: Parse Excel once, cache results
2. **Query Validation**: Dry-run before execution
3. **Resource Limits**: Max bytes, timeout, result limits
4. **Exploration Queries**: Limit results (e.g., LIMIT 100)
5. **Session Cleanup**: Automatic deletion of old sessions

---

## Recent Architecture Improvements

### Phase 1.5 (Completed) - Orchestration & Enterprise Integration

#### 1. Text2SQLAgent Orchestrator

**Problem Solved**: Manual coordination of multiple components was error-prone and complex.

**Solution**: Single orchestrator class that automates the entire workflow.

**Benefits**:
- **87% less code** for end users (2 lines vs. 15 lines)
- **Automatic error handling** across all components
- **Consistent state management** with state machine
- **Simplified API** - one method call for everything

**Before**:
```python
# Manual approach - 15+ lines
schema = schema_loader.load_from_excel()
understanding = query_understanding.analyze(query)
tables = understanding["tables"]  # Manual inspection
joins = join_inference.infer_joins(...)  # Manual selection
sql = sql_generator.generate(...)
result = bigquery_client.execute(sql)
```

**After**:
```python
# Automated approach - 2 lines
agent = Text2SQLAgent()
result = agent.query("Show me top customers")
```

#### 2. ConnectChain Integration

**Problem Solved**: Enterprise environments require EAS authentication, proxy configuration, and certificate management.

**Solution**: Multi-provider LLM architecture with ConnectChain support.

**Benefits**:
- **Enterprise-ready**: EAS, proxy, and certificate support
- **Transparent switching**: Same API for both providers
- **Zero code changes**: Toggle via configuration
- **Maintains all features**: Retry logic, session management, etc.

**Architecture**:
```
Application
    ↓
Text2SQLAgent (unchanged)
    ↓
get_llm_client() (auto-selects provider)
    ↓
    ├─→ ResilientConnectChain (enterprise)
    └─→ ResilientAzureOpenAI (direct)
```

#### 3. LLM-Powered Components

**Query Understanding Module**: Replaces manual table/column identification with LLM-based semantic understanding.

**SQL Generator Module**: Uses LLM for context-aware SQL generation instead of template-based approaches.

**Benefits**:
- **Semantic understanding**: Handles synonyms, business terms
- **Flexible**: Works with any schema structure
- **Context-aware**: Uses table descriptions and column metadata
- **Handles complexity**: Multi-table queries, subqueries, aggregations

#### 4. Cross-Session Memory System

**Problem Solved**: Company tables have prefixes (PROD_, DWH_) not in Excel schema files, causing repeated errors.

**Solution**: Two-tier memory system that learns from past queries.

**Architecture**:
```
Manual Lessons (YAML)          Auto-Learned Lessons (JSON)
Confidence: 0.90-1.00          Confidence: 0.60-0.90 (adaptive)
    │                                    │
    └──────────┬──────────────────────┘
               ↓
        Lesson Repository
               ↓
    ┌──────────┴──────────┐
    ↓                     ↓
Table Mapper         Prompt Context
(Transforms tables)  (Informs LLM)
```

**Benefits**:
- **Automatic learning**: Extracts patterns from error recovery and corrections
- **Adaptive confidence**: Increases with success, decreases with failure
- **Continuous improvement**: Builds institutional knowledge over time
- **Transparent**: All lessons visible and manageable
- **Zero manual intervention**: Automatically applied during query processing

**Learning Sources**:
1. **Error Recovery**: Table not found → Retry with prefix → Success → Learn mapping
2. **User Corrections**: "Use PROD_ prefix" → Extract pattern → Apply to future queries
3. **Pattern Reinforcement**: Successful uses increase confidence, failures decrease it

**Integration**:
- **SQL Generation**: Applies table transformations and includes lessons in LLM prompts
- **Post-Query**: Automatically extracts lessons after each session
- **Repository**: Manages both manual (YAML) and learned (JSON) lessons

---

## Future Architecture Improvements

### Phase 2 (Scale)
- PostgreSQL for session storage
- Redis for schema caching
- Distributed processing (Celery)
- Query result caching with TTL

### Phase 3 (Features)
- Query optimization suggestions
- Multi-table join optimization (cost-based)
- Natural language explanations of SQL
- Query templates and saved queries
- Interactive query refinement

### Phase 4 (Enterprise)
- Multi-tenancy with isolation
- Role-based access control (RBAC)
- Audit dashboard and analytics
- Real-time collaboration on queries
- Integration with data catalogs

### Phase 5 (AI Enhancement)
- Fine-tuned models for specific schemas
- Reinforcement learning from corrections
- Automatic index recommendations
- Query performance prediction
- Anomaly detection in generated SQL

---

## Architecture Evolution Summary

```
Version 1.0 (Initial)
├─ Building blocks (manual coordination)
├─ Direct Azure OpenAI only
└─ Required expert knowledge

Version 1.5 (Current)
├─ Orchestrator (automated coordination)
├─ Multi-provider support (Azure + ConnectChain)
├─ LLM-powered understanding & generation
├─ Cross-session memory (learns from past queries)
└─ User-friendly single API

Version 2.0 (Planned)
├─ Scalable infrastructure (PostgreSQL, Redis)
├─ Advanced features (caching, optimization)
├─ Enterprise features (multi-tenancy, RBAC)
└─ AI enhancements (fine-tuning, RL)
```

---

## Conclusion

This architecture balances:
- **Simplicity**: Easy to understand and maintain
- **Robustness**: Handles failures gracefully
- **Extensibility**: Easy to add features and providers
- **Production-Readiness**: Enterprise logging, security, resilience
- **Usability**: Simple API hiding complex orchestration

**Key Achievements**:
- ✅ **Fully Automated**: No manual steps required
- ✅ **Enterprise-Ready**: ConnectChain integration with EAS/proxy/certs
- ✅ **Secure**: All LLM access through enterprise ConnectChain framework
- ✅ **Intelligent**: LLM-powered understanding and generation
- ✅ **Self-Learning**: Cross-session memory learns from past queries
- ✅ **Resilient**: Comprehensive error handling and recovery
- ✅ **Session-Aware**: Full state persistence and resumption

The modular design allows components to evolve independently while maintaining a cohesive system. The orchestrator pattern successfully abstracts complexity, providing a simple interface while coordinating sophisticated workflows.
