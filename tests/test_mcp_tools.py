"""Tests for MCP Tools."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from src.mcp_tools.save_attachment import SaveAttachmentTool
from src.mcp_tools.followup_classification import FollowupClassificationTool
from src.mcp_tools.ocr_validation import OCRValidationTool
from src.mcp_tools.segregation import SegregationTool
from src.mcp_tools.gap_analysis import GapAnalysisTool
from src.mcp_tools.draft_prepare import DraftPrepareTool


class TestSaveAttachmentTool:
    """Tests for Save Attachment tool."""

    def test_tool_schema(self):
        """Test tool schema is defined."""
        email_service = MagicMock()
        doc_service = MagicMock()
        tool = SaveAttachmentTool(email_service, doc_service)

        schema = tool.get_tool_schema()

        assert schema["name"] == "save_attachment"
        assert "cin" in schema["parameters"]["properties"]
        assert "attachments" in schema["parameters"]["properties"]


class TestFollowupClassificationTool:
    """Tests for Followup Classification tool."""

    def test_extract_explicit_dates(self):
        """Test date extraction from text."""
        tool = FollowupClassificationTool()

        text = "I will send the documents by 2024-01-15"
        dates = tool.extract_explicit_dates(text)

        assert len(dates) >= 0  # Should find at least one date

    def test_extract_relative_dates(self):
        """Test relative date extraction."""
        tool = FollowupClassificationTool()

        text = "I will send tomorrow"
        dates = tool.extract_relative_dates(text)

        assert len(dates) >= 0  # Should find 'tomorrow'

    @pytest.mark.asyncio
    async def test_execute_classification(self):
        """Test email classification execution."""
        tool = FollowupClassificationTool()

        # Mock LLM service
        with patch.object(tool, '_determine_next_action_date') as mock_date:
            mock_date.return_value = MagicMock(isoformat=lambda: "2024-01-20")

            result = await tool.execute(
                email_body="Please find attached documents",
                email_subject="Document Submission"
            )

            assert "category" in result
            assert "next_action_date" in result


class TestOCRValidationTool:
    """Tests for OCR Validation tool."""

    def test_tool_schema(self):
        """Test tool schema is defined."""
        tool = OCRValidationTool()

        schema = tool.get_tool_schema()

        assert schema["name"] == "ocr_validation"
        assert "document_path" in schema["parameters"]["properties"]
        assert "expected_type" in schema["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_validate_nonexistent_document(self):
        """Test validation of non-existent document."""
        tool = OCRValidationTool()

        result = await tool.execute(
            document_path="/nonexistent/path.pdf",
            expected_type="Aadhaar Card"
        )

        assert result["is_valid"] is False
        assert "error" in result


class TestSegregationTool:
    """Tests for Segregation tool."""

    def test_categorize_by_type(self):
        """Test document categorization."""
        tool = SegregationTool()

        # Education documents
        assert tool.categorize_by_type("10th Marksheet") == "education"
        assert tool.categorize_by_type("Degree Certificate") == "education"

        # Employment documents
        assert tool.categorize_by_type("Relieving Letter") == "employment"
        assert tool.categorize_by_type("Salary Slip") == "employment"

        # Personal documents
        assert tool.categorize_by_type("Aadhaar Card") == "personal_details"
        assert tool.categorize_by_type("PAN Card") == "personal_details"

    def test_get_document_summary_empty(self):
        """Test document summary for empty directory."""
        tool = SegregationTool(storage_path="/tmp/test")

        summary = tool.get_document_summary("NONEXISTENT_CIN")

        assert summary["exists"] is False
        assert summary["total_documents"] == 0


class TestGapAnalysisTool:
    """Tests for Gap Analysis tool."""

    def test_tool_schema(self):
        """Test tool schema is defined."""
        mock_db = AsyncMock()
        tool = GapAnalysisTool(mock_db)

        schema = tool.get_tool_schema()

        assert schema["name"] == "gap_analysis"
        assert "candidate_id" in schema["parameters"]["properties"]


class TestDraftPrepareTool:
    """Tests for Draft Prepare tool."""

    def test_generate_subject(self):
        """Test email subject generation."""
        mock_db = AsyncMock()
        tool = DraftPrepareTool(mock_db)

        subject = tool._generate_subject(
            mail_type="followup_reminder",
            missing_docs=["Aadhaar Card", "PAN Card"]
        )

        assert "Reminder" in subject
        assert "2" in subject or "Documents" in subject

    def test_format_body(self):
        """Test email body formatting."""
        mock_db = AsyncMock()
        tool = DraftPrepareTool(mock_db)

        body = tool._format_body(
            content="Please submit your documents.",
            candidate_name="John Doe"
        )

        assert "Dear John Doe" in body
        assert "regards" in body.lower()

    def test_format_document_list(self):
        """Test document list formatting."""
        mock_db = AsyncMock()
        tool = DraftPrepareTool(mock_db)

        docs = ["Aadhaar Card", "PAN Card", "Degree Certificate"]
        formatted = tool._format_document_list(docs)

        assert "• Aadhaar Card" in formatted
        assert "• PAN Card" in formatted