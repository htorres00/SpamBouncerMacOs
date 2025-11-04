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
        self.processed_file = LOG_DIR / 'processed_emails.txt'
        self.processed_ids = self._load_processed()

    def _load_config(self, config_file):
        """Load configuration from JSON file"""
        config_path = Path(__file__).parent / config_file
        if not config_path.exists():
            raise FileNotFoundError(
                f"Config file not found: {config_path}\n"
                "Please create config.json with your iCloud credentials."
            )
        with open(config_path) as f:
            return json.load(f)

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
        msg['From'] = f'Mail Delivery System <MAILER-DAEMON@{self._get_domain(recipient)}>'
        msg['To'] = original_from
        msg['Subject'] = f'Mail delivery failed: returning message to sender'
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

    def connect_imap(self):
        """Connect to IMAP server"""
        try:
            logger.info("Connecting to IMAP server...")
            mail = imaplib.IMAP4_SSL(self.config['imap_server'], self.config.get('imap_port', 993))
            mail.login(self.config['email'], self.config['password'])
            logger.info("Successfully connected to IMAP")
            return mail
        except Exception as e:
            logger.error(f"IMAP connection failed: {e}")
            raise

    def send_bounce(self, to_address, original_subject, recipient):
        """Send fake bounce message"""
        try:
            logger.info(f"Sending bounce to: {to_address}")

            # Create bounce message
            bounce_msg = self._create_bounce_message(to_address, original_subject, recipient)

            # Connect to SMTP and send
            with smtplib.SMTP(self.config['smtp_server'], self.config.get('smtp_port', 587)) as server:
                server.starttls()
                server.login(self.config['email'], self.config['password'])
                server.send_message(bounce_msg)

            logger.info(f"Bounce sent successfully to {to_address}")
            return True

        except Exception as e:
            logger.error(f"Failed to send bounce to {to_address}: {e}")
            return False

    def process_spam(self):
        """Check for spam emails and send bounce messages"""
        mail = None
        try:
            mail = self.connect_imap()
            mail.select('INBOX')

            # Search for unread spam messages
            # Looking for messages with X-Clx-Spam: true header
            status, messages = mail.search(None, 'UNSEEN')

            if status != 'OK':
                logger.error("Failed to search for messages")
                return

            if not messages or not messages[0]:
                logger.info("No unread messages found")
                return

            email_ids = messages[0].split()
            logger.info(f"Found {len(email_ids)} unread messages to check")

            for email_id in email_ids:
                try:
                    # Fetch the email
                    status, msg_data = mail.fetch(email_id, '(RFC822)')
                    if status != 'OK':
                        continue

                    # Parse email
                    raw_email = msg_data[0][1]
                    msg = email.message_from_bytes(raw_email)

                    # Check if it's spam
                    is_spam = (
                        msg.get('X-Clx-Spam', '').lower() == 'true' or
                        msg.get('X-Proofpoint-Spam-Details', '') != ''
                    )

                    if not is_spam:
                        logger.debug(f"Email {email_id} is not spam, skipping")
                        continue

                    # Get sender info
                    from_header = msg.get('From', '')
                    subject = msg.get('Subject', '(No Subject)')
                    message_id = msg.get('Message-ID', email_id.decode() if isinstance(email_id, bytes) else str(email_id))

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
                    if self.send_bounce(from_email, subject, self.config['email']):
                        self._mark_processed(message_id)
                        logger.info(f"Successfully bounced spam from {from_email}")

                        # Move to Junk folder
                        try:
                            # Try common spam folder names
                            spam_folders = ['Junk', 'Spam', 'INBOX.Junk', 'INBOX.Spam']
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
                    logger.error(f"Error processing email {email_id}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error in process_spam: {e}")
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
