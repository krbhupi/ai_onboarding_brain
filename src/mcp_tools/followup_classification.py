"""MCP Tool: Classify follow-up emails and extract dates."""
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import re

from config.logging import logger
from src.services.llm_service import LLMService
from src.constants.constants import HumanAction

llm_service = LLMService()


class FollowupClassificationTool:
    """Tool for classifying candidate replies and scheduling follow-ups."""

    def __init__(self):
        self.name = "followup_classification"
        self.description = "Classify candidate email replies and determine next follow-up date"

    async def execute(
        self,
        email_body: str,
        email_subject: str = "",
        candidate_name: str = ""
    ) -> Dict[str, Any]:
        """
        Classify an email reply from a candidate.

        Args:
            email_body: Content of the email
            email_subject: Subject line of the email
            candidate_name: Name of the candidate

        Returns:
            Classification result with category and next action date
        """
        try:
            # Use LLM to classify the email
            classification = await llm_service.classify_email_reply(email_body)

            # Extract or compute next follow-up date
            next_action_date = self._determine_next_action_date(classification)

            # Determine human action required
            human_action = self._determine_human_action(classification)

            result = {
                "category": classification.get("category", "other"),
                "documents_mentioned": classification.get("documents_list", []),
                "proposed_date": classification.get("proposed_date"),
                "urgency": classification.get("urgency", "medium"),
                "summary": classification.get("summary", ""),
                "next_action_date": next_action_date.isoformat(),
                "human_action_required": human_action["required"],
                "human_action_type": human_action["type"],
                "confidence": classification.get("confidence", 0.5)
            }

            logger.info(f"Classified email: {result['category']}, next action: {result['next_action_date']}")
            return result

        except Exception as e:
            logger.error(f"Classification error: {e}")
            return {
                "category": "other",
                "documents_mentioned": [],
                "proposed_date": None,
                "urgency": "medium",
                "summary": f"Error: {str(e)}",
                "next_action_date": (datetime.now() + timedelta(days=2)).isoformat(),
                "human_action_required": True,
                "human_action_type": HumanAction.ESCALATE,
                "confidence": 0.0,
                "error": str(e)
            }

    def _determine_next_action_date(
        self,
        classification: Dict[str, Any]
    ) -> datetime:
        """Determine the next follow-up date based on classification."""
        category = classification.get("category", "other")
        proposed_date = classification.get("proposed_date")
        urgency = classification.get("urgency", "medium")

        # If candidate proposed a date, use it
        if proposed_date:
            try:
                if isinstance(proposed_date, str):
                    return datetime.fromisoformat(proposed_date)
                return proposed_date
            except (ValueError, TypeError):
                pass

        # Otherwise, determine based on category and urgency
        if category == "documents_attached":
            # Documents received, process immediately
            return datetime.now()

        elif category == "request_extension":
            # Give them more time
            days = 7 if urgency == "high" else 14 if urgency == "medium" else 21
            return datetime.now() + timedelta(days=days)

        elif category == "acknowledgment":
            # Follow up in a few days
            days = 3 if urgency == "high" else 5 if urgency == "medium" else 7
            return datetime.now() + timedelta(days=days)

        else:  # "other" or "query"
            # Needs human review
            days = 1 if urgency == "high" else 2 if urgency == "medium" else 3
            return datetime.now() + timedelta(days=days)

    def _determine_human_action(
        self,
        classification: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Determine if human action is required and what type."""
        category = classification.get("category", "other")

        if category == "documents_attached":
            # Auto-process documents
            return {
                "required": True,  # Still need to validate documents
                "type": HumanAction.ACCEPT
            }

        elif category == "request_extension":
            # HR needs to approve extension
            return {
                "required": True,
                "type": HumanAction.ACCEPT  # Can be modified by HR
            }

        elif category == "query":
            # HR needs to respond to query
            return {
                "required": True,
                "type": HumanAction.ESCALATE
            }

        else:
            # Default to HR review
            return {
                "required": True,
                "type": HumanAction.ESCALATE
            }

    def extract_explicit_dates(self, text: str) -> List[datetime]:
        """Extract explicit date mentions from text."""
        dates = []

        # ISO format: YYYY-MM-DD
        iso_pattern = r'\d{4}-\d{2}-\d{2}'
        for match in re.finditer(iso_pattern, text):
            try:
                dates.append(datetime.strptime(match.group(), "%Y-%m-%d"))
            except ValueError:
                pass

        # DD/MM/YYYY or DD-MM-YYYY
        dmy_pattern = r'\d{1,2}[/-]\d{1,2}[/-]\d{4}'
        for match in re.finditer(dmy_pattern, text):
            try:
                date_str = match.group().replace("/", "-")
                dates.append(datetime.strptime(date_str, "%d-%m-%Y"))
            except ValueError:
                pass

        # Month names: "by January 15" or "on 15th January"
        month_pattern = r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?\b'
        for match in re.finditer(month_pattern, text, re.IGNORECASE):
            try:
                dates.append(datetime.strptime(match.group(), "%B %d"))
            except ValueError:
                pass

        return dates

    def extract_relative_dates(self, text: str) -> List[datetime]:
        """Extract relative date expressions from text."""
        dates = []
        text_lower = text.lower()
        today = datetime.now()

        # "tomorrow", "in 3 days", "next week", etc.
        if "tomorrow" in text_lower:
            dates.append(today + timedelta(days=1))

        if "day after tomorrow" in text_lower or "in 2 days" in text_lower:
            dates.append(today + timedelta(days=2))

        # "in X days"
        days_pattern = r'in (\d+) days?'
        for match in re.finditer(days_pattern, text_lower):
            days = int(match.group(1))
            dates.append(today + timedelta(days=days))

        if "next week" in text_lower:
            dates.append(today + timedelta(days=7))

        if "in a week" in text_lower:
            dates.append(today + timedelta(days=7))

        return dates

    def get_tool_schema(self) -> Dict[str, Any]:
        """Return the tool schema for MCP."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "email_body": {
                        "type": "string",
                        "description": "Content of the email to classify"
                    },
                    "email_subject": {
                        "type": "string",
                        "description": "Subject line of the email"
                    },
                    "candidate_name": {
                        "type": "string",
                        "description": "Name of the candidate"
                    }
                },
                "required": ["email_body"]
            }
        }