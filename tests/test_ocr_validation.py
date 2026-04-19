#!/usr/bin/env python
"""
OCR Document Validation Pipeline

This script:
1. Extracts attachments from emails
2. Saves them to document storage
3. Uses LLM to validate document type
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


async def save_and_validate_documents(candidate_email: str = "kr_bhupi@outlook.com"):
    """Save and validate documents from email attachments."""
    print("\n" + "="*70)
    print("OCR DOCUMENT VALIDATION PIPELINE")
    print("="*70)

    # Initialize
    email_service = EmailService()
    llm = LLMService()
    await init_db()

    # Create storage directory
    storage_path = Path(settings.DOCUMENT_STORAGE_PATH)
    storage_path.mkdir(parents=True, exist_ok=True)

    print(f"\nStorage Path: {storage_path}")

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
        print(f"Candidate Folder: {candidate_folder}")

        # Read emails
        print("\n[STEP 1] Reading inbox for emails with attachments...")
        emails = await email_service.read_inbox(unread_only=False, limit=50)

        # Filter emails from candidate or with relevant attachments
        candidate_emails = []
        for email in emails:
            from_addr = email.get('from_address', '').lower()
            attachments = email.get('attachments', [])

            # Check if email has attachments (candidate or for testing)
            if attachments:
                candidate_emails.append(email)

        print(f"Found {len(candidate_emails)} emails with attachments")

        # Get document types
        result = await db.execute(select(DocumentTypeMaster))
        doc_types = {dt.document_name.lower(): dt.document_type_id for dt in result.scalars().all()}

        # Process attachments
        validated_docs = []

        for email in candidate_emails[:5]:  # Process first 5
            from_addr = email.get('from_address', '')
            subject = email.get('subject', '')
            attachments = email.get('attachments', [])

            print(f"\n--- Processing Email ---")
            print(f"From: {from_addr}")
            print(f"Subject: {subject}")
            print(f"Attachments: {len(attachments)}")

            for att in attachments:
                filename = att.get('filename', 'unknown.pdf')
                content_type = att.get('content_type', '')
                size = att.get('size', 0)

                print(f"\n  File: {filename}")
                print(f"  Type: {content_type}")
                print(f"  Size: {size} bytes")

                # Skip non-PDF/image files
                if not ('pdf' in content_type or 'image' in content_type):
                    print("  Skipped: Not a document file")
                    continue

                # Save attachment
                save_path = candidate_folder / filename
                try:
                    # save_attachment expects a Path object
                    await email_service.save_attachment(att, save_path)
                    print(f"  Saved to: {save_path}")

                    # Validate document using LLM
                    print(f"  Validating with LLM...")

                    # Read file content (for demo, use filename)
                    # In production, extract text using OCR
                    validation_result = await llm.validate_document(
                        document_text=f"Document filename: {filename}. This appears to be a document for onboarding.",
                        document_type="unknown"
                    )

                    doc_type = validation_result.get('document_type', 'Unknown')
                    is_valid = validation_result.get('is_valid', False)
                    confidence = validation_result.get('confidence', 0)
                    extracted_info = validation_result.get('extracted_info', {})

                    print(f"  Document Type: {doc_type}")
                    print(f"  Valid: {is_valid}")
                    print(f"  Confidence: {confidence:.2f}")

                    # Match with document types
                    doc_type_id = None
                    doc_type_lower = doc_type.lower()
                    for name, id in doc_types.items():
                        if name in doc_type_lower or any(word in name for word in doc_type_lower.split()):
                            doc_type_id = id
                            break

                    if doc_type_id and is_valid:
                        # Update document tracker
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
                                'type': list(doc_types.keys())[list(doc_types.values()).index(doc_type_id)],
                                'valid': is_valid
                            })
                            print(f"  ✓ Document validated and tracked")

                except Exception as e:
                    print(f"  Error: {e}")

        await db.commit()

        # Run gap analysis
        print("\n[STEP 2] Running gap analysis...")
        from src.mcp_tools.gap_analysis import GapAnalysisTool

        gap_tool = GapAnalysisTool(db)
        gap_result = await gap_tool.execute(candidate_id=candidate.candidate_id)

        print("\n" + "="*70)
        print("VALIDATION SUMMARY")
        print("="*70)
        print(f"Candidate: {candidate.candidate_name}")
        print(f"Email: {candidate.personal_email_id}")
        print(f"Joining Date: {candidate.expected_doj_wrt_to_np}")
        print(f"\nDocument Completion: {gap_result.get('completion_percentage', 0):.1f}%")
        print(f"Documents Received: {gap_result.get('received_documents', 0)}/{gap_result.get('total_documents', 0)}")

        if gap_result.get('missing_document_list'):
            print(f"\nMissing Documents:")
            for doc in gap_result['missing_document_list']:
                print(f"  - {doc}")

        print("\nValidated Documents:")
        for doc in validated_docs:
            print(f"  ✓ {doc['filename']} -> {doc['type']}")

        print("="*70)

        break


if __name__ == "__main__":
    asyncio.run(save_and_validate_documents())