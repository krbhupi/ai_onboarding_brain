# Production Deployment Guide

## Overview

This guide outlines the steps for deploying the HR Automation application in a production environment with Oracle Database and hosted LLM/VLM models.

## Prerequisites

- Oracle Database 12c or higher
- Python 3.10+
- Hosted LLM and VLM model servers
- Linux server (Ubuntu 20.04+ recommended)
- 8GB RAM minimum
- 20GB storage minimum

## Database Configuration

### Oracle Database Setup

1. **Connection String Format**:
   ```
   DATABASE_URL=oracle+cx_oracle://username:password@host:port/service_name
   ```

2. **Required Oracle Client Libraries**:
   ```bash
   # Install Oracle Instant Client
   sudo apt-get install oracle-instantclient-basic
   pip install cx_Oracle
   ```

3. **Database Schema**:
   The existing Alembic migrations should work with Oracle with minimal changes.
   Run migrations:
   ```bash
   alembic upgrade head
   ```

## LLM/VLM Model Configuration

### Hosted Model Setup

1. **LLM Configuration** (in `.env`):
   ```
   LLM_BASE_URL=http://your-llm-server:port
   LLM_MODEL=your-model-name
   ```

2. **VLM Configuration** (in `.env`):
   ```
   VISION_BASE_URL=http://your-vlm-server:port
   VISION_MODEL=your-vision-model-name
   ```

3. **API Keys** (if required):
   ```
   LLM_API_KEY=your-api-key
   VISION_API_KEY=your-vision-api-key
   ```

## Application Deployment

### 1. Environment Setup

```bash
# Clone repository
git clone https://github.com/krbhupi/ai_onboarding_brain.git
cd ai_onboarding_brain

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

Copy and edit the environment file:
```bash
cp .env.example .env
nano .env
```

Update the following values for production:
- `DATABASE_URL` - Oracle connection string
- `IMAP_USERNAME` - Production email account
- `IMAP_PASSWORD` - Production email password
- `SMTP_USERNAME` - Production SMTP account
- `SMTP_PASSWORD` - Production SMTP password
- `LLM_BASE_URL` - Hosted LLM endpoint
- `VISION_BASE_URL` - Hosted VLM endpoint

### 3. Database Initialization

```bash
# Create necessary directories
mkdir -p data/documents data/temp data/input

# Initialize database (Alembic migrations)
alembic upgrade head

# Add sample Excel file to data/input/
# Copy your offer_tracker.xlsx to data/input/
```

### 4. Application Startup

For production, use Gunicorn:
```bash
# Install Gunicorn
pip install gunicorn

# Start application
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### 5. ETL Pipeline Scheduling

Use system-level cron jobs instead of the Python scheduler for better reliability:

```bash
# Edit crontab
crontab -e

# Add these entries:
# Run ETL pipeline every hour
0 * * * * cd /path/to/ai_onboarding_brain && /path/to/venv/bin/python scripts/run_etl_pipeline.py --full >> /var/log/hr_etl.log 2>&1

# Run ETL pipeline daily at 10 PM
0 22 * * * cd /path/to/ai_onboarding_brain && /path/to/venv/bin/python scripts/run_etl_pipeline.py --full >> /var/log/hr_etl.log 2>&1
```

## Monitoring and Maintenance

### Log Monitoring

```bash
# Application logs
tail -f logs/hr_automation.log

# Service logs (if using systemd)
sudo journalctl -u hr-onboarding -f
```

### Health Checks

```bash
# Health check endpoint
curl http://localhost:8000/health

# Database connectivity
python -c "from src.core.database import engine; print(engine.connect())"
```

### Backup Strategy

1. **Database Backups**:
   - Use Oracle RMAN for database backups
   - Schedule regular automated backups

2. **File Backups**:
   - Backup the `data/` directory containing documents
   - Include the `hr_onboarding.db` file if using SQLite for testing

## Security Considerations

1. **Environment Variables**:
   - Store sensitive credentials securely
   - Use vault or secret management systems in production

2. **Network Security**:
   - Use HTTPS for all external communications
   - Restrict database access to application servers only

3. **Authentication**:
   - Implement proper API authentication for production endpoints
   - Use OAuth2 or similar for user authentication

## Scaling Considerations

1. **Horizontal Scaling**:
   - Use load balancer for multiple application instances
   - Implement database connection pooling

2. **Vertical Scaling**:
   - Monitor resource usage and scale accordingly
   - Optimize database queries for performance

3. **Queue Processing**:
   - For high-volume email processing, consider using message queues
   - Implement worker pools for job processing

## Troubleshooting

### Common Issues

1. **Database Connection Errors**:
   - Verify Oracle client installation
   - Check connection string format
   - Ensure network connectivity to database server

2. **LLM/VLM API Errors**:
   - Verify hosted model endpoints are accessible
   - Check API key validity
   - Monitor model server logs

3. **Email Processing Issues**:
   - Verify IMAP/SMTP credentials
   - Check email server connectivity
   - Review email quota limits

### Recovery Procedures

1. **Database Recovery**:
   - Restore from Oracle RMAN backups
   - Re-run ETL pipeline to sync latest data

2. **Application Recovery**:
   - Restart Gunicorn processes
   - Check application logs for errors
   - Verify all dependencies are installed

## Performance Optimization

1. **Database Indexes**:
   - Ensure proper indexing on frequently queried columns
   - Monitor slow queries and optimize

2. **Caching**:
   - Implement Redis or similar for frequently accessed data
   - Cache LLM responses where appropriate

3. **Batch Processing**:
   - Optimize ETL pipeline for batch processing
   - Use bulk database operations where possible

## Updates and Maintenance

1. **Code Updates**:
   - Pull latest changes from repository
   - Run database migrations if needed
   - Restart application services

2. **Dependency Updates**:
   - Regularly update Python dependencies
   - Test compatibility with Oracle database updates

3. **Model Updates**:
   - Coordinate with LLM/VLM hosting provider for model updates
   - Test new models before deployment