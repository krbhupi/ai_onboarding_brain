#!/usr/bin/env python
"""Test SMTP email service."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.email_service import EmailService


async def test_smtp():
    """Test SMTP email sending."""
    print("=" * 60)
    print("SMTP EMAIL SERVICE TEST")
    print("=" * 60)

    email_service = EmailService()

    print(f"\nSMTP Configuration:")
    print(f"  Host: {email_service.smtp_host}")
    print(f"  Port: {email_service.smtp_port}")
    print(f"  Username: {email_service.smtp_username}")
    print(f"  From: {email_service.smtp_from}")

    print("\n" + "-" * 60)
    print("Testing email send...")
    print("-" * 60)

    # Send test email
    result = await email_service.send_email(
        to_address="kr_bhupi@outlook.com",  # Send to self for testing
        subject="HR Automation - SMTP Test",
        body="This is a test email from HR Automation system using SMTP configuration.\n\nIf you received this, SMTP is working correctly!"
    )

    if result:
        print("\n✓ Email sent successfully!")
    else:
        print("\n✗ Failed to send email")
        print("\nNote: Microsoft has disabled basic authentication for Outlook.com.")
        print("You may need to:")
        print("1. Use OAuth2 (set USE_OAUTH2=true and configure Azure app)")
        print("2. Or use an app password if your account supports it")

    return result


if __name__ == "__main__":
    asyncio.run(test_smtp())