# 1. Create the S3 Bucket for Freshdesk Attachments
resource "aws_s3_bucket" "diagnostic_attachments" {
  bucket_prefix = "dialogix-diagnostics-"

  tags = {
    Name = "dialogix-diagnostic-attachments"
  }
}

# 2. Enforce Strict Security (Block all public internet access to these files)
resource "aws_s3_bucket_public_access_block" "secure_attachments" {
  bucket = aws_s3_bucket.diagnostic_attachments.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}