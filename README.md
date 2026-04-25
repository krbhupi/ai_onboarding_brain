# HR Automation - AI Onboarding System

An autonomous AI-driven workflow for HR onboarding that collects employee documents, performs validation, and manages the complete document lifecycle.

## Features

- **Document Collection**: Automated email-based document collection
- **AI Document Classification**: OCR validation using local LLM (Ollama)
- **Gap Analysis**: Track missing vs completed documents
- **Follow-up Automation**: Automated reminder emails
- **Human-in-the-Loop**: HR approval workflow
- **Audit Trail**: Complete tracking of all operations

## Architecture

```
ai_onboarding_brain/
├── config/                 # Configuration files
│   ├── settings.py        # Environment and DB config
│   └── logging.py         # Logging setup
├── src/
│   ├── constants/         # Status codes, job types
│   ├── models/            # SQLAlchemy database models
│   ├── schemas/           # Pydantic schemas
│   ├── controller/        # FastAPI endpoints
│   ├── core/              # Database, security
│   ├── services/          # Business logic services
│   ├── mcp_tools/         # MCP tools for document processing
│   ├── agent/             # Agent orchestration
│   └── data/              # Data storage
├── airflow/
│   └── dags/              # Airflow DAGs
├── tests/                 # Test files
├── alembic/               # Database migrations
└── main.py                # Application entry point
```

## Tech Stack

- **Framework**: FastAPI
- **Database**: SQLite (via SQLAlchemy)
- **Email**: IMAP/SMTP
- **LLM**: Local Ollama (qwen2.5:7b)
- **Orchestration**: Pure Python (schedule library)

## Setup

### Prerequisites

- Python 3.10+
- Ollama (for local LLM)

### Installation

1. Clone and install dependencies:
```bash
cd ai_onboarding_brain
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

2. Configure environment:
```bash
cp .env.example .env
# Edit .env with your settings
```

3. Run database migrations:
```bash
alembic upgrade head
```

4. The SQLite database will be created automatically on first run

5. Start Ollama LLM:
```bash
ollama serve
ollama pull qwen2.5:7b
```

6. Run the application:
```bash
uvicorn main:app --reload
```

7. Run ETL pipeline manually (optional):
```bash
# Run full ETL pipeline
python scripts/run_etl_pipeline.py --full

# Or run the scheduler for periodic execution
python scripts/scheduler.py
```

## API Endpoints

### Candidates
- `GET /api/candidates` - List candidates
- `POST /api/candidates` - Create candidate
- `GET /api/candidates/{id}` - Get candidate
- `PUT /api/candidates/{id}` - Update candidate

### Documents
- `GET /api/documents` - List documents
- `POST /api/documents` - Create document tracker
- `POST /api/documents/upload` - Upload document
- `POST /api/documents/{id}/validate` - Validate with OCR

### Jobs
- `GET /api/jobs` - List jobs
- `POST /api/jobs` - Create job
- `GET /api/jobs/pending/action` - Get pending actions
- `POST /api/jobs/{id}/approve` - Approve job

### Email
- `POST /api/email/draft` - Generate email draft
- `POST /api/email/send` - Send email
- `GET /api/email/inbox` - Read inbox
- `POST /api/email/process-replies` - Process replies

## MCP Tools

### save_attachment
Saves email attachments to candidate folders.

### followup_classification
Classifies candidate email replies and extracts dates.

### ocr_validation
Validates document types using LLM.

### segregation
Organizes documents into categories (education, employment, personal).

### gap_analysis
Analyzes missing documents and updates status.

### draft_prepare
Generates follow-up email drafts.

## Database Schema

### Key Tables
- `candidate_info` - Candidate details
- `document_tracker` - Document tracking
- `job_tracker` - Workflow jobs
- `document_type_master` - Document types
- `status_master` - Status values
- `job_type_master` - Job types
- `mail_type_master` - Email templates

## Workflow

1. **ETL Pipeline** (Daily at 10 PM via scheduler.py)
   - Read `offer_tracker.xlsx`
   - Sync candidates to database
   - Create initial jobs

2. **Email Processing**
   - Monitor inbox for replies
   - Classify and process attachments
   - Run OCR validation

3. **Gap Analysis**
   - Compare required vs received documents
   - Update tracker status
   - Schedule follow-ups

4. **HR Approval**
   - Review generated drafts
   - Approve/modify emails
   - Track completion

## Testing

```bash
pytest tests/ -v
```

## Production Deployment

For production deployment:

1. **Database**: Configure Oracle DB connection in `.env`
2. **LLM Models**: Use hosted LLM and VLM models by updating API endpoints
3. **Scheduling**: Use system-level cron jobs instead of the Python scheduler for better reliability
4. **Monitoring**: Implement proper logging and monitoring for production use

## License

MIT License