"""Constants for status, job types, mail types, etc."""


class StatusType:
    """Status values for job and document tracking."""
    PENDING = 1
    IN_PROGRESS = 2
    COMPLETE = 3
    FAILED = 4
    ON_HOLD = 5

    NAMES = {
        1: "pending",
        2: "in_progress",
        3: "complete",
        4: "failed",
        5: "on_hold"
    }


class JobType:
    """Job type identifiers."""
    DOCUMENTS_REQUIRED = 1
    MAIL_SEND = 2
    FOLLOWUP_MAIL = 3
    READ_INBOX = 4
    SAVE_ATTACHMENT = 5
    OCR_VALIDATION = 6
    SEGREGATION = 7
    GAP_ANALYSIS = 8

    NAMES = {
        1: "documents_required",
        2: "mail_send",
        3: "followup_mail",
        4: "read_inbox",
        5: "save_attachment",
        6: "ocr_validation",
        7: "segregation",
        8: "gap_analysis"
    }


class MailType:
    """Mail type identifiers for templates."""
    INITIAL_REQUEST = 1
    FOLLOWUP_REMINDER = 2
    DOCUMENT_RECEIVED = 3
    GAP_NOTIFICATION = 4

    NAMES = {
        1: "initial_request",
        2: "followup_reminder",
        3: "document_received",
        4: "gap_notification"
    }


class CandidateType:
    """Candidate type identifiers."""
    FRESHER = 1
    EXPERIENCE = 2
    DEV_PARTNER = 3

    NAMES = {
        1: "fresher",
        2: "experience",
        3: "dev_partner"
    }


class DocumentCategory:
    """Document categories for segregation."""
    EDUCATION = "education"
    EMPLOYMENT = "employment"
    PERSONAL_DETAILS = "personal_details"
    UNMATCHED = "unmatched"


class HumanAction:
    """Human action types for approval workflow."""
    ACCEPT = "accept"
    REJECT = "reject"
    MODIFY = "modify"
    ESCALATE = "escalate"


# Document types mapping for each candidate type
DOCUMENT_TYPE_MAPPING = {
    CandidateType.FRESHER: [
        "Aadhaar Card",
        "PAN Card",
        "10th Marksheet",
        "12th Marksheet",
        "Degree Certificate",
        "Passport Photo",
        "Bank Passbook/Cancelled Cheque"
    ],
    CandidateType.EXPERIENCE: [
        "Aadhaar Card",
        "PAN Card",
        "10th Marksheet",
        "12th Marksheet",
        "Degree Certificate",
        "Passport Photo",
        "Bank Passbook/Cancelled Cheque",
        "Relieving Letter",
        "Experience Certificate",
        "Salary Slip (Last 3 months)",
        "Form 16"
    ],
    CandidateType.DEV_PARTNER: [
        "Aadhaar Card",
        "PAN Card",
        "Passport Photo",
        "Bank Passbook/Cancelled Cheque",
        "Partner Agreement"
    ]
}