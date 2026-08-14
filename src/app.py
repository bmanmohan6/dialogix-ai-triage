import re
from datetime import datetime, timezone
import boto3
import requests
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

def process_ticket_attachments(ticket_id: int, attachments: List[Attachment]):
    print(f"[BACKGROUND] Starting secure extraction for Ticket #{ticket_id}")
    
    for attachment in attachments:
        file_name = attachment.name
        file_url = attachment.attachment_url
        
        # Create the virtual folder structure: "ticket_id/filename.ext"
        s3_key = f"{ticket_id}/{file_name}"
        
        print(f"[BACKGROUND] Downloading {file_name} from Freshdesk...")
        try:
            # Download the file as a stream so we don't overwhelm the server's RAM
            response = requests.get(file_url, stream=True)
            response.raise_for_status() 
            
            print(f"[BACKGROUND] Uploading to S3: s3://{S3_BUCKET_NAME}/{s3_key} ...")
            
            # Stream the raw file data directly into your AWS S3 bucket
            s3_client.upload_fileobj(response.raw, S3_BUCKET_NAME, s3_key)
            
            print(f"[BACKGROUND] SUCCESS! {file_name} securely vaulted in S3.")
            
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