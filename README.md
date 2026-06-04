# Kindroid Chat Exporter

A simple command-line Python tool for exporting chat messages from a Kindroid AI using Kindroid’s official API.

This script prompts for your Kindroid API key and AI ID, downloads messages using the `/get-chat-messages` endpoint, respects rate limits, and saves progress as it goes so interrupted exports can be resumed.

## Features

* Exports chat history for a single Kindroid AI
* Prompts for your API key securely instead of hardcoding it
* Uses the maximum supported page size of `100`
* Handles rate limiting with `Retry-After` support and exponential backoff
* Saves a checkpoint after every successful page
* Resumes from the last saved timestamp if interrupted
* Writes exported messages to a readable JSON file
* Does not save your API key

## Requirements

* Python 3.9 or newer
* A Kindroid API key beginning with `kn_`
* The AI ID of the Kindroid you want to export
* The `requests` Python package

Install the required package:

```bash
pip install requests
```

## Getting Your API Key and AI ID

Your Kindroid API key and AI ID can be found in Kindroid’s Profile Settings.

Your API key is sensitive. Anyone with access to it may be able to perform actions on your Kindroid account. Do not share it, publish it, commit it to GitHub, or paste it into untrusted tools.

## Usage

Clone this repository or download the script:

```bash
git clone https://github.com/YOUR_USERNAME/kindroid-chat-exporter.git
cd kindroid-chat-exporter
```

Run the exporter:

```bash
python app.py
```

The script will prompt you for:

1. Your Kindroid API key
2. The AI ID you want to export
3. An optional output filename

Example:

```text
Kindroid Chat Exporter
======================

This exports messages for one Kindroid AI using your kn_ API key.
Your API key is only used locally for this script and is not saved.

Enter your Kindroid API key, starting with kn_:
Enter the AI ID to export:
Output file [kindroid_export_abc123.json]:
```

When complete, the script will save the exported messages to a JSON file.

## Output Format

The exported file is a JSON array of message objects.

Example:

```json
[
  {
    "id": "message_id_here",
    "sender": "sender_id_or_name",
    "sender_type": "ai",
    "display_name": "Beth",
    "timestamp": 1770000000000,
    "message": "Example message text"
  }
]
```

Depending on the message, additional fields may be present, such as:

```json
{
  "image_urls": ["https://example.com/image.png"],
  "image_description": "Description of the image",
  "video_description": "Description of the video",
  "internet_response": "Internet response text",
  "link_url": "https://example.com",
  "link_description": "Description of the link"
}
```

Fields that do not apply to a message may be omitted.

## Rate Limits

Kindroid may return a `429 Too Many Requests` response if the script sends requests too quickly.

This script handles that by:

* Waiting when rate limited
* Respecting the `Retry-After` header if Kindroid provides one
* Falling back to exponential backoff when no retry time is provided
* Adding a small randomized delay between successful requests
* Saving progress after every page

If you are still being rate limited heavily, increase the delay between successful pages in the script:

```python
sleep_for = random.uniform(2.0, 5.0)
```

For stricter pacing, change it to something like:

```python
sleep_for = random.uniform(10.0, 20.0)
```

Do not run multiple exports in parallel. That will likely trigger rate limits more aggressively.

## Resuming an Interrupted Export

The script creates a checkpoint file named:

```text
kindroid_export_checkpoint.json
```

If the export is interrupted, run the script again with the same AI ID. The script will detect the checkpoint and ask whether you want to resume.

Example:

```text
Found a previous checkpoint for this AI.
Previous output file: kindroid_export_abc123.json
Messages already saved: 1200
Last timestamp: 1770000000000
Resume from this checkpoint? [Y/n]:
```

Choose `Y` or press Enter to continue from where the previous run stopped.

## Security Notes

This script does not save your API key.

However, be careful with exported chat files. They may contain private conversations, personal information, links, images, or other sensitive data.

Recommended precautions:

* Do not commit exports to GitHub
* Add exported `.json` files to `.gitignore`
* Store exports in a secure location
* Delete old checkpoint files when no longer needed
* Rotate your API key if you believe it has been exposed

A suggested `.gitignore` entry:

```gitignore
*.json
kindroid_export_checkpoint.json
```

If you want to commit example data, create a sanitized sample file instead.

## Limitations

This script exports messages for one AI ID at a time.

It does not currently:

* Automatically discover all of your Kindroid AIs
* Automatically discover group chat IDs
* Export all account data in one step
* Export group chats unless modified to use `group_id`
* Decrypt or process older unofficial Firestore/archive formats

The Kindroid API endpoint supports both `ai_id` and `group_id`, but this version of the script is focused on single-AI exports for simplicity.

## Group Chat Support

The official API also supports fetching messages by `group_id`.

To adapt the script for group chats, replace the request parameter:

```python
"ai_id": ai_id
```

with:

```python
"group_id": group_id
```

A future version may add a prompt allowing the user to choose between AI export and group chat export.

## Troubleshooting

### `401 Unauthorized`

Your API key was rejected.

Check that:

* The key starts with `kn_`
* The key was copied correctly
* There are no extra spaces before or after the key

### `403 Forbidden`

The request is not allowed.

Possible causes:

* The AI ID does not belong to your account
* Your account does not have access to the requested resource
* You are trying to access a group chat without the required subscription status

### `400 Bad Request`

The request was malformed.

Check that:

* You entered the correct AI ID
* You are using only one identifier type at a time
* The API endpoint has not changed

### `429 Too Many Requests`

Kindroid is rate limiting the export.

The script should pause and retry automatically. If this happens repeatedly, increase the delay between successful requests.

### Export Stops Midway

Run the script again. If a checkpoint exists, the script should offer to resume.

## Disclaimer

This is an unofficial utility for personal data export using Kindroid’s documented API behavior.

It is not affiliated with, endorsed by, or maintained by Kindroid.

Use it responsibly, respect Kindroid’s rate limits, and keep your API key private.

## License

MIT License

You are free to use, modify, and distribute this script, provided you include the license notice.
