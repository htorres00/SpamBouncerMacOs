# Quick Start Guide

## 5-Minute Setup

### 1. Get iCloud App Password (2 minutes)
1. Visit [appleid.apple.com](https://appleid.apple.com)
2. Go to **Security** → **App-Specific Passwords**
3. Click **Generate Password**
4. Name it "Spam Bouncer"
5. Copy the password (xxxx-xxxx-xxxx-xxxx format)

### 2. Configure (1 minute)
```bash
cd "/Users/hector/TIM Dropbox/Hector Torres/Apps/spam-email"
cp config.json.template config.json
nano config.json  # or use any text editor
```

Replace these fields:
- `email`: Your iCloud email (htorres00@icloud.com)
- `password`: The app-specific password you just created

### 3. Test (30 seconds)
```bash
python3 spam_bouncer.py --once
```

### 4. Install Auto-Start (30 seconds)
```bash
cp com.spambouncer.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.spambouncer.plist
launchctl start com.spambouncer
```

### 5. Verify (30 seconds)
```bash
launchctl list | grep spambouncer
tail -f logs/spam_bouncer_*.log
```

## Done! 🎉

The script is now running in the background and will:
- Monitor **all configured email accounts** (iCloud, Gmail, etc.)
- Check for spam every 5 minutes
- Send fake bounce messages to spammers
- Move spam to Junk folder
- Log all activity to `logs/`
- Compress old logs daily at 2am (keeps 30 days)

## Common Commands

**View logs:**
```bash
tail -f logs/spam_bouncer_*.log
```

**Stop service:**
```bash
launchctl stop com.spambouncer
launchctl unload ~/Library/LaunchAgents/com.spambouncer.plist
```

**Start service:**
```bash
launchctl load ~/Library/LaunchAgents/com.spambouncer.plist
launchctl start com.spambouncer
```

**Manual run:**
```bash
python3 spam_bouncer.py --once
```

## Example Fake Bounce

When a spammer sends you spam, they'll receive:

```
From: Mail Delivery System <MAILER-DAEMON@icloud.com>
Subject: Mail delivery failed: returning message to sender

This is the mail system at host icloud.com.

I'm sorry to have to inform you that your message could not
be delivered to one or more recipients.

<htorres00@icloud.com>: host mail.icloud.com said:
550 5.1.1 Recipient address rejected: User unknown in
local recipient table
```

This makes them think your email address is invalid! 🎭
