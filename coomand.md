Steps to Deploy and Test on a Server                                                                      
                                                                                          
  1. Server Requirements                                                                                    
                                                                                                            
  # Minimum requirements:                                                                                   
  - Ubuntu 20.04+ or similar Linux                                                                          
  - Python 3.10+                                                                                            
  - 4GB RAM minimum                                                                                         
  - 10GB storage                                                                                            
  - Internet access (for LLM API)                                                                           
                                                                                                            
  2. Clone and Setup                                                                                        
                                                                                                            
  # SSH into your server                                                                                    
  ssh user@your-server-ip                                                                                   
                                                                                                            
  # Install system dependencies                                                                             
  sudo apt update && sudo apt install -y \                                                                  
      python3 python3-pip python3-venv \                                                                    
      git tesseract-ocr poppler-utils                                                                       
                                                                                                            
  # Clone repository                                                                                        
  cd /opt                                                                                                   
  sudo git clone https://github.com/krbhupi/ai_onboarding_brain.git                                         
  cd ai_onboarding_brain                                                                                    
                                                                                                            
  # Create virtual environment                                                                              
  python3 -m venv venv                                                                                      
  source venv/bin/activate                                                                                  
                                                                                                            
  # Install dependencies                                                                                    
  pip install -r requirements.txt                                                                           
                                                                                                            
  3. Configure Environment                                                                                  
   
  # Copy and edit .env                                                                                      
  cp .env.example .env                                                                                      
  nano .env                                                                                                 
                                                                                                            
  # Update these values:                                                                                    
  # DATABASE_URL=sqlite+aiosqlite:///./hr_onboarding.db                                                     
  # IMAP_USERNAME=your-email@gmail.com                                                                      
  # IMAP_PASSWORD=your-app-password                                                                         
  # SMTP_USERNAME=your-email@gmail.com                                                                      
  # SMTP_PASSWORD=your-app-password                                                                         
  # LLM_BASE_URL=https://ollama.com                                                                         
  # LLM_MODEL=gpt-oss:120b                                                                                  
  # OLLAMA_API_KEY=your-api-key                                                                             
                                                                                                            
  4. Initialize Database                                                                                    
                                                                 
  # Create necessary directories                                                                            
  mkdir -p data/documents data/temp data/input                                                              
                                                                                                            
  # Initialize database                                                                                     
  python init_db.py                                                                                         
                                                                                                            
  # Add sample Excel file to data/input/                                                                    
  # Copy your offer_tracker.xlsx to data/input/
                                                                                                            
  5. Run the Application                                                                                    
   
  # Start FastAPI server                                                                                    
  uvicorn main:app --host 0.0.0.0 --port 8000                                                               
                                                                                                            
  # Or run with gunicorn for production                                                                     
  gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000                               
                                                                                                            
  6. Test Endpoints                                                                                         
                                                                                                            
  # Health check                                                                                            
  curl http://localhost:8000/health                                                                         
                                                                                                            
  # Get all candidates                                                                                      
  curl http://localhost:8000/candidates                                                                     
                                                                                                            
  # Get candidate by ID                                                                                     
  curl http://localhost:8000/candidates/1                                                                   
                                                                                                            
  # Run gap analysis                                                                                        
  curl http://localhost:8000/candidates/1/gap-analysis                                                      
                                                                                                            
  # Get document status                                                                                     
  curl http://localhost:8000/candidates/1/documents                                                         
                                                                                                            
  7. Run ETL Pipeline                                                                                       
                                                                                                            
  # Sync candidates from Excel                                                                              
  python -c "                                                                                               
  import asyncio                                                                                            
  from src.services.etl_service import ETLService                                                           
  from src.core.database import get_db, init_db                                                             
                                                                                                            
  async def run():                                                                                          
      await init_db()                                                                                       
      async for session in get_db():                                                                        
          etl = ETLService(session)                                                                         
          result = await etl.sync_candidates()                                                              
          print(f'Result: {result}')                                                                        
          break                                                                                             
                                                                                                            
  asyncio.run(run())                                                                                        
  "                                                              

  8. Test Full Workflow                                                                                     
   
  # Run end-to-end test                                                                                     
  python tests/end_to_end_test.py                                                                           
                                                                                                            
  9. Set Up as Systemd Service (Production)                                                                 
                                                                                                            
  # Create service file                                                                                     
  sudo nano /etc/systemd/system/hr-onboarding.service                                                       
                                                                                                            
  [Unit]                                                                                                    
  Description=HR Onboarding API                                                                             
  After=network.target                                                                                      
                                                                                                            
  [Service]                                                                                                 
  Type=simple                                                                                               
  User=www-data                                                                                             
  WorkingDirectory=/opt/ai_onboarding_brain                                                                 
  ExecStart=/opt/ai_onboarding_brain/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000                   
  Restart=always                                                                                            
  RestartSec=10                                                                                             
                                                                                                            
  [Install]                                                      
  WantedBy=multi-user.target                                                                                
                                                                                                            
  # Enable and start                                                                                        
  sudo systemctl daemon-reload                                                                              
  sudo systemctl enable hr-onboarding                                                                       
  sudo systemctl start hr-onboarding                                                                        
                                                                                                            
  # Check status                                                                                            
  sudo systemctl status hr-onboarding                                                                       
                                                                                                            
  10. Set Up Nginx Reverse Proxy                                                                            
                                                                                                            
  sudo apt install nginx                                                                                    
  sudo nano /etc/nginx/sites-available/hr-onboarding             
                                                                                                            
  server {                                                                                                  
      listen 80;                                                                                            
      server_name your-domain.com;                                                                          
                                                                                                            
      location / {                                                                                          
          proxy_pass http://127.0.0.1:8000;                                                                 
          proxy_set_header Host $host;                                                                      
          proxy_set_header X-Real-IP $remote_addr;                                                          
      }                                                                                                     
  }                                                                                                         
                                                                                                            
  sudo ln -s /etc/nginx/sites-available/hr-onboarding /etc/nginx/sites-enabled/                             
  sudo nginx -t                                                                                             
  sudo systemctl restart nginx                                                                              
                                                                                                            
  11. Schedule ETL Pipeline (Optional)                                                                      
   
  # Run the scheduler script (runs daily at 10 PM and hourly)                                              
  python scripts/scheduler.py &                                                                             
                                                                                                            
  # Or add to crontab for system-level scheduling                                                           
  # Run every hour:                                                                                         
  # 0 * * * * cd /opt/ai_onboarding_brain && /opt/ai_onboarding_brain/venv/bin/python scripts/run_etl_pipeline.py --full >> /var/log/hr_etl.log 2>&1
                                                                                                            
  # Run daily at 10 PM:                                                                                     
  # 0 22 * * * cd /opt/ai_onboarding_brain && /opt/ai_onboarding_brain/venv/bin/python scripts/run_etl_pipeline.py --full >> /var/log/hr_etl.log 2>&1
                                                                                                            
  12. Monitor Logs                                                                                          
                                                                                                            
  # Application logs                                                                                        
  tail -f logs/hr_automation.log                                 
                                                                                                            
  # Service logs                                                                                            
  sudo journalctl -u hr-onboarding -f                                                                       
                                                                                                            
  # ETL Pipeline logs                                            
  tail -f logs/hr_automation.log                                                            
                                                                                                            
  ---                                                                                                       
  Production Configuration                                                                                  
                                                                                                            
  # For production deployment with Oracle DB and hosted LLM/VLM models:                                     
  # 1. Update .env with Oracle database connection:                                                         
  #    DATABASE_URL=oracle+cx_oracle://user:password@host:port/service_name                                
  # 2. Configure LLM settings for hosted models:                                                            
  #    LLM_BASE_URL=http://your-llm-server:port                                                            
  #    VISION_BASE_URL=http://your-vlm-server:port                                                         
  # 3. Adjust concurrency settings as needed for production load                                             
                                                                                                            
  ---                                                                                                       
  Quick Test Script                                                                                         
                                                                                                            
  # Create test script                                           
  cat > test_server.sh << 'EOF'                                                                             
  #!/bin/bash                                                                                               
  echo "Testing HR Onboarding API..."
                                                                                                            
  # Health check                                                 
  echo "1. Health Check:"                                                                                   
  curl -s http://localhost:8000/health | jq .                                                               
                                                                                                            
  # Get candidates                                                                                          
  echo -e "\n2. Get Candidates:"                                                                            
  curl -s http://localhost:8000/candidates | jq .                                                           
                                                                                                            
  # Gap analysis                                                                                            
  echo -e "\n3. Gap Analysis (Candidate 1):"                                                                
  curl -s http://localhost:8000/candidates/1/gap-analysis | jq .                                            
                                                                                                            
  echo -e "\n✅ All tests passed!"                                                                          
  EOF                                                                                                       
                                                                                                            
  chmod +x test_server.sh                                                                                   
  ./test_server.sh                                                                                          
                                                                                                            
  ---                                                                                                       
  API Endpoints Reference
                                                                                                            
  ┌───────────────────────────────┬────────┬─────────────────────┐
  │           Endpoint            │ Method │     Description     │                                          
  ├───────────────────────────────┼────────┼──────────────────────┤                                         
  │ /health                       │ GET    │ Health check         │                                         
  ├───────────────────────────────┼────────┼──────────────────────┤                                         
  │ /candidates                   │ GET    │ List all candidates  │                                         
  ├───────────────────────────────┼────────┼──────────────────────┤                                         
  │ /candidates/{id}              │ GET    │ Get candidate by ID  │                                         
  ├───────────────────────────────┼────────┼──────────────────────┤                                         
  │ /candidates/{id}/documents    │ GET    │ Get document status  │
  ├───────────────────────────────┼────────┼──────────────────────┤                                         
  │ /candidates/{id}/gap-analysis │ GET    │ Run gap analysis     │
  ├───────────────────────────────┼────────┼──────────────────────┤                                         
  │ /candidates/{id}/send-email   │ POST   │ Send follow-up email │
  ├───────────────────────────────┼────────┼──────────────────────┤                                         
  │ /jobs/pending                 │ GET    │ Get pending jobs     │
  ├───────────────────────────────┼────────┼──────────────────────┤                                         
  │ /inbox/check                  │ POST   │ Check for new emails │
  └───────────────────────────────┴────────┴──────────────────────┘