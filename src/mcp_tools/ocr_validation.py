"""MCP Tool: OCR validation for documents using LLM."""
from pathlib import Path
from typing import Dict, Any, Optional, List
import asyncio

from config.settings import get_settings
from config.logging import logger
from src.services.llm_service import LLMService
from src.constants.constants import DocumentCategory

settings = get_settings()


class OCRValidationTool:
    """Tool for validating documents using OCR and LLM."""

    def __init__(self, llm_service: LLMService = None):
        self.llm_service = llm_service or LLMService()
        self.name = "ocr_validation"
        self.description = "Validate document type using OCR and LLM"

    async def execute(
        self,
        document_path: str,
        expected_type: str,
        cin: str = ""
    ) -> Dict[str, Any]:
        """
        Validate a document against expected type.

        Args:
            document_path: Path to the document file
            expected_type: Expected document type (e.g., 'Aadhaar Card', 'PAN Card')
            cin: Candidate identification number

        Returns:
            Validation result with extracted information
        """
        document_path = Path(document_path)

        if not document_path.exists():
            return {
                "is_valid": False,
                "confidence": 0.0,
                "error": "Document file not found",
                "path": str(document_path)
            }

        # Extract text from document
        extracted_text = await self._extract_text(document_path)

        if not extracted_text:
            return {
                "is_valid": False,
                "confidence": 0.0,
                "error": "Could not extract text from document",
                "path": str(document_path)
            }

        # Validate using LLM
        validation_result = await self.llm_service.validate_document(
            extracted_text,
            expected_type
        )

        # Add metadata
        validation_result["document_path"] = str(document_path)
        validation_result["expected_type"] = expected_type
        validation_result["cin"] = cin
        validation_result["extracted_text_length"] = len(extracted_text)

        # Determine category based on validation
        if validation_result.get("is_valid"):
            category = self._determine_category(expected_type)
            validation_result["category"] = category

        logger.info(
            f"Document validation: {expected_type} - "
            f"Valid: {validation_result.get('is_valid')}, "
            f"Confidence: {validation_result.get('confidence')}"
        )

        return validation_result

    async def _extract_text(self, document_path: Path) -> str:
        """Extract text from document based on file type."""
        suffix = document_path.suffix.lower()

        if suffix == ".pdf":
            return await self._extract_from_pdf(document_path)
        elif suffix in [".jpg", ".jpeg", ".png", ".bmp"]:
            return await self._extract_from_image(document_path)
        elif suffix in [".doc", ".docx"]:
            return await self._extract_from_docx(document_path)
        elif suffix in [".txt", ".csv"]:
            return await self._extract_from_text(document_path)
        else:
            return await self._extract_generic(document_path)

    async def _extract_from_pdf(self, path: Path) -> str:
        """Extract text from PDF file."""
        try:
            # Try PyPDF2 first
            from PyPDF2 import PdfReader
            reader = PdfReader(str(path))
            text_parts = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
            return "\n".join(text_parts)
        except ImportError:
            logger.warning("PyPDF2 not installed, falling back to basic extraction")
            return await self._extract_generic(path)
        except Exception as e:
            logger.error(f"PDF extraction error: {e}")
            return ""

    async def _extract_from_image(self, path: Path) -> str:
        """Extract text from image using OCR."""
        try:
            # Try pytesseract if available
            import pytesseract
            from PIL import Image

            loop = asyncio.get_event_loop()
            text = await loop.run_in_executor(
                None,
                lambda: pytesseract.image_to_string(Image.open(path))
            )
            return text
        except ImportError:
            logger.warning("pytesseract not installed, returning image description")
            return f"[Image file: {path.name}]"
        except Exception as e:
            logger.error(f"Image OCR error: {e}")
            return ""

    async def _extract_from_docx(self, path: Path) -> str:
        """Extract text from Word document."""
        try:
            from docx import Document
            doc = Document(str(path))
            return "\n".join([para.text for para in doc.paragraphs])
        except ImportError:
            logger.warning("python-docx not installed")
            return await self._extract_generic(path)
        except Exception as e:
            logger.error(f"DOCX extraction error: {e}")
            return ""

    async def _extract_from_text(self, path: Path) -> str:
        """Read text file directly."""
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        except Exception as e:
            logger.error(f"Text file read error: {e}")
            return ""

    async def _extract_generic(self, path: Path) -> str:
        """Generic text extraction attempt."""
        try:
            with open(path, "rb") as f:
                content = f.read()
            # Try to decode as text
            try:
                return content.decode("utf-8", errors="ignore")
            except UnicodeDecodeError:
                return content.decode("latin-1", errors="ignore")
        except Exception as e:
            logger.error(f"Generic extraction error: {e}")
            return ""

    def _determine_category(self, document_type: str) -> str:
        """Determine document category based on type."""
        return self.llm_service.document_service.categorize_document(document_type)

    async def validate_batch(
        self,
        documents: List[Dict[str, Any]],
        cin: str
    ) -> List[Dict[str, Any]]:
        """
        Validate multiple documents in batch.

        Args:
            documents: List of document dictionaries with path and expected_type
            cin: Candidate identification number

        Returns:
            List of validation results
        """
        tasks = [
            self.execute(doc["path"], doc["expected_type"], cin)
            for doc in documents
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append({
                    "is_valid": False,
                    "confidence": 0.0,
                    "error": str(result),
                    "path": documents[i]["path"]
                })
            else:
                processed_results.append(result)

        return processed_results

    def get_tool_schema(self) -> Dict[str, Any]:
        """Return the tool schema for MCP."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "document_path": {
                        "type": "string",
                        "description": "Path to the document file"
                    },
                    "expected_type": {
                        "type": "string",
                        "description": "Expected document type (e.g., 'Aadhaar Card')"
                    },
                    "cin": {
                        "type": "string",
                        "description": "Candidate identification number"
                    }
                },
                "required": ["document_path", "expected_type"]
            }
        }