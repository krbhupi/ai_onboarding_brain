#!/usr/bin/env python
"""Quick OCR validation demo without IMAP delays."""
import asyncio
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from src.core.database import get_db, init_db
from src.models.database import CandidateInfo, DocumentTracker, DocumentTypeMaster
from src.constants.constants import StatusType
from src.services.llm_service import LLMService
from src.mcp_tools.ocr_validation import OCRValidationTool


async def demo_ocr_validation():
    """Demonstrate OCR validation for documents."""
    print("\n" + "="*70)
    print("OCR DOCUMENT VALIDATION DEMO")
    print("="*70)

    await init_db()
    llm = LLMService()

    async for db in get_db():
        # Find candidate
        result = await db.execute(
            select(CandidateInfo).where(CandidateInfo.personal_email_id == "kr_bhupi@outlook.com")
        )
        candidate = result.scalar_one_or_none()

        if not candidate:
            print("Candidate not found")
            return

        print(f"\nCandidate: {candidate.candidate_name}")
        print(f"Email: {candidate.personal_email_id}")
        print(f"Joining Date: {candidate.expected_doj_wrt_to_np}")

        # Sample document texts for OCR validation
        sample_documents = [
            {
                "filename": "Aadhaar_Card.pdf",
                "text": """
                AADHAAR CARD
                Unique Identification Authority of India

                Name: KR
                Date of Birth: 15/05/1990
                Gender: Male
                Aadhaar Number: XXXX XXXX 1234
                Address: Mumbai, Maharashtra
                """,
                "expected_type": "Aadhaar Card"
            },
            {
                "filename": "PAN_Card.pdf",
                "text": """
                PERMANENT ACCOUNT NUMBER CARD

                Name: KR
                Father's Name: Suresh Kumar
                Date of Birth: 15/05/1990
                PAN: ABCDE1234F
                """,
                "expected_type": "PAN Card"
            },
            {
                "filename": "Degree_Certificate.pdf",
                "text": """
                CERTIFICATE OF DEGREE
                Bachelor of Engineering (Computer Science)

                This is to certify that KR
                has successfully completed the course of study

                University: Mumbai University
                Year: 2012
                Grade: First Class with Distinction
                """,
                "expected_type": "Degree Certificate"
            },
            {
                "filename": "Bank_Passbook.pdf",
                "text": """
                STATE BANK OF INDIA
                SAVINGS BANK ACCOUNT

                Account Holder: KR
                Account Number: XXXX1234
                IFSC Code: SBIN0001234
                Branch: Mumbai Main Branch

                This passbook is valid for salary credit
                """,
                "expected_type": "Bank Passbook/Cancelled Cheque"
            }
        ]

        print("\n" + "-"*70)
        print("VALIDATING DOCUMENTS USING LLM")
        print("-"*70)

        # Get document types
        result = await db.execute(select(DocumentTypeMaster))
        doc_types = {dt.document_name.lower(): dt.document_type_id for dt in result.scalars().all()}

        validated_count = 0

        for doc in sample_documents:
            print(f"\n📄 Document: {doc['filename']}")
            print(f"   Expected Type: {doc['expected_type']}")

            # Validate using LLM
            validation_result = await llm.validate_document(
                document_text=doc['text'],
                expected_type=doc['expected_type']
            )

            is_valid = validation_result.get('is_valid', False)
            confidence = validation_result.get('confidence', 0)
            doc_type = validation_result.get('document_type', 'Unknown')
            extracted_info = validation_result.get('extracted_info', {})

            print(f"   Validated: {'✓ YES' if is_valid else '✗ NO'}")
            print(f"   Type Detected: {doc_type}")
            print(f"   Confidence: {confidence:.1%}")

            if extracted_info:
                print(f"   Extracted Info:")
                for key, value in extracted_info.items():
                    print(f"     - {key}: {value}")

            # Update database if valid
            if is_valid:
                doc_type_lower = doc_type.lower()
                doc_type_id = None
                for name, id in doc_types.items():
                    if name in doc_type_lower or doc_type_lower in name:
                        doc_type_id = id
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
                        validated_count += 1

        await db.commit()

        # Run gap analysis
        print("\n" + "-"*70)
        print("FINAL DOCUMENT STATUS")
        print("-"*70)

        from src.mcp_tools.gap_analysis import GapAnalysisTool
        gap_tool = GapAnalysisTool(db)
        gap_result = await gap_tool.execute(candidate_id=candidate.candidate_id)

        print(f"\nCandidate: {candidate.candidate_name}")
        print(f"Email: {candidate.personal_email_id}")
        print(f"Joining Date: {candidate.expected_doj_wrt_to_np}")
        print(f"\nDocument Completion: {gap_result.get('completion_percentage', 0):.1f}%")
        print(f"Documents Received: {gap_result.get('received_documents', 0)}/{gap_result.get('total_documents', 0)}")

        if gap_result.get('missing_document_list'):
            print(f"\nPending Documents:")
            for doc in gap_result['missing_document_list']:
                print(f"  - {doc}")

        print("\n" + "="*70)
        print(f"✓ OCR VALIDATION COMPLETE - {validated_count} documents validated")
        print("="*70)

        break


if __name__ == "__main__":
    asyncio.run(demo_ocr_validation())