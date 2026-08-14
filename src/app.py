import re
from datetime import datetime, timezone
import boto3
import requests
import io
import zipfile
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from typing import List

class PIIRedactor:
    def __init__(self):
        self.patterns = {
            "EMAIL": r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
            "IP_ADDRESS": r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b',
            "PHONE": r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',
            "SSN": r'\b\d{3}-\d{2}-\d{4}\b'
        }

    def redact(self, log_text):
        redacted_text = log_text
        for pii_type, pattern in self.patterns.items():
            redacted_text = re.sub(pattern, f"[REDACTED_{pii_type}]", redacted_text)
        return redacted_text

class LogProcessor:
    def __init__(self):
        self.redactor = PIIRedactor()
        self.log_pattern = r'^\[(?P<timestamp>.*?)\] \[(?P<level>INFO|WARN|ERROR|DEBUG)\] \[(?P<service>.*?)\] (?P<message>.*)$'

    def parse_line(self, line):
        match = re.match(self.log_pattern, line.strip())
        if not match:
            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": "UNKNOWN",
                "service": "general",
                "raw_message": self.redactor.redact(line.strip())
            }

        data = match.groupdict()
        data["message"] = self.redactor.redact(data["message"])
        return data


app = FastAPI(title="DiaLogix Log Processor API")
processor = LogProcessor()

# --- Data Models ---
class LogRequest(BaseModel):
    raw_log: str

class Attachment(BaseModel):
    name: str
    attachment_url: str

class TicketInfo(BaseModel):
    id: int
    attachments: List[Attachment] = []

class FreshdeskWebhook(BaseModel):
    ticket: TicketInfo

# --- Background Worker ---
s3_client = boto3.client('s3')
S3_BUCKET_NAME = "dialogix-diagnostics-20260814012619980300000001"
redactor = PIIRedactor()

def process_ticket_attachments(ticket_id: int, attachments: List[Attachment]):
    print(f"[BACKGROUND] Starting secure extraction and redaction for Ticket #{ticket_id}")
    
    for attachment in attachments:
        file_name = attachment.name
        file_url = attachment.attachment_url
        
        print(f"[BACKGROUND] Downloading {file_name} from Freshdesk...")
        try:
            response = requests.get(file_url)
            response.raise_for_status() 
            
            if file_name.endswith('.zip'):
                print(f"[BACKGROUND] Unzipping and redacting {file_name} in memory...")
                
                with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                    for extracted_name in z.namelist():
                        # Skip directories inside the zip
                        if extracted_name.endswith('/'):
                            continue
                            
                        s3_key = f"{ticket_id}/{extracted_name}"
                        print(f"[BACKGROUND] Redacting and uploading: s3://{S3_BUCKET_NAME}/{s3_key} ...")
                        
                        with z.open(extracted_name) as f:
                            try:
                                # 1. Read bytes and convert to string
                                raw_text = f.read().decode('utf-8')
                                
                                # 2. Scrub the PII
                                redacted_text = redactor.redact(raw_text)
                                
                                # 3. Convert back to bytes for S3
                                redacted_bytes = redacted_text.encode('utf-8')
                                s3_client.upload_fileobj(io.BytesIO(redacted_bytes), S3_BUCKET_NAME, s3_key)
                                
                            except UnicodeDecodeError:
                                # If it's not a text file (like an image), just upload raw bytes
                                f.seek(0)
                                s3_client.upload_fileobj(f, S3_BUCKET_NAME, s3_key)
                                
                print(f"[BACKGROUND] SUCCESS! {file_name} extracted, redacted, and vaulted.")
                
            else:
                s3_key = f"{ticket_id}/{file_name}"
                print(f"[BACKGROUND] Redacting and uploading to S3: s3://{S3_BUCKET_NAME}/{s3_key} ...")
                
                try:
                    raw_text = response.content.decode('utf-8')
                    redacted_text = redactor.redact(raw_text)
                    redacted_bytes = redacted_text.encode('utf-8')
                    s3_client.upload_fileobj(io.BytesIO(redacted_bytes), S3_BUCKET_NAME, s3_key)
                except UnicodeDecodeError:
                    s3_client.upload_fileobj(io.BytesIO(response.content), S3_BUCKET_NAME, s3_key)
                    
                print(f"[BACKGROUND] SUCCESS! {file_name} securely vaulted.")
            
        except Exception as e:
            print(f"[BACKGROUND] ERROR processing {file_name}: {str(e)}")

# --- API Endpoints ---
@app.get("/")
async def root():
    return {"status": "healthy", "service": "log-processor"}

@app.post("/parse")
async def parse_log_endpoint(request: LogRequest):
    return processor.parse_line(request.raw_log)

@app.post("/api/v1/webhooks/freshdesk")
async def freshdesk_webhook_endpoint(webhook: FreshdeskWebhook, background_tasks: BackgroundTasks):
    ticket_id = webhook.ticket.id
    attachments = webhook.ticket.attachments
    
    if attachments:
        # Hand the heavy lifting off to the background worker so we don't freeze the API
        background_tasks.add_task(process_ticket_attachments, ticket_id, attachments)
        
    return {
        "status": "accepted", 
        "ticket_id": ticket_id, 
        "message": f"Webhook received. {len(attachments)} attachments queued for background processing."
    }