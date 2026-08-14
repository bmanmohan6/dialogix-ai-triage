import re
import json
from datetime import datetime, timezone

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
        # Standard log regex pattern: [TIMESTAMP] [LOG_LEVEL] [SERVICE] Message
        self.log_pattern = r'^\[(?P<timestamp>.*?)\] \[(?P<level>INFO|WARN|ERROR|DEBUG)\] \[(?P<service>.*?)\] (?P<message>.*)$'

    def parse_line(self, line):
        match = re.match(self.log_pattern, line.strip())
        if not match:
            # Fallback for unstructured logs
            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": "UNKNOWN",
                "service": "general",
                "raw_message": self.redactor.redact(line.strip())
            }

        data = match.groupdict()
        # Redact PII from the log message before returning
        data["message"] = self.redactor.redact(data["message"])
        return data

# fastapi and pydantic
from fastapi import FastAPI
from pydantic import BaseModel

# ... (Keep your PIIRedactor and LogProcessor classes here) ...

# 1. Initialize the FastAPI application
app = FastAPI(title="DiaLogix Log Processor API")

# 2. Define the expected incoming JSON structure
class LogRequest(BaseModel):
    raw_log: str

# 3. Instantiate the processor once so it is ready for all requests
processor = LogProcessor()

# 4. Create the API endpoint
@app.post("/parse")
async def parse_log_endpoint(request: LogRequest):
    """
    Receives a raw log line, redacts PII, and returns structured JSON.
    """
    # The request.raw_log string is passed to your existing engine
    parsed_data = processor.parse_line(request.raw_log)
    return parsed_data