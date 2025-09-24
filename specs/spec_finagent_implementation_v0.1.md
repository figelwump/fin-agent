## Implementation Plan for Financial CLI Tools Suite

### Technology Stack
**All tools will be implemented in Python** for consistency and maintainability.

### Project Structure

```
fin-cli/
├── fin-extract/          # PDF extraction tool
│   ├── extractors/       # Bank-specific extractors
│   ├── parsers/          # Table parsing logic
│   └── main.py
├── fin-enhance/          # Smart categorization & import
│   ├── categorizers/     # Dynamic categorization engine
│   ├── reviewers/        # Review modes (interactive, json, auto)
│   └── main.py
├── fin-query/            # SQL query tool
│   ├── queries/          # Saved queries
│   └── main.py
├── fin-analyze/          # Analysis engine
│   ├── analyzers/        # Analysis modules
│   └── main.py
├── fin-export/           # Report generator
│   ├── templates/        # Markdown templates
│   └── main.py
├── shared/               # Shared utilities
│   ├── database.py       # Database schema & migrations
│   ├── models.py         # Data models
│   ├── config.py         # Configuration management
│   └── utils.py
└── tests/
```

### Key Technical Decisions

#### 1. PDF Parsing Strategy

**Approach**: Digital PDFs only (no OCR support)
- Primary library: `pdfplumber` for table extraction
- Fallback: `camelot-py` for complex tables
- Bank-specific extractors for Chase, Bank of America, Mercury

**Implementation Notes**:
- Each bank gets its own extractor class
- Auto-detect bank format from PDF content patterns
- Extract only transaction tables (date, merchant, amount)
- No PII extraction since we only need table data

#### 2. Database Design

**Technology**: SQLite for simplicity
- Single file database at `~/.findata/transactions.db`
- Foreign key constraints enabled
- Indexes on frequently queried columns

**Schema**:
```sql
-- Accounts (auto-detected by fin-extract)
CREATE TABLE accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    institution TEXT NOT NULL,
    account_type TEXT NOT NULL,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_import DATE,
    auto_detected BOOLEAN DEFAULT TRUE
);

-- Dynamic categories table
CREATE TABLE categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    subcategory TEXT NOT NULL,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    transaction_count INTEGER DEFAULT 0,
    last_used DATE,
    user_approved BOOLEAN DEFAULT FALSE,
    auto_generated BOOLEAN DEFAULT TRUE,
    UNIQUE(category, subcategory)
);

-- Transactions
CREATE TABLE transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    merchant TEXT NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    category_id INTEGER,
    account_id INTEGER,
    original_description TEXT,
    import_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    categorization_confidence REAL,
    categorization_method TEXT,
    fingerprint TEXT NOT NULL UNIQUE,
    FOREIGN KEY (account_id) REFERENCES accounts(id),
    FOREIGN KEY (category_id) REFERENCES categories(id)
);

-- Learned merchant patterns
CREATE TABLE merchant_patterns (
    pattern TEXT PRIMARY KEY,
    category_id INTEGER,
    confidence REAL,
    learned_date TIMESTAMP,
    usage_count INTEGER DEFAULT 0,
    FOREIGN KEY (category_id) REFERENCES categories(id)
);

-- Simple migration tracking
CREATE TABLE schema_versions (
    version INTEGER PRIMARY KEY,
    applied_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    description TEXT
);
```

#### 3. Dynamic Categorization System

**Hybrid Approach**: LLM + Rules

**LLM Integration**:
- Primary: OpenAI GPT-4o-mini for cost-effectiveness
- Configurable via config file
- Cached responses to minimize API calls
- Fallback to rules if API unavailable

**Dynamic Category Creation**:
- LLM can suggest new categories based on transaction patterns
- Tracks pending categories until threshold met (3+ transactions)
- Auto-approves high confidence suggestions (>0.85)
- Requires user approval for lower confidence

**Learning System**:
- Saves merchant patterns from user decisions
- Builds confidence scores over time
- Rules checked before LLM to minimize API usage

#### 4. Configuration Management

**Location**: `~/.finconfig/config.yaml`

**Structure**:
```yaml
database:
  path: ~/.findata/transactions.db

extraction:
  auto_detect_accounts: true
  supported_banks: [chase, bofa, mercury]

categorization:
  llm:
    enabled: true
    provider: openai
    model: gpt-4o-mini
    api_key_env: OPENAI_API_KEY
    
  dynamic_categories:
    enabled: true
    min_transactions_for_new: 3
    auto_approve_confidence: 0.85
    max_pending_categories: 20
    
  confidence:
    auto_approve: 0.8
```

#### 5. Migration System

**Simple versioned migrations**:
- Track schema version in database
- Run migrations on tool startup if needed
- Each migration is a SQL script with version number
- No rollback support initially (can add later)

### Tool-Specific Implementation Details

