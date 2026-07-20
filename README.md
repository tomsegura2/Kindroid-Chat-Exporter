# Kindroid Chat Exporter

[![CodeQL Advanced](https://github.com/tomsegura2/Kindroid-Chat-Exporter/actions/workflows/codeql.yml/badge.svg)](https://github.com/tomsegura2/Kindroid-Chat-Exporter/actions/workflows/codeql.yml)

[![Quality gate status](https://sonarcloud.io/api/project_badges/measure?project=tomsegura2_Kindroid-Chat-Exporter&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=tomsegura2_Kindroid-Chat-Exporter)

A Python utility for exporting chat histories from Kindroid AI characters and group chats using Kindroid's official API.

The exporter downloads your messages directly from Kindroid, saves them locally, supports automatic resume after interruptions, and can convert exports into multiple formats including JSON, JSONL, Markdown, plain text, and PDF.

## Why This Exists

Kindroid conversations can represent hundreds or thousands of hours of writing, roleplay, companionship, journaling, and creative work.

This project exists to allow users to:

* Create personal backups of their conversations
* Preserve chat histories for archival purposes
* Analyze conversations using local tools
* Import conversations into other applications
* Maintain ownership of their personal data

The exporter uses Kindroid's documented API and accesses only conversations associated with your own account.

---

# Features

* Export chat history for a single AI
* Export group chat history
* Secure API key entry (hidden or visible mode)
* Automatic handling of API rate limits
* Automatic retry of temporary server errors
* Checkpointing after every successful page
* Resume interrupted exports
* Automatic display name restoration for single-AI exports
* Convert exports to:

  * JSON
  * JSON Lines (JSONL)
  * Plain Text
  * Markdown
  * PDF
* Beginner-friendly command-line interface
* No telemetry
* No analytics
* No external servers

---

# Privacy & Security Model

## What This Tool Does

This tool:

* Connects directly to Kindroid's official API
* Downloads messages associated with an AI ID or Group ID that you provide
* Saves those messages to files on your local computer

## What This Tool Does Not Do

This tool does **not**:

* Send data to any server operated by the author
* Upload conversations to third parties
* Collect analytics
* Collect telemetry
* Track usage
* Modify your Kindroid account
* Access conversations belonging to other users
* Save your API key to disk

## Data Flow

```text
Your Computer
      |
      | HTTPS (TLS encrypted)
      v
api.kindroid.ai
      |
      v
Local Export File
```

No intermediary servers are involved.

All communication occurs directly between your computer and Kindroid's API.

---

# API Key Handling

Your Kindroid API key:

* Is entered locally
* Is stored only in memory while the application is running
* Is transmitted only to Kindroid's official API
* Is sent using HTTPS encryption
* Is never written to disk
* Is never included in export files
* Is never stored in checkpoint files

The exporter uses the standard HTTP Authorization header:

```http
Authorization: Bearer kn_xxxxxxxxxxxxxxxxx
```

The API key is not included in URLs, filenames, logs, or exported data.

---

# Verifying the Source Code

This repository is fully open source.

Users are encouraged to:

* Review the source code before running it
* Build executables themselves from source
* Inspect network traffic with Wireshark, Fiddler, Burp Suite, or similar tools
* Verify release hashes before execution
* Run the exporter in a sandboxed environment if desired

No code obfuscation is used.

---

# Requirements

* Python 3.9 or newer
* Kindroid API key
* AI ID or Group ID
* requests
* reportlab (optional, for PDF conversion)

Install dependencies:

```bash
pip install requests
pip install reportlab
```

---

# Installation

Clone the repository:

```bash
git clone https://github.com/tomsegura2/kindroid-chat-exporter.git
cd kindroid-chat-exporter
```

Run the exporter:

```bash
python app.py
```

---

# Getting Your API Key

Within Kindroid:

```text
Profile
 └── Settings
      └── API Key
```

API keys begin with:

```text
kn_
```

Treat your API key like a password.

Do not:

* Share it publicly
* Post it online
* Commit it to GitHub
* Include it in screenshots

---

# Getting Your AI ID

Within Kindroid:

```text
Profile
 └── Settings
      └── AI ID
```

For group exports, use the Group ID instead.

---

# Usage

Launch the application:

```bash
python app.py
```

Main menu:

```text
1) Download a chat export
2) Convert an export
3) View session summary
4) Exit
```

---

# Exporting a Single AI

Choose:

```text
1) Chat with a single AI
```

You will be asked for:

* API Key
* AI ID
* Character Name
* User Name (optional)

The exporter will automatically generate a filename such as:

```text
Lisa_Chat_Export_20260609.json
```

---

# Exporting a Group Chat

Choose:

```text
2) Group chat
```

You will be prompted for:

* API Key
* Group ID

The exporter will create a file such as:

```text
Group_ABC123_Chat_Export_20260609.json
```

---

# Export Formats

## JSON

Native export format.

Example:

```json
{
  "display_name": "Beth",
  "sender": "ai",
  "timestamp": 1770000000000,
  "message": "Hello there."
}
```

## JSONL

One JSON object per line.

Useful for:

* Machine learning
* Data pipelines
* Importing into analysis tools

## Plain Text

Example:

```text
[2026-06-09 14:22:11] Beth

Hello there.
```

## Markdown

Example:

```markdown
## Beth

Hello there.
```

## PDF

Formatted document suitable for:

* Printing
* Reading offline
* Long-term archival

---

# Checkpointing & Resume

The exporter automatically creates:

```text
kindroid_export_checkpoint.json
```

after every successful page download.

If an export is interrupted:

* Power outage
* Application closed
* Network failure
* Rate limiting
* Keyboard interrupt

simply launch the exporter again and choose the same AI or Group ID.

The exporter will offer to resume automatically.

---

# Checkpoint File Contents

Checkpoint files contain:

* AI ID or Group ID
* Output filename
* Last downloaded timestamp
* Message count
* Save timestamp

Checkpoint files do **not** contain:

* API keys
* Message content
* Passwords
* Authentication credentials

---

# Rate Limiting

Kindroid may occasionally return:

```text
429 Too Many Requests
```

The exporter automatically:

* Honors Retry-After headers
* Uses exponential backoff
* Adds randomized request spacing
* Saves progress before retrying

No manual intervention is normally required.

---

# Server Errors

The exporter automatically retries:

```text
500 Internal Server Error
502 Bad Gateway
503 Service Unavailable
504 Gateway Timeout
```

using exponential backoff.

Progress remains preserved throughout the retry process.

---

# Security Recommendations

Exported files may contain:

* Personal information
* Journal entries
* Roleplay content
* Images
* Links
* Private conversations

Recommended practices:

* Store exports securely
* Encrypt backups
* Avoid public cloud sharing
* Exclude exports from Git repositories

Suggested .gitignore:

```gitignore
*.json
*.jsonl
*.txt
*.md
*.pdf
kindroid_export_checkpoint.json
```

---

# Limitations

This exporter currently does not:

* Automatically discover AI IDs
* Automatically discover Group IDs
* Export every AI in an account automatically
* Modify Kindroid conversations
* Upload data back to Kindroid

It is a read-only export tool.

---

# Troubleshooting

## 401 Unauthorized

Possible causes:

* Invalid API key
* Extra spaces in API key
* Expired or revoked key

## 403 Forbidden

Possible causes:

* AI ID does not belong to your account
* Group access requires a subscription level you do not have

## 400 Bad Request

Possible causes:

* Invalid AI ID
* Invalid Group ID
* API changes

## 429 Too Many Requests

The exporter will retry automatically.

## Export Stops Midway

Run the exporter again.

If a checkpoint exists, the exporter will offer to resume.

---

# Frequently Asked Questions

### Does this save my API key?

No.

The key exists only in memory during the current session.

### Does this send data to the developer?

No.

The exporter communicates only with Kindroid's official API.

### Can I verify that?

Yes.

The entire source code is available for inspection.

You can also monitor network traffic using tools such as Wireshark or Fiddler.

### Does this modify my chats?

No.

The exporter only downloads data.

### Can I export group chats?

Yes.

Provided your account has access to the group chat and the API permits access.

---

# Disclaimer

This is an unofficial utility that uses Kindroid's documented API.

This project is not affiliated with, endorsed by, sponsored by, or maintained by Kindroid.

Users are responsible for complying with Kindroid's Terms of Service and safeguarding their exported data.

---

# License

Apache License 2.0

Copyright (c) Contributors

Licensed under the Apache License, Version 2.0.
