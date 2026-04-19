"""MCP Tool: Save attachments from emails to candidate folders."""
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from config.settings import get_settings
from config.logging import logger
from src.services.email_service import EmailService
from src.services.document_service import DocumentService

settings = get_settings()


class SaveAttachmentTool:
    """Tool for saving email attachments to candidate-specific folders."""

    def __init__(self, email_service: EmailService, document_service: DocumentService):
        self.email_service = email_service
        self.document_service = document_service
        self.name = "save_attachment"
        self.description = "Save email attachments to candidate document folders"

    async def execute(
        self,
        cin: str,
        attachments: List[Dict[str, Any]],
        job_id: Optional[int] = None,
        candidate_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Save attachments for a candidate.

        Args:
            cin: Candidate identification number
            attachments: List of attachment dictionaries from email
            job_id: Associated job tracker ID
            candidate_id: Database candidate ID

        Returns:
            Dictionary with saved attachment details
        """
        results = {
            "cin": cin,
            "saved_count": 0,
            "failed_count": 0,
            "documents": []
        }

        candidate_dir = self.document_service.get_candidate_directory(cin)

        for attachment in attachments:
            try:
                # Generate unique filename
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_filename = f"{timestamp}_{attachment['filename']}"
                save_path = candidate_dir / safe_filename

                # Save attachment
                await self.email_service.save_attachment(attachment, save_path)

                # Get document type ID (will be determined by OCR later)
                document_type_id = await self._get_or_create_document_type(
                    attachment['filename']
                )

                # Create document tracker entry
                if candidate_id and job_id:
                    tracker = await self.document_service.create_document_tracker(
                        candidate_id=candidate_id,
                        document_type_id=document_type_id,
                        job_id=job_id,
                        document_store_id=None,  # Will be updated after storage
                        comments=f"Received via email on {datetime.now().isoformat()}"
                    )

                    results["documents"].append({
                        "filename": safe_filename,
                        "original_name": attachment['filename'],
                        "path": str(save_path),
                        "size": attachment.get('size', 0),
                        "content_type": attachment.get('content_type', 'unknown'),
                        "document_tracker_id": tracker.document_tracker_id
                    })
                else:
                    results["documents"].append({
                        "filename": safe_filename,
                        "original_name": attachment['filename'],
                        "path": str(save_path),
                        "size": attachment.get('size', 0),
                        "content_type": attachment.get('content_type', 'unknown')
                    })

                results["saved_count"] += 1
                logger.info(f"Saved attachment: {safe_filename} for CIN: {cin}")

            except Exception as e:
                logger.error(f"Failed to save attachment {attachment['filename']}: {e}")
                results["failed_count"] += 1
                results["documents"].append({
                    "filename": attachment['filename'],
                    "error": str(e)
                })

        return results

    async def _get_or_create_document_type(self, filename: str) -> int:
        """Get document type ID based on filename, create if needed."""
        # Map common filenames to document types
        filename_lower = filename.lower()

        type_mapping = {
            'aadhar': 1,
            'aadhaar': 1,
            'pan': 2,
            '10th': 3,
            '12th': 4,
            'hsc': 4,
            'ssc': 3,
            'degree': 5,
            'marksheet': 6,
            'passport': 7,
            'photo': 7,
            'bank': 8,
            'cheque': 8,
            'relieving': 9,
            'experience': 10,
            'salary': 11,
            'form16': 12,
            'form 16': 12,
        }

        for key, type_id in type_mapping.items():
            if key in filename_lower:
                return type_id

        # Default to a generic document type (adjust as needed)
        return 1  # Default ID

    def get_tool_schema(self) -> Dict[str, Any]:
        """Return the tool schema for MCP."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "cin": {
                        "type": "string",
                        "description": "Candidate identification number"
                    },
                    "attachments": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "filename": {"type": "string"},
                                "content_type": {"type": "string"},
                                "size": {"type": "integer"},
                                "part": {"type": "object"}
                            }
                        },
                        "description": "List of email attachments"
                    },
                    "job_id": {
                        "type": "integer",
                        "description": "Associated job tracker ID"
                    },
                    "candidate_id": {
                        "type": "integer",
                        "description": "Database candidate ID"
                    }
                },
                "required": ["cin", "attachments"]
            }
        }