#### fin-extract
- **Input**: PDF files from Chase, BofA, Mercury
- **Output**: CSV with transactions + account detection
- **Key challenges**: 
  - Different table formats per bank
  - Multi-page transaction tables
  - Detecting account info without capturing PII

#### fin-enhance  
- **Input**: CSV files from fin-extract
- **Processing**:
  - Batch transactions for efficient LLM calls
  - Track new category suggestions
  - Three review modes (interactive, json, auto)
- **Key challenges**:
  - Minimizing LLM API calls
  - Building effective category hierarchy
  - Handling ambiguous transactions

#### fin-query
- **Direct SQL execution** on SQLite database
- **Saved queries** for common operations
- **Output formats**: table, CSV, JSON
- **Key features**: Schema inspection, query history

#### fin-analyze
- **Analysis modules**:
  - Spending trends with dynamic categories
  - Category evolution tracking
  - Subscription detection
  - Anomaly detection
  - Category optimization suggestions

#### fin-export
- **Markdown generation** with tables and formatting
- **Template system** for customizable reports
- **Dynamic sections** based on available data
- **Integration-friendly** output for Claude Code

### Development Phases

#### Phase 1: Core Foundation (Week 1)
- Database schema with accounts and dynamic categories
- Basic fin-extract for Chase PDF
- Simple fin-enhance without LLM
- Basic fin-query with direct SQL

#### Phase 2: Intelligence Layer (Week 2)  
- LLM integration for categorization (GPT-4o-mini)
- Dynamic category creation system
- Review queue export (JSON)
- Merchant pattern learning

#### Phase 3: Bank Support & Analysis (Week 3)
- Add BofA and Mercury extractors
- Implement fin-analyze modules
- Subscription detection
- Category evolution tracking

#### Phase 4: Polish & Export (Week 4)
- fin-export with markdown templates
- Configuration management
- Simple migration system
- Comprehensive testing
- Claude Code integration examples

### Technical Stack

```yaml
Core:
  language: Python 3.11+
  database: SQLite
  
PDF Processing:
  - pdfplumber (primary)
  - camelot-py[base] (fallback for complex tables)
  
Categorization:
  - openai (GPT-4o-mini API)
  
CLI Framework:
  - click (CLI framework)
  - rich (terminal formatting)
  
Data Processing:
  - pandas (data manipulation)
  - python-dateutil (date parsing)
  
Configuration:
  - pyyaml (config files)
  - python-dotenv (environment variables)
  
Testing:
  - pytest
  - pytest-mock
```

### Testing Strategy

**Unit Tests**:
- PDF extraction for each bank format
- Category creation logic
- LLM prompt generation
- Database operations

**Integration Tests**:
- End-to-end workflow tests
- LLM fallback scenarios
- Migration system

**Test Data**:
- Synthetic PDFs for each bank
- Mock LLM responses
- Sample transaction datasets

### Performance Considerations

**PDF Processing**:
- Stream large PDFs instead of loading fully
- Cache extracted data for re-processing

**LLM Optimization**:
- Batch multiple transactions per API call
- Cache merchant categorizations
- Local rules before LLM calls

**Database**:
- Indexes on commonly queried columns
- Prepared statements for repeated queries
- Connection pooling for concurrent access

### Error Handling

**PDF Extraction**:
- Graceful handling of unsupported formats
- Clear error messages for parsing failures
- Partial extraction recovery

**LLM Failures**:
- Automatic fallback to rules
- Retry logic with exponential backoff
- Queue failed categorizations for later

**Data Integrity**:
- Transaction deduplication
- Constraint validation
- Audit logging for categorization changes

### Security Considerations

**Local Processing**:
- fin-extract never makes network calls
- No PII sent to LLM services
- Transaction descriptions only, no account info

**API Keys**:
- Stored in environment variables
- Never logged or displayed
- Optional local LLM support

### Distribution Plan

**Package Management**:
- Single package: `fin-cli`
- Installable via pip
- Optional standalone binaries via PyInstaller

**Dependencies**:
- Minimal required dependencies
- Optional dependencies for enhanced features
- Clear dependency documentation

### Questions Remaining

1. **Initial Bank Support Priority**:
   - Should we implement all three banks in Phase 1?
   - Or start with Chase and add others incrementally?

2. **LLM Provider Flexibility**:
   - Should we support multiple providers from day 1?
   - Or start with OpenAI and add others later?

3. **Category Seeding**:
   - Start with zero predefined categories?
   - Or include minimal seed categories?

4. **Review Workflow**:
   - Should JSON mode support bulk operations?
   - Specific format requirements for Claude Code?

5. **Export Formats**:
   - Just Markdown initially?
   - Add PDF, HTML export later?

This implementation plan provides a clear path to building the financial CLI tools suite with focus on privacy, intelligent categorization, and extensibility.