"""Exchange email service using exchangelib."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Dict, Any, Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

# Import exchangelib components
try:
    from exchangelib import Credentials, Account, Configuration, DELEGATE
    from exchangelib.protocol import BaseProtocol, NoVerifyHTTPAdapter
    from exchangelib.items import Message
    from exchangelib.folders import Folder
    from exchangelib.attachments import FileAttachment
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:
    raise ImportError("exchangelib is not installed. Please install it with: pip install exchangelib")

from config.settings import get_settings
from config.logging import logger

settings = get_settings()


class ExchangeEmailService:
    """Service for email operations via Microsoft Exchange using exchangelib."""

    def __init__(self):
        # Exchange configuration from settings or environment variables
        self.exchange_username = getattr(settings, 'EXCHANGE_USERNAME', None) or 'agentcai.solution@rebittest.com'
        self.exchange_password = getattr(settings, 'EXCHANGE_PASSWORD', None) or 'Welcome@2026'
        self.exchange_server = getattr(settings, 'EXCHANGE_SERVER', None) or 'mail.rebittest.com'
        self.primary_smtp_address = getattr(settings, 'EXCHANGE_PRIMARY_SMTP', None) or 'agentcai.solution@rebittest.com'

        # Disable SSL verification if needed
        self.disable_ssl_verification = getattr(settings, 'EXCHANGE_DISABLE_SSL_VERIFY', False)

        self._executor = ThreadPoolExecutor(max_workers=4)
        self.account = None

    def _connect_exchange(self) -> Account:
        """Connect to Exchange server."""
        try:
            # Set up credentials
            credentials = Credentials(
                username=self.exchange_username,
                password=self.exchange_password
            )

            # Set up configuration
            config = Configuration(
                server=self.exchange_server,
                credentials=credentials
            )

            # Disable SSL verification if requested
            if self.disable_ssl_verification:
                BaseProtocol.HTTP_ADAPTER_CLS = NoVerifyHTTPAdapter

            # Create account
            account = Account(
                primary_smtp_address=self.primary_smtp_address,
                config=config,
                autodiscover=False,
                access_type=DELEGATE
            )

            logger.info(f"Connected to Exchange server: {self.exchange_server}")
            return account

        except Exception as e:
            logger.error(f"Failed to connect to Exchange server: {e}")
            raise

    def _ensure_connection(self) -> Account:
        """Ensure we have a valid Exchange connection."""
        if self.account is None:
            self.account = self._connect_exchange()
        return self.account

    async def read_inbox(
        self,
        folder: str = "inbox",
        unread_only: bool = True,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Read emails from Exchange inbox asynchronously."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self._read_inbox_sync,
            folder,
            unread_only,
            limit
        )

    def _read_inbox_sync(
        self,
        folder: str,
        unread_only: bool,
        limit: int
    ) -> List[Dict[str, Any]]:
        """Synchronous inbox reading from Exchange."""
        emails = []
        try:
            account = self._ensure_connection()

            # Get the folder
            if folder.lower() == "inbox":
                exchange_folder = account.inbox
            else:
                # Try to find the folder by name
                exchange_folder = account.root / folder

            # Query emails
            query = exchange_folder.all()
            if unread_only:
                query = query.filter(is_read=False)

            # Limit results
            query = query.order_by('-datetime_received')[:limit]

            for item in query:
                email_data = self._parse_exchange_email(item)
                emails.append(email_data)

            logger.info(f"Read {len(emails)} emails from Exchange {folder}")
            return emails

        except Exception as e:
            logger.error(f"Error reading Exchange inbox: {e}")
            return emails

    def _parse_exchange_email(self, item: Message) -> Dict[str, Any]:
        """Parse Exchange email item into structured data."""
        email_data = {
            "message_id": getattr(item, 'message_id', ''),
            "from_address": getattr(item, 'sender', {}).get('email_address', '') if hasattr(item, 'sender') else '',
            "to_address": ', '.join([recipient.email_address for recipient in getattr(item, 'to_recipients', [])]),
            "subject": getattr(item, 'subject', ''),
            "date": getattr(item, 'datetime_received', '').isoformat() if getattr(item, 'datetime_received', None) else '',
            "body": getattr(item, 'body', ''),
            "attachments": self._get_exchange_attachments(item),
            "is_read": getattr(item, 'is_read', False),
            "raw": item  # Keep reference to original item for marking as read
        }

        return email_data

    def _get_exchange_attachments(self, item: Message) -> List[Dict[str, Any]]:
        """Extract attachment information from Exchange email."""
        attachments = []

        try:
            for attachment in getattr(item, 'attachments', []):
                if hasattr(attachment, 'name'):
                    attachments.append({
                        "filename": attachment.name,
                        "content_type": getattr(attachment, 'content_type', 'application/octet-stream'),
                        "size": getattr(attachment, 'size', 0),
                        "attachment_object": attachment  # Keep reference for saving
                    })
        except Exception as e:
            logger.error(f"Error extracting attachments: {e}")

        return attachments

    async def save_attachment(
        self,
        attachment: Dict[str, Any],
        save_path: Path
    ) -> Path:
        """Save Exchange email attachment to disk."""
        loop = asyncio.get_event_loop()

        def _save():
            save_path.parent.mkdir(parents=True, exist_ok=True)

            # Get the attachment object
            attachment_obj = attachment.get("attachment_object")
            if attachment_obj:
                # Save attachment content to file
                with open(save_path, "wb") as f:
                    f.write(attachment_obj.content)

            return save_path

        return await loop.run_in_executor(self._executor, _save)

    async def send_email(
        self,
        to_address: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
        attachments: Optional[List[Path]] = None
    ) -> bool:
        """Send email via Exchange."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self._send_email_sync,
            to_address,
            subject,
            body,
            html_body,
            attachments
        )

    def _send_email_sync(
        self,
        to_address: str,
        subject: str,
        body: str,
        html_body: Optional[str],
        attachments: Optional[List[Path]]
    ) -> bool:
        """Synchronous email sending via Exchange."""
        try:
            account = self._ensure_connection()

            # Create message
            message = Message(
                account=account,
                folder=account.sent,
                subject=subject,
                body=html_body if html_body else body,
                to_recipients=[to_address]
            )

            # Add attachments if provided
            if attachments:
                for file_path in attachments:
                    path = Path(file_path)
                    if path.exists():
                        with open(path, 'rb') as f:
                            content = f.read()
                        message.attachments.append(
                            FileAttachment(
                                name=path.name,
                                content=content
                            )
                        )

            # Send the message
            message.send_and_save()

            logger.info(f"Email sent via Exchange to {to_address}: {subject}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email via Exchange: {e}")
            return False

    async def mark_as_read(
        self,
        email_item: Any,
        folder: str = "inbox"
    ) -> bool:
        """Mark Exchange email as read."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self._mark_as_read_sync,
            email_item
        )

    def _mark_as_read_sync(self, email_item: Any) -> bool:
        """Synchronous mark as read for Exchange email."""
        try:
            if hasattr(email_item, 'raw') and email_item.raw:
                # Mark the original Exchange item as read
                exchange_item = email_item.raw
                exchange_item.is_read = True
                exchange_item.save()
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to mark Exchange email as read: {e}")
            return False

    def health_check(self) -> bool:
        """Check if Exchange service is available."""
        try:
            account = self._ensure_connection()
            # Try to access inbox to verify connection
            _ = list(account.inbox.all().order_by('-datetime_received')[:1])
            return True
        except Exception as e:
            logger.error(f"Exchange health check failed: {e}")
            return False