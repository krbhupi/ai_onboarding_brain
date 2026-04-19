"""LLM service for Ollama Cloud integration."""
import os
import base64
from typing import Dict, Any, Optional, List
import httpx
from pathlib import Path

from config.settings import get_settings
from config.logging import logger

settings = get_settings()


class LLMService:
    """Service for LLM operations via Ollama Cloud."""

    def __init__(self):
        self.base_url = settings.LLM_BASE_URL
        self.model = settings.LLM_MODEL
        self.timeout = settings.LLM_TIMEOUT
        self.api_key = settings.OLLAMA_API_KEY or os.getenv("OLLAMA_API_KEY")

        # Vision configuration
        self.vision_backend = os.getenv("VISION_BACKEND", "ocr_fallback")
        self.vision_model = os.getenv("VISION_MODEL", "llava:13b")
        self.vision_base_url = os.getenv("VISION_BASE_URL", "http://localhost:11434")

        # Build headers for authentication
        self.headers = {}
        if self.api_key:
            self.headers["Authorization"] = f"Bearer {self.api_key}"

    async def _call_llm(
        self,
        prompt: str,
        system_prompt: Optional[str] = None
    ) -> str:
        """Make a call to the LLM API."""
        url = f"{self.base_url}/api/generate"

        headers = {"Content-Type": "application/json"}
        headers.update(self.headers)

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False
        }

        if system_prompt:
            payload["system"] = system_prompt

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                result = response.json()
                return result.get("response", "")
            except httpx.HTTPError as e:
                logger.error(f"LLM API error: {e}")
                raise

    async def validate_document(
        self,
        document_text: str,
        expected_type: str
    ) -> Dict[str, Any]:
        """Validate if document matches expected type using LLM."""
        system_prompt = """You are a document validation assistant.
Analyze the extracted text from a document and determine if it matches the expected document type.
Return a JSON response with:
- "is_valid": boolean indicating if the document matches
- "confidence": float between 0 and 1
- "extracted_info": object with key information found (name, date, id_number, etc.)
- "reason": string explaining the validation result"""

        prompt = f"""Expected document type: {expected_type}

Document content:
{document_text}

Is this document a valid {expected_type}? Analyze the content and provide your assessment."""

        try:
            response = await self._call_llm(prompt, system_prompt)

            # Try to parse JSON from response
            json_start = response.find("{")
            json_end = response.rfind("}") + 1

            if json_start >= 0 and json_end > json_start:
                import json
                json_str = response[json_start:json_end]
                return json.loads(json_str)

            return {
                "is_valid": False,
                "confidence": 0.0,
                "extracted_info": {},
                "reason": "Could not parse LLM response"
            }

        except Exception as e:
            logger.error(f"Document validation error: {e}")
            return {
                "is_valid": False,
                "confidence": 0.0,
                "extracted_info": {},
                "reason": f"Error: {str(e)}"
            }

    async def classify_email_reply(
        self,
        email_body: str
    ) -> Dict[str, Any]:
        """Classify candidate email reply and extract dates."""
        system_prompt = """You are an email classification assistant.
Analyze the email and classify the candidate's response.
Return a JSON response with:
- "category": one of "documents_attached", "request_extension", "query", "acknowledgment", "other"
- "documents_list": array of mentioned documents
- "proposed_date": ISO format date if mentioned, null otherwise
- "urgency": "high", "medium", or "low"
- "summary": brief summary of the email content"""

        prompt = f"""Email content:
{email_body}

Classify this email reply from a candidate regarding document submission."""

        try:
            response = await self._call_llm(prompt, system_prompt)
            import json
            json_start = response.find("{")
            json_end = response.rfind("}") + 1

            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                return json.loads(json_str)

            return {
                "category": "other",
                "documents_list": [],
                "proposed_date": None,
                "urgency": "medium",
                "summary": "Could not parse response"
            }

        except Exception as e:
            logger.error(f"Email classification error: {e}")
            return {
                "category": "other",
                "documents_list": [],
                "proposed_date": None,
                "urgency": "medium",
                "summary": f"Error: {str(e)}"
            }

    async def generate_followup_email(
        self,
        candidate_name: str,
        missing_documents: List[str],
        days_since_last_contact: int,
        previous_communications: Optional[str] = None
    ) -> str:
        """Generate a follow-up email draft using LLM."""
        system_prompt = """You are an HR communication assistant.
Generate professional, polite follow-up emails for document collection.
Keep the tone friendly but professional. Include specific document names.
Do not include placeholders - use actual information provided."""

        prompt = f"""Generate a follow-up email for:

Candidate name: {candidate_name}
Missing documents: {', '.join(missing_documents)}
Days since last contact: {days_since_last_contact}
Previous context: {previous_communications or 'First follow-up'}

Write a professional email requesting the missing documents."""

        return await self._call_llm(prompt, system_prompt)

    async def analyze_gap(
        self,
        required_documents: List[str],
        received_documents: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Perform gap analysis on submitted documents."""
        system_prompt = """You are a document gap analysis assistant.
Compare required documents with received documents and identify gaps.
Return JSON with:
- "missing_documents": array of still-needed documents
- "complete_documents": array of validated documents
- "invalid_documents": array of documents that failed validation
- "next_steps": suggested actions"""

        received_summary = "\n".join([
            f"- {d.get('type', 'unknown')}: {d.get('status', 'unknown')}"
            for d in received_documents
        ])

        prompt = f"""Required documents:
{chr(10).join([f'- {d}' for d in required_documents])}

Received documents:
{received_summary}

Perform gap analysis and identify what's missing or invalid."""

        try:
            response = await self._call_llm(prompt, system_prompt)
            import json
            json_start = response.find("{")
            json_end = response.rfind("}") + 1

            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                return json.loads(json_str)

            return {
                "missing_documents": required_documents,
                "complete_documents": [],
                "invalid_documents": [],
                "next_steps": ["Review all documents"]
            }

        except Exception as e:
            logger.error(f"Gap analysis error: {e}")
            return {
                "missing_documents": required_documents,
                "complete_documents": [],
                "invalid_documents": [],
                "next_steps": ["Manual review required"]
            }

    async def health_check(self) -> bool:
        """Check if LLM service is available."""
        url = f"{self.base_url}/api/tags"
        headers = {"Content-Type": "application/json"}
        headers.update(self.headers)

        async with httpx.AsyncClient(timeout=10) as client:
            try:
                response = await client.get(url, headers=headers)
                return response.status_code == 200
            except httpx.HTTPError:
                return False

    async def validate_document_vision(
        self,
        image_path: str,
        expected_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """Validate document using Vision LLM (VLLM).

        Processes image/PDF directly using vision model to:
        1. Identify document type
        2. Extract key information
        3. Validate document authenticity

        Supports multiple backends:
        - local_ollama: Local Ollama instance with vision model (llava)
        - ollama_cloud: Ollama Cloud API (may not support vision)
        - ocr_fallback: Extract text with OCR, then use text LLM

        Args:
            image_path: Path to image or PDF file
            expected_type: Expected document type (optional, for validation)

        Returns:
            Dict with validation results and extracted information
        """
        import json

        # Try vision backends in order
        if self.vision_backend == "local_ollama":
            return await self._validate_with_local_vision(image_path, expected_type)
        elif self.vision_backend == "ocr_fallback":
            return await self._validate_with_ocr_fallback(image_path, expected_type)
        else:
            # Default to OCR fallback
            return await self._validate_with_ocr_fallback(image_path, expected_type)

    async def _validate_with_local_vision(
        self,
        image_path: str,
        expected_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """Validate using local Ollama instance with vision model."""
        import json

        # Convert PDF to image if needed
        image_base64 = await self._prepare_image_for_vision(image_path)
        if not image_base64:
            return {
                "is_valid": False,
                "confidence": 0.0,
                "document_type": "Unknown",
                "extracted_info": {},
                "error": "Failed to process image"
            }

        system_prompt = """You are a document validation and OCR assistant.
Analyze the document image and identify:
1. Document type (Aadhaar Card, PAN Card, Degree Certificate, Bank Passbook/Cancelled Cheque, Marksheet, Experience Certificate, Relieving Letter, Salary Slip, Form 16, etc.)
2. Extract all visible text and key information
3. Determine if the document appears authentic

Return a JSON response with:
- "is_valid": boolean (true if document is readable and appears authentic)
- "document_type": string (identified document type)
- "confidence": float between 0 and 1
- "extracted_info": object with key information (name, dates, id_numbers, etc.)
- "text_content": full extracted text from the document"""

        prompt = f"""Analyze this document image and extract all information.
{f'Expected document type: {expected_type}' if expected_type else ''}

Identify the document type, validate it, and extract all relevant information.
Return results as JSON."""

        try:
            response = await self._call_vision_llm(prompt, system_prompt, image_base64)

            # Parse JSON response
            json_start = response.find("{")
            json_end = response.rfind("}") + 1

            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                result = json.loads(json_str)

                return {
                    "is_valid": result.get("is_valid", False),
                    "document_type": result.get("document_type", "Unknown"),
                    "confidence": result.get("confidence", 0.0),
                    "extracted_info": result.get("extracted_info", {}),
                    "text_content": result.get("text_content", ""),
                    "raw_response": response
                }

            return {
                "is_valid": False,
                "confidence": 0.0,
                "document_type": "Unknown",
                "extracted_info": {},
                "raw_response": response
            }

        except Exception as e:
            logger.error(f"Vision document validation error: {e}")
            return {
                "is_valid": False,
                "confidence": 0.0,
                "document_type": "Unknown",
                "extracted_info": {},
                "error": str(e)
            }

    async def _validate_with_ocr_fallback(
        self,
        image_path: str,
        expected_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """Validate using OCR text extraction + text LLM."""
        import json

        # Step 1: Extract text using OCR
        ocr_result = await self.ocr_extract_text(image_path)

        if not ocr_result.get("success"):
            return {
                "is_valid": False,
                "confidence": 0.0,
                "document_type": "Unknown",
                "extracted_info": {},
                "error": ocr_result.get("error", "OCR extraction failed")
            }

        extracted_text = ocr_result.get("text", "")

        if len(extracted_text.strip()) < 10:
            return {
                "is_valid": False,
                "confidence": 0.0,
                "document_type": "Unknown",
                "extracted_info": {},
                "error": "Insufficient text extracted"
            }

        # Step 2: Use text LLM to validate and classify
        system_prompt = """You are a document classification and validation assistant.
Analyze the extracted text from a document and:
1. Identify the document type (Aadhaar Card, PAN Card, Degree Certificate, Bank Passbook/Cancelled Cheque, Marksheet, Experience Certificate, Relieving Letter, Salary Slip, Form 16, etc.)
2. Extract key information (name, dates, id numbers, etc.)
3. Validate if the document appears authentic

Return a JSON response with:
- "is_valid": boolean (true if document appears authentic)
- "document_type": string (identified document type)
- "confidence": float between 0 and 1
- "extracted_info": object with key information"""

        prompt = f"""Analyze this document text and classify it:

{extracted_text[:2000]}

{f'Expected document type: {expected_type}' if expected_type else ''}

Identify the document type, extract key information, and validate.
Return results as JSON."""

        try:
            response = await self._call_llm(prompt, system_prompt)

            # Parse JSON response
            json_start = response.find("{")
            json_end = response.rfind("}") + 1

            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                result = json.loads(json_str)

                return {
                    "is_valid": result.get("is_valid", False),
                    "document_type": result.get("document_type", "Unknown"),
                    "confidence": result.get("confidence", 0.0),
                    "extracted_info": result.get("extracted_info", {}),
                    "text_content": extracted_text,
                    "ocr_confidence": ocr_result.get("confidence", 0.5)
                }

            return {
                "is_valid": False,
                "confidence": 0.0,
                "document_type": "Unknown",
                "extracted_info": {},
                "text_content": extracted_text
            }

        except Exception as e:
            logger.error(f"OCR + LLM validation error: {e}")
            return {
                "is_valid": False,
                "confidence": 0.0,
                "document_type": "Unknown",
                "extracted_info": {},
                "error": str(e)
            }

    async def _prepare_image_for_vision(self, file_path: str) -> Optional[str]:
        """Convert PDF to image or load existing image, return base64 encoded."""
        try:
            path = Path(file_path)

            if not path.exists():
                logger.error(f"File not found: {file_path}")
                return None

            # Handle PDF files
            if path.suffix.lower() == '.pdf':
                from pdf2image import convert_from_path
                images = convert_from_path(file_path, first_page=1, last_page=1)
                if images:
                    # Convert first page to base64
                    import io
                    buffer = io.BytesIO()
                    images[0].save(buffer, format='PNG')
                    return base64.b64encode(buffer.getvalue()).decode('utf-8')

            # Handle image files
            elif path.suffix.lower() in ['.png', '.jpg', '.jpeg', '.bmp', '.tiff']:
                with open(file_path, 'rb') as f:
                    return base64.b64encode(f.read()).decode('utf-8')

            return None

        except Exception as e:
            logger.error(f"Error preparing image for vision: {e}")
            return None

    async def _call_vision_llm(
        self,
        prompt: str,
        system_prompt: Optional[str],
        image_base64: str
    ) -> str:
        """Call vision-enabled LLM with image."""
        url = f"{self.base_url}/api/generate"

        headers = {"Content-Type": "application/json"}
        headers.update(self.headers)

        payload = {
            "model": self.vision_model,
            "prompt": prompt,
            "stream": False,
            "images": [image_base64]
        }

        if system_prompt:
            payload["system"] = system_prompt

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                result = response.json()
                return result.get("response", "")
            except httpx.HTTPError as e:
                logger.error(f"Vision LLM API error: {e}")
                raise

    async def ocr_extract_text(self, image_path: str) -> Dict[str, Any]:
        """Extract text from document using multiple methods.

        Tries in order:
        1. pdfplumber (for PDFs) - extracts embedded text
        2. PaddleOCR (for images) - neural network based OCR
        3. EasyOCR (alternative) - neural network based OCR
        4. pytesseract (fallback) - traditional OCR

        Returns:
            Dict with success status, extracted text, and confidence
        """
        path = Path(image_path)

        if not path.exists():
            return {"success": False, "error": f"File not found: {image_path}", "text": ""}

        # Try pdfplumber first for PDFs (extracts embedded text)
        if path.suffix.lower() == '.pdf':
            text = await self._extract_pdf_text(str(path))
            if text:
                return {
                    "success": True,
                    "text": text,
                    "confidence": 0.9,
                    "method": "pdfplumber"
                }

        # Try PaddleOCR for images (good accuracy, runs locally)
        try:
            from paddleocr import PaddleOCR
            import os
            os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'

            # Initialize OCR with English language
            ocr = PaddleOCR(lang='en')
            results = ocr.ocr(str(path))

            # Combine text results
            text_parts = []
            if results and results[0]:
                for line in results[0]:
                    if line and len(line) >= 2:
                        text_parts.append(line[1][0])

            text = "\n".join(text_parts)

            if text.strip():
                return {
                    "success": True,
                    "text": text,
                    "confidence": 0.85,
                    "method": "paddleocr"
                }

        except ImportError:
            logger.warning("paddleocr not installed")
        except Exception as e:
            logger.warning(f"PaddleOCR extraction failed: {e}")

        # Try EasyOCR for images (better accuracy)
        try:
            import easyocr

            reader = easyocr.Reader(['en'], gpu=False)
            results = reader.readtext(str(path))

            # Combine text results
            text_parts = [result[1] for result in results]
            text = "\n".join(text_parts)

            if text.strip():
                # Calculate average confidence
                avg_confidence = sum(result[2] for result in results) / len(results) if results else 0.5
                return {
                    "success": True,
                    "text": text,
                    "confidence": avg_confidence,
                    "method": "easyocr"
                }

        except ImportError:
            logger.warning("easyocr not installed, trying pytesseract")
        except Exception as e:
            logger.warning(f"EasyOCR extraction failed: {e}")

        # Try pytesseract for images and PDFs
        try:
            from PIL import Image
            import pytesseract

            if path.suffix.lower() == '.pdf':
                from pdf2image import convert_from_path
                images = convert_from_path(image_path, first_page=1, last_page=3)
                if images:
                    text_parts = []
                    for img in images:
                        text_parts.append(pytesseract.image_to_string(img))
                    text = "\n".join(text_parts)
                    return {
                        "success": True,
                        "text": text,
                        "confidence": 0.7,
                        "method": "pytesseract"
                    }
            else:
                img = Image.open(image_path)
                text = pytesseract.image_to_string(img)
                return {
                    "success": True,
                    "text": text,
                    "confidence": 0.7,
                    "method": "pytesseract"
                }

        except ImportError:
            logger.warning("pytesseract not installed, skipping OCR")
        except Exception as e:
            logger.warning(f"OCR extraction failed: {e}")

        # Return failure if all methods failed
        return {
            "success": False,
            "error": "All text extraction methods failed",
            "text": ""
        }

    async def _extract_pdf_text(self, pdf_path: str) -> Optional[str]:
        """Extract embedded text from PDF using pdfplumber."""
        try:
            import pdfplumber

            text_parts = []
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages[:3]:  # First 3 pages
                    text = page.extract_text()
                    if text:
                        text_parts.append(text)

            return "\n".join(text_parts) if text_parts else None

        except ImportError:
            # Try PyMuPDF as fallback
            try:
                import fitz
                doc = fitz.open(pdf_path)
                text_parts = []
                for page in doc[:3]:
                    text_parts.append(page.get_text())
                doc.close()
                return "\n".join(text_parts) if text_parts else None
            except ImportError:
                logger.warning("Neither pdfplumber nor PyMuPDF installed")
                return None
        except Exception as e:
            logger.error(f"PDF text extraction error: {e}")
            return None