# Spam Bouncer

Automatically reply to spam emails with convincing fake bounce messages to discourage future spam.

## How It Works

1. **Monitors** your iCloud mailbox for spam messages (marked with `X-Clx-Spam: true` or similar headers)
2. **Sends** a fake "bounce" message that looks like it came from the Mail Delivery System (MAILER-DAEMON)
3. **Tricks** spammers into thinking your email address is invalid
4. **Logs** all activity for your review

## Features

- ✅ Convincing fake bounce messages with realistic SMTP error codes (550, 551, 553)
- ✅ Random bounce reasons to appear natural
- ✅ Automatically moves spam to Junk folder after bouncing
- ✅ Tracks processed emails to avoid duplicates within sessions
- ✅ Comprehensive logging with automatic cleanup
- ✅ Daily log compression (older than 1 day) and 30-day retention
- ✅ Can run once or continuously
- ✅ Launch Agent support for automatic background operation

## Setup Instructions

### 1. Create iCloud App-Specific Password

Since you're using iCloud, you need an app-specific password:

1. Go to [appleid.apple.com](https://appleid.apple.com)
2. Sign in and go to **Security** section
3. Under **App-Specific Passwords**, click **Generate Password**
4. Name it "Spam Bouncer" or similar
5. Copy the generated password (format: xxxx-xxxx-xxxx-xxxx)

### 2. Configure the Script

Create `config.json` from the template:

```bash
cd "/Users/hector/TIM Dropbox/Hector Torres/Apps/spam-email"
cp config.json.template config.json
```

Edit `config.json` with your details:

```json
{
  "email": "htorres00@icloud.com",
  "password": "your-app-specific-password-here",
  "imap_server": "imap.mail.me.com",
  "imap_port": 993,
  "smtp_server": "smtp.mail.me.com",
  "smtp_port": 587
}
```

**⚠️ Important**: Never commit `config.json` to version control (it contains your password).

### 3. Test the Script

Run it once to make sure everything works:

```bash
python3 spam_bouncer.py --once
```

Check the logs:
```bash
tail -f logs/spam_bouncer_*.log
```

### 4. Install as Launch Agent (Auto-Start)

To run automatically in the background:

```bash
# Copy the plist to LaunchAgents directory
cp com.spambouncer.plist ~/Library/LaunchAgents/

# Load the agent
launchctl load ~/Library/LaunchAgents/com.spambouncer.plist

# Start the agent
launchctl start com.spambouncer
```

### 5. Verify It's Running

```bash
# Check if it's loaded
launchctl list | grep spambouncer

# Check the logs
tail -f logs/spam_bouncer_*.log
```

## Usage

### Run Once (Manual)
```bash
python3 spam_bouncer.py --once
```

### Run Continuously (Check every 5 minutes)
```bash
python3 spam_bouncer.py
```

### Custom Check Interval (e.g., every 2 minutes)
```bash
python3 spam_bouncer.py --interval 120
```

### Stop the Launch Agent
```bash
launchctl stop com.spambouncer
launchctl unload ~/Library/LaunchAgents/com.spambouncer.plist
```

### Start the Launch Agent
```bash
launchctl load ~/Library/LaunchAgents/com.spambouncer.plist
launchctl start com.spambouncer
```

## How the Fake Bounce Works

The script generates messages that look like official Mail Delivery System failures:

```
From: Mail Delivery System <MAILER-DAEMON@icloud.com>
Subject: Mail delivery failed: returning message to sender

This is the mail system at host icloud.com.

I'm sorry to have to inform you that your message could not
be delivered to one or more recipients.

<htorres00@icloud.com>: host mail.icloud.com said: 550 5.1.1
Recipient address rejected: User unknown in local recipient table
```

This uses standard SMTP error codes that spammers recognize as permanent failures.

## Bounce Message Types

The script randomly selects from these realistic bounce reasons:

1. **550 5.1.1** - User unknown in local recipient table
2. **550 5.7.1** - Access denied
3. **553 5.3.0** - Mailbox unavailable
4. **551 5.1.1** - User not local

## Logs

All activity is logged in the `logs/` directory:

- `spam_bouncer_YYYYMMDD.log` - Daily log file with all operations
- `spam_bouncer_YYYYMMDD.log.gz` - Compressed logs (older than 1 day)
- `spam_bouncer_stdout.log` - Standard output (when running as Launch Agent)
- `spam_bouncer_stderr.log` - Error output (when running as Launch Agent)
- `log_cleanup.log` - Log cleanup activity (compression and deletion)
- `processed_emails.txt` - List of already processed email IDs

### Automatic Log Management

Logs are automatically managed by a separate service:

- **Daily at 2am**: Old logs are compressed and cleaned
- **Compression**: Logs older than 1 day are gzipped (saves space)
- **Retention**: Logs older than 30 days are deleted
- **Launch Agent**: `com.spambouncer.logcleanup`

To manually run log cleanup:
```bash
cd "/Users/hector/TIM Dropbox/Hector Torres/Apps/spam-email"
python3 log_cleanup.py
```

To check log cleanup status:
```bash
launchctl list | grep logcleanup
cat logs/log_cleanup.log
```

## Important Warnings

⚠️ **Potential Risks:**

1. **Email Confirmation**: Even fake bounces confirm someone is monitoring the address
2. **Email Loops**: Some auto-responders might reply back, creating loops
3. **Legitimate Emails**: Make sure your spam filter is accurate to avoid bouncing real emails
4. **iCloud Rate Limits**: Sending too many emails might trigger rate limits

## Troubleshooting

### "Login failed"
- Verify you're using an **app-specific password**, not your regular iCloud password
- Check that your email address is correct

### "Connection refused"
- Verify iCloud IMAP/SMTP settings are correct
- Check your internet connection
- Ensure firewall isn't blocking the connection

### "No spam found"
- Check that Apple Mail is properly marking spam with headers
- Look at a spam email's full headers to see what headers are present
- Modify the spam detection logic in `process_spam()` if needed

### Script not running automatically
```bash
# Check if it's loaded
launchctl list | grep spambouncer

# View errors
cat logs/spam_bouncer_stderr.log

# Reload the agent
launchctl unload ~/Library/LaunchAgents/com.spambouncer.plist
launchctl load ~/Library/LaunchAgents/com.spambouncer.plist
```

## Customization

### Change Bounce Message

Edit the `bounce_templates` list in `spam_bouncer.py` around line 88:

```python
bounce_templates = [
    {
        'code': '550 5.1.1',
        'title': 'Your custom message here',
        'reason': 'Custom reason here'
    }
]
```

### Change Spam Detection

Modify the spam detection logic around line 196:

```python
is_spam = (
    msg.get('X-Clx-Spam', '').lower() == 'true' or
    msg.get('X-Proofpoint-Spam-Details', '') != '' or
    # Add your own conditions here
)
```

### Change Check Interval

Edit `com.spambouncer.plist` and change:

```xml
<string>--interval</string>
<string>300</string>  <!-- Change to desired seconds -->
```

Then reload:
```bash
launchctl unload ~/Library/LaunchAgents/com.spambouncer.plist
launchctl load ~/Library/LaunchAgents/com.spambouncer.plist
```

## Security Notes

- ✅ Uses app-specific password (not your main iCloud password)
- ✅ Credentials stored locally in `config.json` (not in code)
- ✅ All communication over encrypted connections (SSL/TLS)
- ⚠️ Keep `config.json` secure and never share it

## License

This is a personal utility script. Use at your own risk.

---

**Created**: November 4, 2025
**Author**: Hector Torres
