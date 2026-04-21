"""Document Validator - Validates documents using OCR/LLM before marking complete."""
import os
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from config.logging import logger
from src.models.database import (
    DocumentTracker, DocumentTypeMaster, StatusMaster, CandidateInfo
)
from src.constants.constants import StatusType
from src.services.llm_service import LLMService


class DocumentValidator:
    """Validates documents using OCR/LLM and updates tracker status."""

    def __init__(self, db: AsyncSession, llm_service: LLMService = None):
        self.db = db
        self.llm_service = llm_service or LLMService()
        self.name = "document_validator"
        self.description = "Validate documents using OCR/LLM and update status"

    async def validate_all_documents(
        self,
        candidate_id: int,
        documents_folder: str,
        candidate_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validate all documents in a candidate's folder.

        Args:
            candidate_id: Database ID of the candidate
            documents_folder: Path to folder containing documents
            candidate_name: Expected candidate name for name validation

        Returns:
            Validation results for all documents
        """
        results = {
            "candidate_id": candidate_id,
            "candidate_name": candidate_name,
            "validated": [],
            "invalid": [],
            "errors": [],
            "summary": {}
        }

        if not os.path.exists(documents_folder):
            results["errors"].append(f"Documents folder not found: {documents_folder}")
            return results

        # Get all files in folder
        files = [f for f in os.listdir(documents_folder)
                 if f.lower().endswith(('.png', '.jpg', '.jpeg', '.pdf'))]

        if not files:
            results["errors"].append("No documents found in folder")
            return results

        # Get or create document tracker entries
        for filename in files:
            file_path = os.path.join(documents_folder, filename)

            try:
                validation_result = await self._validate_single_document(
                    candidate_id, file_path, filename, candidate_name
                )

                if validation_result.get("is_valid") and validation_result.get("name_match", True):
                    results["validated"].append(validation_result)
                else:
                    results["invalid"].append(validation_result)

            except Exception as e:
                results["errors"].append({
                    "file": filename,
                    "error": str(e)
                })

        # Update summary
        results["summary"] = {
            "total_files": len(files),
            "validated": len(results["validated"]),
            "invalid": len(results["invalid"]),
            "errors": len(results["errors"])
        }

        return results

    async def _validate_single_document(
        self,
        candidate_id: int,
        file_path: str,
        filename: str,
        candidate_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Validate a single document and update tracker."""
        result = {
            "filename": filename,
            "file_path": file_path,
            "is_valid": False,
            "name_match": False,
            "document_type": None,
            "confidence": 0,
            "extracted_name": "",
            "issues": []
        }

        # Run OCR/LLM validation
        if filename.lower().endswith('.pdf'):
            # PDF validation
            validation = await self._validate_pdf(file_path, candidate_name)
        else:
            # Image validation using Vision LLM
            validation = await self.llm_service.validate_document_vision(
                file_path, candidate_name=candidate_name
            )

        result["document_type"] = validation.get("document_type", "Unknown")
        result["confidence"] = validation.get("confidence", 0)
        result["extracted_name"] = validation.get("extracted_name", "")
        result["name_match"] = validation.get("name_match", False)
        result["is_sample"] = validation.get("is_sample", False)

        # Build issues list
        issues = validation.get("issues", [])
        if validation.get("is_sample"):
            issues.append("Document appears to be a sample/placeholder")
        if candidate_name and not validation.get("name_match", False):
            issues.append(f"Name mismatch: expected '{candidate_name}', found '{result['extracted_name']}'")
        if validation.get("confidence", 0) < 70:
            issues.append(f"Low confidence: {validation.get('confidence', 0):.1f}%")

        result["issues"] = issues

        # Document is valid if:
        # 1. Confidence >= 70%
        # 2. Not a sample document
        # 3. Name matches (if candidate name provided)
        # 4. No critical issues
        is_valid = (
            validation.get("confidence", 0) >= 70 and
            not validation.get("is_sample", False) and
            (not candidate_name or validation.get("name_match", False)) and
            not any("critical" in issue.lower() for issue in issues)
        )
        result["is_valid"] = is_valid

        # Update or create document tracker entry
        await self._update_tracker(
            candidate_id=candidate_id,
            filename=filename,
            document_type=result["document_type"],
            is_valid=is_valid,
            confidence=result["confidence"],
            issues=result["issues"],
            name_match=result["name_match"],
            extracted_name=result["extracted_name"]
        )

        return result

    async def _validate_pdf(self, file_path: str, candidate_name: Optional[str] = None) -> Dict[str, Any]:
        """Validate PDF document using OCR."""
        try:
            import pdfplumber

            text = ""
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages[:2]:  # Check first 2 pages
                    text += page.extract_text() or ""

            # Determine document type from text content
            text_lower = text.lower()

            # Extract name from PDF text
            extracted_name = self._extract_name_from_text(text)

            # Check if name matches
            name_match = False
            if candidate_name and extracted_name:
                candidate_normalized = candidate_name.lower().replace(" ", "")
                extracted_normalized = extracted_name.lower().replace(" ", "")
                name_match = candidate_normalized in extracted_normalized or extracted_normalized in candidate_normalized
            elif not candidate_name:
                name_match = True  # No name to check

            # Check for sample/placeholder documents
            is_sample = any(keyword in text_lower for keyword in
                           ['sample', 'test', 'demo', 'placeholder', 'dummy', 'example'])

            if "experience" in text_lower and "certificate" in text_lower:
                return {
                    "document_type": "Experience Certificate",
                    "confidence": 85,
                    "extracted_name": extracted_name,
                    "name_match": name_match,
                    "is_sample": is_sample
                }
            elif "relieving" in text_lower:
                return {
                    "document_type": "Relieving Letter",
                    "confidence": 85,
                    "extracted_name": extracted_name,
                    "name_match": name_match,
                    "is_sample": is_sample
                }
            elif "salary" in text_lower or "pay slip" in text_lower:
                return {
                    "document_type": "Salary Slip",
                    "confidence": 80,
                    "extracted_name": extracted_name,
                    "name_match": name_match,
                    "is_sample": is_sample
                }
            elif "form 16" in text_lower or "tax" in text_lower:
                return {
                    "document_type": "Form 16",
                    "confidence": 80,
                    "extracted_name": extracted_name,
                    "name_match": name_match,
                    "is_sample": is_sample
                }
            elif "marksheet" in text_lower or "certificate" in text_lower:
                return {
                    "document_type": "Educational Document",
                    "confidence": 75,
                    "extracted_name": extracted_name,
                    "name_match": name_match,
                    "is_sample": is_sample
                }
            else:
                return {
                    "document_type": "Unknown Document",
                    "confidence": 30,
                    "extracted_name": extracted_name,
                    "name_match": name_match,
                    "is_sample": is_sample
                }

        except Exception as e:
            logger.error(f"PDF validation error: {e}")
            return {"document_type": "Unknown", "confidence": 0, "issues": [str(e)]}

    def _extract_name_from_text(self, text: str) -> str:
        """Extract person's name from document text."""
        import re

        # Common patterns for names in documents
        patterns = [
            r'(?:Name|नाम|NAME)\s*[:\-]?\s*([A-Z][a-zA-Z\s]+)',
            r'(?:Candidate|Employee|Student)\s*[:\-]?\s*([A-Z][a-zA-Z\s]+)',
            r'To\s+Whom\s+It\s+May\s+Concern[^.]*?(?:Mr\.?|Ms\.?|Mrs\.?)?\s*([A-Z][a-zA-Z\s]+)',
            r'(?:This\s+is\s+to\s+certify[^.]*?(?:Mr\.?|Ms\.?|Mrs\.?)?\s*([A-Z][a-zA-Z\s]+))',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                # Clean up name
                name = re.sub(r'\s+', ' ', name)
                # Remove common non-name words
                name = re.sub(r'\b(DOB|Date|Birth|Father|Mother|Son|Daughter|of)\b.*', '', name, flags=re.IGNORECASE)
                if len(name) > 2 and len(name) < 50:
                    return name.strip()

        return ""

    async def _update_tracker(
        self,
        candidate_id: int,
        filename: str,
        document_type: str,
        is_valid: bool,
        confidence: float,
        issues: List[str],
        name_match: bool = True,
        extracted_name: str = ""
    ) -> None:
        """Update document tracker with validation result."""
        # Find document type ID
        doc_type_result = await self.db.execute(
            select(DocumentTypeMaster).where(
                DocumentTypeMaster.document_name == document_type
            )
        )
        doc_type = doc_type_result.scalar_one_or_none()

        if not doc_type:
            # Try fuzzy match
            doc_type_result = await self.db.execute(
                select(DocumentTypeMaster)
            )
            all_types = doc_type_result.scalars().all()

            for t in all_types:
                if t.document_name.lower() in document_type.lower() or \
                   document_type.lower() in t.document_name.lower():
                    doc_type = t
                    break

        # Get status IDs
        if is_valid:
            status_id = StatusType.COMPLETE
        else:
            status_id = StatusType.FAILED

        # Build comment with all validation details
        comment_parts = [f"Validated: {confidence:.1f}% confidence"]
        if extracted_name:
            comment_parts.append(f"Name found: '{extracted_name}'")
        if not name_match:
            comment_parts.append("NAME MISMATCH")
        if issues:
            comment_parts.append(f"Issues: {', '.join(issues)}")
        comment = ". ".join(comment_parts)

        # Check if tracker entry exists
        if doc_type:
            existing = await self.db.execute(
                select(DocumentTracker).where(
                    DocumentTracker.candidate_id == candidate_id,
                    DocumentTracker.document_type_id == doc_type.document_type_id,
                    DocumentTracker.is_active == True
                )
            )
            tracker_entry = existing.scalar_one_or_none()

            if tracker_entry:
                # Update existing entry
                tracker_entry.status_id = status_id
                tracker_entry.comments = comment
                tracker_entry.updated_on = datetime.utcnow()
            else:
                # Create new entry
                tracker_entry = DocumentTracker(
                    candidate_id=candidate_id,
                    document_type_id=doc_type.document_type_id,
                    status_id=status_id,
                    comments=f"{comment}. File: {filename}",
                    document_received_on=datetime.utcnow().date(),
                    is_active=True
                )
                self.db.add(tracker_entry)

            await self.db.commit()

    def get_tool_schema(self) -> Dict[str, Any]:
        """Return the tool schema for MCP."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "candidate_id": {
                        "type": "integer",
                        "description": "Database ID of the candidate"
                    },
                    "documents_folder": {
                        "type": "string",
                        "description": "Path to folder containing documents"
                    },
                    "candidate_name": {
                        "type": "string",
                        "description": "Expected candidate name for name validation"
                    }
                },
                "required": ["candidate_id", "documents_folder"]
            }
        }