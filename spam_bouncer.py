#!/usr/bin/env python3
"""
Spam Bouncer - Auto-reply to spam emails with fake bounce messages
Monitors iCloud Mail for spam and sends convincing bounce notifications
"""

import imaplib
import smtplib
import email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
import time
import logging
import json
import os
from datetime import datetime
from pathlib import Path

# Setup logging
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / f'spam_bouncer_{datetime.now().strftime("%Y%m%d")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class SpamBouncer:
    """Monitors mailbox for spam and sends fake bounce messages"""

    def __init__(self, config_file='config.json'):
        self.config = self._load_config(config_file)
        self.accounts = self._normalize_accounts(self.config)
        self.processed_file = LOG_DIR / 'processed_emails.txt'
        self.processed_ids = self._load_processed()

    def _load_config(self, config_file):
        """Load configuration from JSON file"""
        config_path = Path(__file__).parent / config_file
        if not config_path.exists():
            raise FileNotFoundError(
                f"Config file not found: {config_path}\n"
                "Please create config.json with your email credentials."
            )
        with open(config_path) as f:
            return json.load(f)

    def _normalize_accounts(self, config):
        """Normalize config to always be a list of accounts (backward compatibility)"""
        # New format: {"accounts": [...]}
        if 'accounts' in config:
            return [acc for acc in config['accounts'] if acc.get('enabled', True)]

        # Old format: {"email": "...", "password": "..."}
        if 'email' in config:
            logger.warning("Using legacy config format. Please update to new multi-account format.")
            return [config]

        raise ValueError("Invalid config format. Must have 'accounts' array or legacy 'email' field.")

    def _load_processed(self):
        """Load list of already processed email IDs"""
        if self.processed_file.exists():
            with open(self.processed_file) as f:
                return set(line.strip() for line in f)
        return set()

    def _mark_processed(self, email_id):
        """Mark an email as processed"""
        with open(self.processed_file, 'a') as f:
            f.write(f"{email_id}\n")
        self.processed_ids.add(email_id)

    def _is_spam(self, msg):
        """
        Comprehensive spam detection based on headers and patterns.
        Returns True if email appears to be spam.
        """
        import re

        # 1. Check existing spam headers first
        if (msg.get('X-Clx-Spam', '').lower() == 'true' or
            msg.get('X-Proofpoint-Spam-Details', '') != '' or
            msg.get('X-Spam-Flag', '').lower() == 'yes' or
            msg.get('X-Gmail-Labels', '').lower().find('spam') != -1):
            return True

        # 2. Get sender information
        from_header = msg.get('From', '')
        from_email = email.utils.parseaddr(from_header)[1].lower()
        from_domain = from_email.split('@')[-1] if '@' in from_email else ''

        # 3. Suspicious sender patterns
        # Random string usernames (e.g., skunklunarlit450@icloud.com)
        username = from_email.split('@')[0] if '@' in from_email else ''

        # Pattern: random words + numbers (common spam pattern)
        random_pattern = re.search(r'^[a-z]+[a-z0-9]{6,}[0-9]+$', username)
        if random_pattern:
            logger.debug(f"Spam indicator: Random username pattern in {from_email}")
            return True

        # 4. Suspicious iCloud senders
        # Real users rarely have very long random usernames
        if from_domain == 'icloud.com' and len(username) > 15:
            if re.search(r'[0-9]{3,}', username):  # Contains 3+ consecutive numbers
                logger.debug(f"Spam indicator: Suspicious iCloud username {from_email}")
                return True

        # 5. Check Subject for spam patterns
        subject = msg.get('Subject', '')
        if subject.lower() == '(no subject)' or subject.strip() == '':
            # No subject with suspicious sender is often spam
            if random_pattern:
                logger.debug(f"Spam indicator: No subject + random sender")
                return True

        # 6. Check body/preview for common spam patterns
        body_preview = msg.get_payload()
        if isinstance(body_preview, str):
            body_lower = body_preview.lower()
            spam_keywords = [
                'adjust', 'chrysalides', 'capillament', 'demetrius',
                'click here', 'verify your account', 'suspended',
                'urgent action required', 'confirm your identity'
            ]
            keyword_matches = sum(1 for keyword in spam_keywords if keyword in body_lower)
            if keyword_matches >= 2:
                logger.debug(f"Spam indicator: {keyword_matches} spam keywords found")
                return True

        # 7. Missing authentication headers (SPF, DKIM, DMARC failures)
        auth_results = msg.get('Authentication-Results', '').lower()
        if 'spf=fail' in auth_results or 'dkim=fail' in auth_results:
            logger.debug(f"Spam indicator: Authentication failure")
            return True

        # 8. Suspicious To/Reply-To mismatches
        to_header = msg.get('To', '').lower()
        reply_to = msg.get('Reply-To', '').lower()
        if reply_to and reply_to != from_email and from_domain != reply_to.split('@')[-1]:
            logger.debug(f"Spam indicator: Reply-To mismatch")
            return True

        return False

    def _create_bounce_message(self, original_from, original_subject, recipient):
        """Create a convincing fake bounce/NDR message"""

        # Random selection of realistic bounce reasons
        bounce_templates = [
            {
                'code': '550 5.1.1',
                'title': 'Recipient address rejected: User unknown in local recipient table',
                'reason': 'The email account that you tried to reach does not exist.'
            },
            {
                'code': '550 5.7.1',
                'title': 'Recipient address rejected: Access denied',
                'reason': 'The recipient mailbox is not accepting messages from this sender.'
            },
            {
                'code': '553 5.3.0',
                'title': 'Mailbox unavailable',
                'reason': 'The mailbox you are trying to reach is currently unavailable or has been disabled.'
            },
            {
                'code': '551 5.1.1',
                'title': 'User not local',
                'reason': 'The recipient address is not hosted on this server.'
            }
        ]

        import random
        bounce = random.choice(bounce_templates)

        # Create the bounce message
        msg = MIMEMultipart('mixed')
        # Use actual email address but with "Mail Delivery System" display name
        # (iCloud/Gmail won't let us impersonate MAILER-DAEMON)
        msg['From'] = f'Mail Delivery System <{recipient}>'
        msg['To'] = original_from
        msg['Subject'] = f'Undelivered Mail Returned to Sender'
        msg['Date'] = formatdate(localtime=True)
        msg['Message-ID'] = make_msgid(domain=self._get_domain(recipient))
        msg['Auto-Submitted'] = 'auto-replied'
        msg['X-Auto-Response-Suppress'] = 'All'

        # Create the human-readable part
        text_part = f"""This is the mail system at host {self._get_domain(recipient)}.

I'm sorry to have to inform you that your message could not
be delivered to one or more recipients. It's attached below.

For further assistance, please contact your email administrator.

If you do so, please include this problem report. You can
delete your own text from the attached returned message.

                   The mail system

<{recipient}>: host mail.{self._get_domain(recipient)} said: {bounce['code']} {bounce['title']}
    (in reply to RCPT TO command)

--{msg.get_boundary()}
Content-Description: Notification
Content-Type: text/plain; charset=UTF-8

Final-Recipient: rfc822; {recipient}
Original-Recipient: rfc822;{recipient}
Action: failed
Status: 5.0.0
Diagnostic-Code: smtp; {bounce['code']} {bounce['title']}
"""

        msg.attach(MIMEText(text_part, 'plain'))

        return msg

    def _get_domain(self, email_address):
        """Extract domain from email address"""
        return email_address.split('@')[-1] if '@' in email_address else 'icloud.com'

    def connect_imap(self, account):
        """Connect to IMAP server for a specific account"""
        try:
            logger.info(f"Connecting to IMAP server for {account['email']}...")
            mail = imaplib.IMAP4_SSL(account['imap_server'], account.get('imap_port', 993))
            mail.login(account['email'], account['password'])
            logger.info(f"Successfully connected to IMAP for {account['email']}")
            return mail
        except Exception as e:
            logger.error(f"IMAP connection failed for {account['email']}: {e}")
            raise

    def send_bounce(self, account, to_address, original_subject, recipient):
        """Send fake bounce message from a specific account"""
        try:
            logger.info(f"Sending bounce to: {to_address} from {account['email']}")

            # Create bounce message
            bounce_msg = self._create_bounce_message(to_address, original_subject, recipient)

            # Connect to SMTP and send
            with smtplib.SMTP(account['smtp_server'], account.get('smtp_port', 587)) as server:
                server.starttls()
                server.login(account['email'], account['password'])
                server.send_message(bounce_msg)

            logger.info(f"Bounce sent successfully to {to_address}")
            return True

        except Exception as e:
            logger.error(f"Failed to send bounce to {to_address}: {e}")
            return False

    def process_account_spam(self, account):
        """Check for spam emails and send bounce messages for a specific account"""
        mail = None
        try:
            mail = self.connect_imap(account)
            mail.select('INBOX')

            # Search for unread spam messages
            # Looking for messages with X-Clx-Spam: true or spam headers
            status, messages = mail.search(None, 'UNSEEN')

            if status != 'OK':
                logger.error(f"Failed to search for messages in {account['email']}")
                return

            if not messages or not messages[0]:
                logger.info(f"No unread messages found in {account['email']}")
                return

            email_ids = messages[0].split()
            logger.info(f"Found {len(email_ids)} unread messages to check in {account['email']}")

            for email_id in email_ids:
                try:
                    # Fetch the email using BODY[] (more reliable than RFC822)
                    status, msg_data = mail.fetch(email_id, '(BODY[])')
                    if status != 'OK':
                        logger.warning(f"Failed to fetch email {email_id}")
                        continue

                    # Validate msg_data structure
                    if not msg_data or len(msg_data) == 0:
                        logger.warning(f"Empty msg_data for email {email_id}")
                        continue

                    # Parse email - handle different response formats
                    # msg_data can be: [(b'1 (RFC822 {size}', email_bytes), b')')] or similar
                    raw_email = None

                    # Try to find the email data in msg_data
                    for item in msg_data:
                        if isinstance(item, tuple) and len(item) >= 2:
                            if isinstance(item[1], bytes) and len(item[1]) > 100:  # Actual email should be bigger
                                raw_email = item[1]
                                break

                    # If not found in tuples, check direct items
                    if raw_email is None and len(msg_data) > 0:
                        if isinstance(msg_data[0], tuple) and len(msg_data[0]) > 1:
                            potential = msg_data[0][1]
                            if isinstance(potential, bytes) and len(potential) > 100:
                                raw_email = potential

                    # Ensure raw_email is valid bytes
                    if raw_email is None:
                        logger.warning(f"Could not extract email data for {email_id}, marking as seen to prevent loop")
                        # Mark as seen so it doesn't keep showing up
                        try:
                            mail.store(email_id, '+FLAGS', '\\Seen')
                        except:
                            pass
                        continue
                    elif isinstance(raw_email, int):
                        logger.error(f"Got integer instead of bytes for email {email_id}, marking as seen")
                        try:
                            mail.store(email_id, '+FLAGS', '\\Seen')
                        except:
                            pass
                        continue
                    elif not isinstance(raw_email, bytes):
                        logger.error(f"Unexpected raw_email type for {email_id}: {type(raw_email)}, marking as seen")
                        try:
                            mail.store(email_id, '+FLAGS', '\\Seen')
                        except:
                            pass
                        continue
                    elif len(raw_email) < 50:
                        logger.warning(f"Email {email_id} too small ({len(raw_email)} bytes), marking as seen")
                        try:
                            mail.store(email_id, '+FLAGS', '\\Seen')
                        except:
                            pass
                        continue

                    msg = email.message_from_bytes(raw_email)

                    # Check if it's spam using comprehensive detection
                    if not self._is_spam(msg):
                        logger.debug(f"Email {email_id} is not spam, skipping")
                        continue

                    # Get sender info
                    from_header = msg.get('From', '')
                    subject = msg.get('Subject', '(No Subject)')

                    # Generate fallback message ID from email_id
                    if isinstance(email_id, bytes):
                        fallback_id = email_id.decode()
                    elif isinstance(email_id, int):
                        fallback_id = str(email_id)
                    else:
                        fallback_id = str(email_id)

                    message_id = msg.get('Message-ID', fallback_id)

                    # Skip if already processed
                    if message_id in self.processed_ids:
                        logger.debug(f"Already processed {message_id}")
                        continue

                    # Extract sender email
                    from_email = email.utils.parseaddr(from_header)[1]

                    if not from_email:
                        logger.warning(f"Could not extract sender email from: {from_header}")
                        continue

                    logger.info(f"Processing spam from: {from_email} - Subject: {subject}")

                    # Send bounce
                    if self.send_bounce(account, from_email, subject, account['email']):
                        self._mark_processed(message_id)
                        logger.info(f"Successfully bounced spam from {from_email}")

                        # Move to Junk folder
                        try:
                            # Try common spam folder names (Gmail uses [Gmail]/Spam)
                            spam_folders = ['Junk', 'Spam', '[Gmail]/Spam', 'INBOX.Junk', 'INBOX.Spam']
                            moved = False

                            for folder_name in spam_folders:
                                try:
                                    # Copy to spam folder
                                    result = mail.copy(email_id, folder_name)
                                    if result[0] == 'OK':
                                        # Mark original for deletion
                                        mail.store(email_id, '+FLAGS', '\\Deleted')
                                        logger.info(f"Moved email to {folder_name} folder")
                                        moved = True
                                        break
                                except:
                                    continue

                            if not moved:
                                logger.warning(f"Could not move email to spam folder, tried: {spam_folders}")
                        except Exception as e:
                            logger.error(f"Error moving email to spam folder: {e}")

                except Exception as e:
                    import traceback
                    logger.error(f"Error processing email {email_id}: {e}")
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    continue

        except Exception as e:
            logger.error(f"Error in process_account_spam for {account['email']}: {e}")
            raise
        finally:
            if mail:
                try:
                    # Expunge deleted messages (actually remove them from INBOX)
                    mail.expunge()
                    mail.close()
                    mail.logout()
                except:
                    pass

    def process_spam(self):
        """Check for spam emails across all configured accounts"""
        logger.info(f"Processing {len(self.accounts)} account(s)")

        for account in self.accounts:
            try:
                logger.info(f"--- Checking account: {account['email']} ---")
                self.process_account_spam(account)
            except Exception as e:
                logger.error(f"Failed to process account {account['email']}: {e}")
                # Continue with next account even if this one fails
                continue

    def run_once(self):
        """Run a single check cycle"""
        logger.info("=" * 60)
        logger.info("Starting spam check cycle")
        try:
            self.process_spam()
            logger.info("Spam check cycle completed")
        except Exception as e:
            logger.error(f"Error in run cycle: {e}")
        logger.info("=" * 60)

    def run_continuous(self, interval=300):
        """Run continuously with specified interval (default: 5 minutes)"""
        logger.info(f"Starting continuous monitoring (checking every {interval} seconds)")
        while True:
            try:
                self.run_once()
                time.sleep(interval)
            except KeyboardInterrupt:
                logger.info("Stopping spam bouncer...")
                break
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                time.sleep(60)  # Wait a minute before retrying


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Spam Bouncer - Auto-reply to spam with fake bounces')
    parser.add_argument('--once', action='store_true', help='Run once and exit')
    parser.add_argument('--interval', type=int, default=300, help='Check interval in seconds (default: 300)')
    parser.add_argument('--config', default='config.json', help='Config file path')

    args = parser.parse_args()

    bouncer = SpamBouncer(config_file=args.config)

    if args.once:
        bouncer.run_once()
    else:
        bouncer.run_continuous(interval=args.interval)


if __name__ == '__main__':
    main()
