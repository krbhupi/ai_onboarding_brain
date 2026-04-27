"""Email service for IMAP and SMTP operations."""
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
import imaplib
import smtplib
import asyncio
from concurrent.futures import ThreadPoolExecutor

from config.settings import get_settings
from config.logging import logger
from src.services.exchange_email_service import ExchangeEmailService

settings = get_settings()


class EmailService:
    """Service for email operations via IMAP/SMTP."""

    def __init__(self):
        self.imap_host = settings.IMAP_HOST
        self.imap_port = settings.IMAP_PORT
        self.imap_username = settings.IMAP_USERNAME
        self.imap_password = settings.IMAP_PASSWORD

        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_username = settings.SMTP_USERNAME
        self.smtp_password = settings.SMTP_PASSWORD
        self.smtp_from = settings.SMTP_FROM_EMAIL

        # Exchange email service
        self.use_exchange = getattr(settings, 'USE_EXCHANGE', False)
        if self.use_exchange:
            self.exchange_service = ExchangeEmailService()

        self._executor = ThreadPoolExecutor(max_workers=4)

    def _connect_imap(self) -> imaplib.IMAP4_SSL:
        """Connect to IMAP server."""
        imap = imaplib.IMAP4_SSL(self.imap_host, self.imap_port)
        imap.login(self.imap_username, self.imap_password)
        return imap

    def _disconnect_imap(self, imap: imaplib.IMAP4_SSL) -> None:
        """Disconnect from IMAP server."""
        try:
            imap.close()
            imap.logout()
        except Exception:
            pass

    async def read_inbox(
        self,
        folder: str = "INBOX",
        unread_only: bool = True,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Read emails from inbox asynchronously."""
        # Use Exchange if enabled
        if self.use_exchange:
            return await self.exchange_service.read_inbox(folder, unread_only, limit)

        # Default to IMAP/SMTP
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
        """Synchronous inbox reading."""
        emails = []
        imap = None

        try:
            imap = self._connect_imap()
            imap.select(folder)

            # Search for emails
            search_criteria = "UNSEEN" if unread_only else "ALL"
            status, message_ids = imap.search(None, search_criteria)

            if status != "OK":
                logger.error(f"Failed to search emails: {status}")
                return emails

            ids = message_ids[0].split()
            ids = ids[:limit]  # Limit results

            for msg_id in ids:
                status, msg_data = imap.fetch(msg_id, "(RFC822)")
                if status != "OK":
                    continue

                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        raw_email = response_part[1]
                        email_data = self._parse_email(raw_email)
                        emails.append(email_data)

            logger.info(f"Read {len(emails)} emails from {folder}")
            return emails

        except Exception as e:
            logger.error(f"Error reading inbox: {e}")
            return emails
        finally:
            if imap:
                self._disconnect_imap(imap)

    def _parse_email(self, raw_email: bytes) -> Dict[str, Any]:
        """Parse raw email into structured data."""
        msg = email.message_from_bytes(raw_email)

        email_data = {
            "message_id": msg.get("Message-ID", ""),
            "from_address": msg.get("From", ""),
            "to_address": msg.get("To", ""),
            "subject": msg.get("Subject", ""),
            "date": msg.get("Date", ""),
            "body": self._get_email_body(msg),
            "attachments": self._get_attachments(msg),
            "raw": raw_email
        }

        return email_data

    def _get_email_body(self, msg: email.message.Message) -> str:
        """Extract email body text."""
        body = ""

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))

                if content_type == "text/plain" and "attachment" not in content_disposition:
                    try:
                        body = part.get_payload(decode=True).decode()
                        break
                    except Exception:
                        continue
        else:
            try:
                body = msg.get_payload(decode=True).decode()
            except Exception:
                pass

        return body

    def _get_attachments(self, msg: email.message.Message) -> List[Dict[str, Any]]:
        """Extract attachment information from email."""
        attachments = []

        for part in msg.walk():
            content_disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in content_disposition:
                filename = part.get_filename()
                if filename:
                    attachments.append({
                        "filename": filename,
                        "content_type": part.get_content_type(),
                        "size": len(part.get_payload(decode=True) or b""),
                        "part": part
                    })

        return attachments

    async def save_attachment(
        self,
        attachment: Dict[str, Any],
        save_path: Path
    ) -> Path:
        """Save email attachment to disk."""
        # Use Exchange if enabled
        if self.use_exchange:
            return await self.exchange_service.save_attachment(attachment, save_path)

        # Default to IMAP/SMTP
        loop = asyncio.get_event_loop()

        def _save():
            save_path.parent.mkdir(parents=True, exist_ok=True)
            payload = attachment["part"].get_payload(decode=True)
            with open(save_path, "wb") as f:
                f.write(payload)
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
        """Send email via SMTP."""
        # Use Exchange if enabled
        if self.use_exchange:
            return await self.exchange_service.send_email(to_address, subject, body, html_body, attachments)

        # Default to IMAP/SMTP
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
        """Synchronous email sending."""
        try:
            msg = MIMEMultipart("alternative" if html_body else "mixed")
            msg["From"] = self.smtp_from
            msg["To"] = to_address
            msg["Subject"] = subject

            # Attach body
            msg.attach(MIMEText(body, "plain"))
            if html_body:
                msg.attach(MIMEText(html_body, "html"))

            # Attach files
            if attachments:
                for file_path in attachments:
                    path = Path(file_path)
                    if not path.exists():
                        continue

                    with open(path, "rb") as f:
                        part = MIMEBase("application", "octet-stream")
                        part.set_payload(f.read())
                        encoders.encode_base64(part)
                        part.add_header(
                            "Content-Disposition",
                            f"attachment; filename= {path.name}"
                        )
                        msg.attach(part)

            # Connect and send
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if settings.SMTP_USE_TLS:
                    server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.sendmail(self.smtp_from, [to_address], msg.as_string())

            logger.info(f"Email sent to {to_address}: {subject}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False

    async def mark_as_read(
        self,
        message_id: str,
        folder: str = "INBOX"
    ) -> bool:
        """Mark email as read."""
        # Use Exchange if enabled
        if self.use_exchange:
            # For Exchange, we need the email item, not just the message_id
            # This is a limitation of the current interface
            return False

        # Default to IMAP/SMTP
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self._mark_as_read_sync,
            message_id,
            folder
        )

    async def mark_exchange_email_as_read(
        self,
        email_item: Any
    ) -> bool:
        """Mark Exchange email as read using the email item."""
        if self.use_exchange:
            return await self.exchange_service.mark_as_read(email_item)
        return False

    def _mark_as_read_sync(self, message_id: str, folder: str) -> bool:
        """Synchronous mark as read."""
        imap = None
        try:
            imap = self._connect_imap()
            imap.select(folder)
            imap.store(message_id, "+FLAGS", "\\Seen")
            return True
        except Exception as e:
            logger.error(f"Failed to mark email as read: {e}")
            return False
        finally:
            if imap:
                self._disconnect_imap(imap)