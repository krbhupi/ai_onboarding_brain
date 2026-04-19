"""MCP Tool: Segregate documents into categories."""
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import shutil

from config.settings import get_settings
from config.logging import logger
from src.constants.constants import DocumentCategory

settings = get_settings()


class SegregationTool:
    """Tool for organizing documents into categories after validation."""

    def __init__(self, storage_path: str = None):
        self.storage_path = Path(storage_path or settings.DOCUMENT_STORAGE_PATH)
        self.name = "segregation"
        self.description = "Organize validated documents into category folders"

    async def execute(
        self,
        cin: str,
        documents: List[Dict[str, Any]],
        validation_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Segregate documents into appropriate categories.

        Args:
            cin: Candidate identification number
            documents: List of document dictionaries with paths
            validation_results: Validation results from OCRValidationTool

        Returns:
            Segregation result with organized document paths
        """
        result = {
            "cin": cin,
            "categories": {
                DocumentCategory.EDUCATION: [],
                DocumentCategory.EMPLOYMENT: [],
                DocumentCategory.PERSONAL_DETAILS: [],
                DocumentCategory.UNMATCHED: []
            },
            "total_processed": 0,
            "total_valid": 0,
            "total_invalid": 0,
            "errors": []
        }

        # Ensure candidate directory exists
        candidate_dir = self.storage_path / cin
        candidate_dir.mkdir(parents=True, exist_ok=True)

        # Create category directories
        for category in result["categories"].keys():
            category_dir = candidate_dir / category
            category_dir.mkdir(exist_ok=True)

        # Process each document
        for doc, validation in zip(documents, validation_results):
            try:
                doc_path = Path(doc.get("path", ""))
                original_name = doc_path.name

                if not doc_path.exists():
                    result["errors"].append(f"Document not found: {original_name}")
                    continue

                # Determine category from validation result
                if validation.get("is_valid"):
                    category = validation.get("category", DocumentCategory.UNMATCHED)
                    result["total_valid"] += 1
                else:
                    category = DocumentCategory.UNMATCHED
                    result["total_invalid"] += 1

                # Move to category directory
                dest_path = candidate_dir / category / original_name

                if category != DocumentCategory.UNMATCHED:
                    # Rename to include CIN for traceability
                    new_name = f"{validation.get('expected_type', 'document')}_{cin}_{original_name}"
                    new_name = new_name.replace(" ", "_")
                    dest_path = candidate_dir / category / new_name

                # Copy file (keep original in unmatched for reference)
                shutil.copy2(doc_path, dest_path)

                # Add CIN prefix to filename
                dest_path = candidate_dir / category / f"{cin}_{original_name}"

                result["categories"][category].append({
                    "original_name": original_name,
                    "new_name": dest_path.name,
                    "path": str(dest_path),
                    "expected_type": validation.get("expected_type"),
                    "is_valid": validation.get("is_valid"),
                    "confidence": validation.get("confidence", 0.0)
                })

                result["total_processed"] += 1

            except Exception as e:
                logger.error(f"Error segregating document {doc}: {e}")
                result["errors"].append(str(e))

        # Update status in DocumentTracker if database is available
        await self._update_document_status(result)

        logger.info(
            f"Segregation complete for {cin}: "
            f"{result['total_valid']} valid, {result['total_invalid']} invalid"
        )

        return result

    async def _update_document_status(self, result: Dict[str, Any]) -> None:
        """Update document status in database after segregation."""
        # This would update the DocumentTracker table
        # Implementation depends on database integration
        pass

    def categorize_by_type(self, document_type: str) -> str:
        """Determine document category based on type name."""
        education_keywords = [
            "marksheet", "certificate", "degree", "diploma",
            "10th", "12th", "hsc", "ssc", "graduation", "post graduation"
        ]
        employment_keywords = [
            "relieving", "experience", "salary", "offer", "appointment",
            "form 16", "form16", "payslip"
        ]
        personal_keywords = [
            "aadhar", "aadhaar", "pan", "passport", "photo",
            "bank", "cheque", "address"
        ]

        doc_lower = document_type.lower()

        for keyword in education_keywords:
            if keyword in doc_lower:
                return DocumentCategory.EDUCATION

        for keyword in employment_keywords:
            if keyword in doc_lower:
                return DocumentCategory.EMPLOYMENT

        for keyword in personal_keywords:
            if keyword in doc_lower:
                return DocumentCategory.PERSONAL_DETAILS

        return DocumentCategory.UNMATCHED

    async def reorganize_directory(
        self,
        cin: str,
        revalidation_results: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Reorganize an existing candidate directory.

        Args:
            cin: Candidate identification number
            revalidation_results: Optional new validation results

        Returns:
            Reorganization summary
        """
        candidate_dir = self.storage_path / cin

        if not candidate_dir.exists():
            return {
                "error": f"Directory not found for CIN: {cin}",
                "processed": False
            }

        # Collect all documents from all subdirectories
        all_documents = []
        for category_dir in candidate_dir.iterdir():
            if category_dir.is_dir():
                for doc_file in category_dir.glob("*"):
                    if doc_file.is_file():
                        all_documents.append({
                            "path": str(doc_file),
                            "current_category": category_dir.name
                        })

        # If revalidation results provided, re-segregate
        if revalidation_results:
            # Match results with documents
            for doc in all_documents:
                doc_path = Path(doc["path"])
                for result in revalidation_results:
                    if result.get("path") == str(doc_path):
                        doc["validation"] = result
                        break

        return {
            "cin": cin,
            "documents_found": len(all_documents),
            "categories_found": [
                d.name for d in candidate_dir.iterdir() if d.is_dir()
            ]
        }

    def get_document_summary(
        self,
        cin: str
    ) -> Dict[str, Any]:
        """
        Get summary of documents for a candidate.

        Args:
            cin: Candidate identification number

        Returns:
            Document summary by category
        """
        candidate_dir = self.storage_path / cin

        if not candidate_dir.exists():
            return {
                "cin": cin,
                "exists": False,
                "documents": {}
            }

        summary = {
            "cin": cin,
            "exists": True,
            "categories": {},
            "total_documents": 0
        }

        for category in [
            DocumentCategory.EDUCATION,
            DocumentCategory.EMPLOYMENT,
            DocumentCategory.PERSONAL_DETAILS,
            DocumentCategory.UNMATCHED
        ]:
            category_dir = candidate_dir / category
            if category_dir.exists():
                files = list(category_dir.glob("*"))
                summary["categories"][category] = {
                    "count": len([f for f in files if f.is_file()]),
                    "files": [f.name for f in files if f.is_file()]
                }
                summary["total_documents"] += len([f for f in files if f.is_file()])

        return summary

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
                    "documents": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string"},
                                "type": {"type": "string"}
                            }
                        },
                        "description": "List of document paths"
                    },
                    "validation_results": {
                        "type": "array",
                        "description": "Validation results from OCRValidationTool"
                    }
                },
                "required": ["cin", "documents"]
            }
        }