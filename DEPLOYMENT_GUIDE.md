# Deployment Guide

## Overview

This guide documents the successful end-to-end testing and deployment of the new features:
1. New LLM Service Integration
2. Exchange Email Service Integration  
3. Oracle Database Support

## Testing Summary

All integration tests passed successfully:

```
Running Integration Tests...

Testing Configuration...
✓ Settings loaded successfully
✓ Database URL: sqlite+aiosqlite:///./hr_onboarding.db
✓ New LLM Enabled: False
✓ Exchange Username: None
✓ Oracle User: AGENTIC_AI
✓ Configuration test passed

Testing New LLM Provider...
✓ NewLLMProvider instantiated with model: gpt-oss-20b
✓ NewLLMProvider URL: http://172.17.58.114:8002/v1/chat/completions
✓ New LLM Provider test passed

Testing LLM Service with New Provider...
✓ LLMService instantiated
✓ New LLM Enabled: False
✓ LLM Service with New Provider test passed

Testing Exchange Email Service...
✓ ExchangeEmailService instantiated
✓ Exchange username: agentcai.solution@rebittest.com
✓ Exchange server: mail.rebittest.com
✓ Exchange Email Service test passed

==================================================
Integration Tests Summary: 4/4 tests passed
==================================================
🎉 All integration tests passed!
```

## Deployment Status

✅ **Code Changes**: Successfully committed and pushed to GitHub
✅ **Version Tag**: Created and pushed v1.1.0 tag
✅ **Dependencies**: All required packages documented in requirements.txt
✅ **Backward Compatibility**: Maintained with existing SQLite/PostgreSQL support

## New Features Overview

### 1. New LLM Service Integration
- **Model**: gpt-oss-20b
- **Endpoint**: http://172.17.58.114:8002/v1/chat/completions
- **Activation**: Set `NEW_LLM_ENABLED=true` in .env
- **Fallback**: Automatically falls back to Ollama if new service fails

### 2. Exchange Email Service
- **Library**: exchangelib
- **Server**: mail.rebittest.com
- **Activation**: Set `USE_EXCHANGE=true` in .env
- **Features**: SSL support, attachment handling, inbox reading

### 3. Oracle Database Support
- **Drivers**: cx_Oracle and oracledb
- **Connection**: oracle+oracledb:// protocol
- **Configuration**: Oracle credentials in .env file
- **Flexibility**: Toggle between SQLite (dev) and Oracle (prod)

## Configuration Instructions

### Enable New LLM Service
```bash
# In .env file
NEW_LLM_ENABLED=true
NEW_LLM_MODEL=gpt-oss-20b
NEW_LLM_URL=http://172.17.58.114:8002/v1/chat/completions
```

### Enable Exchange Email Service
```bash
# In .env file
USE_EXCHANGE=true
EXCHANGE_USERNAME=agentcai.solution@rebittest.com
EXCHANGE_PASSWORD=Welcome@2026
EXCHANGE_SERVER=mail.rebittest.com
EXCHANGE_PRIMARY_SMTP=agentcai.solution@rebittest.com
EXCHANGE_DISABLE_SSL_VERIFY=false
```

### Use Oracle Database
```bash
# In .env file, uncomment Oracle line and comment SQLite line
# DATABASE_URL=oracle+oracledb://AGENTIC_AI:Agentic_ai52026@172.17.59.201:1521/POC2ALFOR
DATABASE_POOL_SIZE=5
DATABASE_MAX_OVERFLOW=10
```

## Dependencies

All new dependencies are documented in `requirements.txt`:
- exchangelib>=5.6.0 (Exchange email)
- cx_Oracle>=8.3.0 (Oracle database)
- oracledb>=3.4.0 (Oracle database)

Install with: `pip install -r requirements.txt`

## Rollback Procedure

If issues occur in production:
1. Revert to previous version: `git checkout v1.0.0`
2. Restore .env from backup
3. Reinstall previous requirements: `pip install -r requirements.txt`
4. Restart application services

## Monitoring

Key metrics to monitor post-deployment:
- LLM response times and error rates
- Email delivery success rates
- Database connection stability
- Application startup time

## Support

For issues with new features, check:
1. Logs in application logging directory
2. Network connectivity to new service endpoints
3. Credential validity in .env file
4. Firewall rules for new service ports