resource "aws_ecr_repository" "dialogix_log_processor" {
  name                 = "dialogix-log-processor"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  # Explicitly defining the default AES-256 encryption
  encryption_configuration {
    encryption_type = "AES256"
  }

  image_scanning_configuration {
    scan_on_push = true
  }
}