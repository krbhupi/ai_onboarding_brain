#!/usr/bin/env python
"""Simulate processing a candidate email reply."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from src.core.database import get_db, init_db
from src.models.database import CandidateInfo, DocumentTracker, DocumentTypeMaster
from src.constants.constants import StatusType
from src.mcp_tools.followup_classification import FollowupClassificationTool
from src.services.llm_service import LLMService


async def simulate_reply_processing():
    """Simulate processing a candidate reply."""
    print("\n" + "="*70)
    print("SIMULATING CANDIDATE REPLY PROCESSING")
    print("="*70)

    # Initialize database
    await init_db()

    async for db in get_db():
        # Find the candidate
        result = await db.execute(
            select(CandidateInfo).where(CandidateInfo.personal_email_id == "kr_bhupi@outlook.com")
        )
        candidate = result.scalar_one_or_none()

        if not candidate:
            print("No candidate found with email kr_bhupi@outlook.com")
            return

        print(f"\nCandidate: {candidate.candidate_name} (ID: {candidate.candidate_id})")
        print(f"Email: {candidate.personal_email_id}")

        # Simulate incoming email
        simulated_email = """
Hi Team,

Thank you for the follow-up. I have attached the following documents:

1. Bank Passbook - for salary account verification
2. 10th Marksheet
3. 12th Marksheet

I will send the remaining documents (Relieving Letter, Experience Certificate,
Salary Slips, and Form 16) by end of this week.

Please let me know if you need anything else.

Best regards,
KR
"""

        print("\n--- Simulated Email Body ---")
        print(simulated_email)

        # Step 1: Classify the email using LLM
        print("\n[STEP 1] Classifying email using LLM...")
        llm = LLMService()

        classification = await llm.classify_email(
            email_body=simulated_email,
            email_subject="Re: HR Onboarding - Document Submission"
        )

        print(f"\nClassification Result:")
        print(f"  Category: {classification.get('category', 'N/A')}")
        print(f"  Confidence: {classification.get('confidence', 0):.2f}")
        print(f"  Action Required: {classification.get('action_required', 'N/A')}")
        print(f"  Next Action Date: {classification.get('next_action_date', 'N/A')}")
        print(f"  Documents Mentioned: {classification.get('documents_mentioned', [])}")

        # Step 2: Update document status
        print("\n[STEP 2] Updating document status...")

        documents_received = ["Bank Passbook/Cancelled Cheque", "10th Marksheet", "12th Marksheet"]

        result = await db.execute(select(DocumentTypeMaster))
        doc_types = {dt.document_name: dt.document_type_id for dt in result.scalars().all()}

        updated_count = 0
        for doc_name in documents_received:
            doc_type_id = doc_types.get(doc_name)
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
                    updated_count += 1

        await db.commit()
        print(f"  Updated {updated_count} documents as received")

        # Step 3: Run gap analysis
        print("\n[STEP 3] Running gap analysis...")
        from src.mcp_tools.gap_analysis import GapAnalysisTool

        gap_tool = GapAnalysisTool(db)
        gap_result = await gap_tool.execute(candidate_id=candidate.candidate_id)

        print(f"\n--- Updated Document Status ---")
        print(f"Total Documents: {gap_result.get('total_documents', 'N/A')}")
        print(f"Received: {gap_result.get('received_documents', 'N/A')}")
        print(f"Missing: {gap_result.get('missing_documents', 'N/A')}")
        print(f"Completion: {gap_result.get('completion_percentage', 0):.1f}%")

        if gap_result.get('missing_document_list'):
            print(f"\nStill Missing:")
            for doc in gap_result['missing_document_list']:
                print(f"  - {doc}")

        # Step 4: Determine next action
        print("\n[STEP 4] Determining next action...")

        completion = gap_result.get('completion_percentage', 0)

        if completion == 100:
            print("  ✓ All documents received! Ready for verification.")
        elif completion >= 50:
            print("  → Send reminder for remaining documents")
        else:
            print("  → Escalate - Low document completion")

        print("\n" + "="*70)
        print("REPLY PROCESSING COMPLETE")
        print("="*70)
        print(f"Candidate: {candidate.candidate_name}")
        print(f"Documents Updated: {updated_count}")
        print(f"Current Completion: {gap_result.get('completion_percentage', 0):.1f}%")
        print(f"Status: {'In Progress' if completion < 100 else 'Complete'}")
        print("="*70)

        break


if __name__ == "__main__":
    asyncio.run(simulate_reply_processing())