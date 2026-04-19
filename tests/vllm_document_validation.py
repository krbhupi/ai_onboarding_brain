#!/usr/bin/env python
"""
VLLM Document Validation Pipeline

This script:
1. Reads emails from inbox
2. Extracts attachments (PDF/images)
3. Uses Vision LLM to identify and validate documents
4. Updates document tracking status
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from src.core.database import get_db, init_db
from src.models.database import CandidateInfo, DocumentTracker, DocumentTypeMaster
from src.constants.constants import StatusType
from src.services.email_service import EmailService
from src.services.llm_service import LLMService
from config.settings import get_settings

settings = get_settings()


async def process_attachments_with_vllm(candidate_email: str = "kr_bhupi@outlook.com"):
    """Process email attachments using Vision LLM."""
    print("\n" + "="*70)
    print("VLLM DOCUMENT VALIDATION PIPELINE")
    print("="*70)

    # Initialize services
    email_service = EmailService()
    llm = LLMService()
    await init_db()

    # Create storage directory
    storage_path = Path(settings.DOCUMENT_STORAGE_PATH)
    storage_path.mkdir(parents=True, exist_ok=True)

    print(f"\nStorage Path: {storage_path}")
    print(f"Vision Model: {llm.vision_model}")
    print(f"LLM Model: {llm.model}")

    async for db in get_db():
        # Find candidate
        result = await db.execute(
            select(CandidateInfo).where(CandidateInfo.personal_email_id == candidate_email)
        )
        candidate = result.scalar_one_or_none()

        if not candidate:
            print(f"\nCandidate not found: {candidate_email}")
            return

        print(f"\nCandidate: {candidate.candidate_name} (ID: {candidate.candidate_id})")

        # Create candidate folder
        candidate_folder = storage_path / f"CIN-{candidate.candidate_id}"
        candidate_folder.mkdir(exist_ok=True)

        # Get document types
        result = await db.execute(select(DocumentTypeMaster))
        doc_types = {dt.document_name.lower(): dt.document_type_id for dt in result.scalars().all()}

        # Step 1: Read emails from inbox
        print("\n[STEP 1] Reading inbox for attachments...")
        emails = await email_service.read_inbox(unread_only=False, limit=10)

        emails_with_attachments = [e for e in emails if e.get('attachments')]
        print(f"Found {len(emails_with_attachments)} emails with attachments")

        validated_docs = []

        # Step 2: Process each email's attachments
        for email in emails_with_attachments[:5]:  # Limit to first 5
            from_addr = email.get('from_address', '')
            subject = email.get('subject', '')
            attachments = email.get('attachments', [])

            print(f"\n--- Processing Email ---")
            print(f"From: {from_addr}")
            print(f"Subject: {subject}")
            print(f"Attachments: {len(attachments)}")

            for att in attachments:
                filename = att.get('filename', 'unknown')
                content_type = att.get('content_type', '')
                size = att.get('size', 0)

                print(f"\n  Attachment: {filename}")
                print(f"  Type: {content_type}")
                print(f"  Size: {size} bytes")

                # Skip non-document files
                if not any(x in content_type.lower() for x in ['pdf', 'image', 'octet-stream']):
                    print("  Skipped: Not a document file")
                    continue

                # Save attachment
                save_path = candidate_folder / filename

                try:
                    # Save the attachment
                    await email_service.save_attachment(att, save_path)
                    print(f"  Saved to: {save_path}")

                    # Step 3: Validate using Vision LLM
                    print(f"  Validating with Vision LLM...")

                    # Try VLLM first
                    validation_result = await llm.validate_document_vision(
                        image_path=str(save_path),
                        expected_type=None  # Auto-detect
                    )

                    # If VLLM fails, fallback to OCR + text validation
                    if not validation_result.get('is_valid') and 'error' in validation_result:
                        print("  VLLM failed, trying OCR fallback...")
                        ocr_result = await llm.ocr_extract_text(str(save_path))

                        if ocr_result.get('success'):
                            validation_result = await llm.validate_document(
                                document_text=ocr_result.get('text', ''),
                                expected_type="unknown"
                            )

                    doc_type = validation_result.get('document_type', 'Unknown')
                    is_valid = validation_result.get('is_valid', False)
                    confidence = validation_result.get('confidence', 0)
                    extracted_info = validation_result.get('extracted_info', {})

                    print(f"  Document Type: {doc_type}")
                    print(f"  Valid: {'✓ YES' if is_valid else '✗ NO'}")
                    print(f"  Confidence: {confidence:.1%}")

                    if extracted_info:
                        print(f"  Extracted Info:")
                        for key, value in extracted_info.items():
                            print(f"    - {key}: {value}")

                    # Match with document types and update tracker
                    if is_valid:
                        doc_type_lower = doc_type.lower()
                        doc_type_id = None

                        for name, id in doc_types.items():
                            if name in doc_type_lower or doc_type_lower in name:
                                doc_type_id = id
                                matched_name = name
                                break

                        if doc_type_id:
                            result = await db.execute(
                                select(DocumentTracker).where(
                                    DocumentTracker.candidate_id == candidate.candidate_id,
                                    DocumentTracker.document_type_id == doc_type_id
                                )
                            )
                            tracker = result.scalar_one_or_none()

                            if tracker:
                                tracker.status_id = StatusType.COMPLETE
                                tracker.document_received_on = datetime.utcnow().date()
                                validated_docs.append({
                                    'filename': filename,
                                    'type': matched_name,
                                    'valid': is_valid
                                })
                                print(f"  ✓ Document tracked: {matched_name}")

                except Exception as e:
                    print(f"  Error processing {filename}: {e}")
                    import traceback
                    traceback.print_exc()

        await db.commit()

        # Step 4: Run gap analysis
        print("\n[STEP 4] Running gap analysis...")
        from src.mcp_tools.gap_analysis import GapAnalysisTool

        gap_tool = GapAnalysisTool(db)
        gap_result = await gap_tool.execute(candidate_id=candidate.candidate_id)

        print("\n" + "="*70)
        print("VALIDATION SUMMARY")
        print("="*70)
        print(f"Candidate: {candidate.candidate_name}")
        print(f"Email: {candidate.personal_email_id}")
        print(f"\nDocument Completion: {gap_result.get('completion_percentage', 0):.1f}%")
        print(f"Documents Received: {gap_result.get('received_documents', 0)}/{gap_result.get('total_documents', 0)}")

        if gap_result.get('missing_document_list'):
            print(f"\nMissing Documents:")
            for doc in gap_result['missing_document_list']:
                print(f"  - {doc}")

        if validated_docs:
            print("\nValidated Documents:")
            for doc in validated_docs:
                print(f"  ✓ {doc['filename']} -> {doc['type']}")

        print("="*70)

        break


async def demo_vllm_from_sample():
    """Demo VLLM with sample documents in storage."""
    print("\n" + "="*70)
    print("VLLM VALIDATION DEMO (Sample Documents)")
    print("="*70)

    llm = LLMService()
    await init_db()

    storage_path = Path(settings.DOCUMENT_STORAGE_PATH)

    # Check for existing documents in storage
    print(f"\nChecking storage: {storage_path}")

    if storage_path.exists():
        pdf_files = list(storage_path.glob("**/*.pdf"))
        image_files = list(storage_path.glob("**/*.{png,jpg,jpeg}"))

        print(f"Found {len(pdf_files)} PDF files")
        print(f"Found {len(image_files)} image files")

        for pdf in pdf_files[:3]:
            print(f"\n--- Processing: {pdf.name} ---")

            # Try VLLM validation
            result = await llm.validate_document_vision(str(pdf))

            print(f"Document Type: {result.get('document_type', 'Unknown')}")
            print(f"Valid: {result.get('is_valid', False)}")
            print(f"Confidence: {result.get('confidence', 0):.1%}")

            if result.get('extracted_info'):
                print("Extracted Info:")
                for k, v in result['extracted_info'].items():
                    print(f"  - {k}: {v}")

            if result.get('error'):
                print(f"Error: {result['error']}")
                print("Trying OCR fallback...")

                ocr_result = await llm.ocr_extract_text(str(pdf))
                if ocr_result.get('success'):
                    print("OCR Text Preview:")
                    print(ocr_result['text'][:200] + "...")
    else:
        print("Storage path does not exist yet.")

    print("\n" + "="*70)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="VLLM Document Validation")
    parser.add_argument("--demo", action="store_true", help="Run demo with sample documents")
    parser.add_argument("--email", type=str, default="kr_bhupi@outlook.com", help="Candidate email")

    args = parser.parse_args()

    if args.demo:
        asyncio.run(demo_vllm_from_sample())
    else:
        asyncio.run(process_attachments_with_vllm(args.email))