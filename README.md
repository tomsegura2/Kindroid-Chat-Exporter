# Kindroid Chat Exporter

A simple command-line Python tool for exporting chat messages from a Kindroid AI or group chat using Kindroid's official API (for official documentation, see https://kindroid.ai/docs/article/api-documentation/).

This script prompts for your Kindroid API key and AI ID (or group ID), downloads messages using the `/get-chat-messages` endpoint, handles rate limits and transient server errors automatically, and saves progress as it goes so interrupted exports can be resumed.

## Features

* Exports chat history for a single Kindroid AI **or group chat**
* Prompts for your API key securely instead of hardcoding it
* Explicitly requests the maximum supported page size of `100` (API default is `50`)
* Handles rate limiting with `Retry-After` support and exponential backoff
* **Retries automatically on transient 5xx server errors** instead of aborting
* Saves a checkpoint after every successful page
* Resumes from the last saved timestamp if interrupted
* Writes exported messages to a readable JSON file
* Does not save your API key

## Requirements

* Python 3.9 or newer
* A Kindroid API key beginning with `kn_`
* The AI ID of the Kindroid you want to export, or a group ID for group chats
* The `requests` Python package

Install the required package:

```bash
pip install requests
```

## Getting Your API Key and AI ID

Your Kindroid API key and AI ID can be found in Kindroid's Profile Settings.

Your API key is sensitive. Anyone with access to it may be able to perform actions on your Kindroid account. Do not share it, publish it, commit it to GitHub, or paste it into untrusted tools.

## Usage

Clone this repository or download the script:

```bash
git clone https://github.com/tomsegura2/kindroid-chat-exporter.git
cd kindroid-chat-exporter
```

Run the exporter:

```bash
python app.py
```

The script will prompt you for:

1. Your Kindroid API key
2. Whether you are exporting a single AI or a group chat
3. The AI ID or group ID you want to export
4. An optional output filename

Example (single AI export):

```text
Kindroid Chat Exporter
======================

Exports messages for a Kindroid AI or group chat using your kn_ API key.
Your API key is only used locally for this script and is not saved.

Enter your Kindroid API key, starting with kn_:

Export type:
  1) Single AI  (ai_id)
  2) Group chat (group_id)
Choose [1/2, default 1]:
Enter the AI ID to export:
Output file [kindroid_export_abc123.json]:
```

When complete, the script will save the exported messages to a JSON file.

## Output Format

The exported file is a JSON array of message objects, ordered oldest first.

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

Depending on the message, additional fields may be present:

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

Fields that do not apply to a message are omitted by the API.

The full set of possible fields per message is:

| Field | Description |
|---|---|
| `id` | Unique message identifier |
| `sender` | Sender identifier |
| `sender_type` | `"ai"` or `"user"` |
| `display_name` | Display name of the sender |
| `timestamp` | Unix timestamp in milliseconds |
| `message` | Message text |
| `image_urls` | Array of image URLs attached to the message |
| `image_description` | Description of attached image |
| `video_description` | Description of attached video |
| `internet_response` | Internet search response content |
| `link_url` | URL attached to the message |
| `link_description` | Description of the attached link |

## Rate Limits and Server Errors

### Rate limiting (429)

Kindroid may return a `429 Too Many Requests` response if the script sends requests too quickly.

This script handles that by:

* Respecting the `Retry-After` header if Kindroid provides one
* Falling back to exponential backoff with jitter when no retry time is provided
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

### Server errors (5xx)

Transient server-side errors (`500`, `502`, `503`, `504`) are retried automatically using the same exponential backoff logic as rate limits. The export will not abort on a single server hiccup.

## Resuming an Interrupted Export

The script creates a checkpoint file named:

```text
kindroid_export_checkpoint.json
```

If the export is interrupted for any reason — rate limiting, a network drop, a `KeyboardInterrupt`, or a transient server error — run the script again with the same AI ID or group ID. The script will detect the checkpoint and ask whether you want to resume.

Example:

```text
Found a previous checkpoint for this export.
Previous output file : kindroid_export_abc123.json
Messages already saved: 1200
Last timestamp        : 1770000000000
Resume from this checkpoint? [Y/n]:
```

Choose `Y` or press Enter to continue from where the previous run stopped.

## Group Chat Support

The script supports exporting group chats in addition to single-AI histories. When prompted for export type, choose option `2` and enter your group ID.

Group chats require an active Kindroid subscription. If your account does not have the required subscription level, the API will return `403 Forbidden`.

Group IDs can be found in the Kindroid app. Groups must be created in the app; this script only exports from existing groups.

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

This script exports messages for one AI ID or group ID at a time.

It does not currently:

* Automatically discover all of your Kindroid AIs
* Automatically discover group chat IDs
* Export all account data in one step
* Decrypt or process older unofficial Firestore/archive formats

## Troubleshooting

### `401 Unauthorized`

Your API key was rejected.

Check that:

* The key starts with `kn_`
* The key was copied correctly with no extra spaces

### `403 Forbidden`

The request is not allowed.

Possible causes:

* The AI ID or group ID does not belong to your account
* You are trying to access a group chat without the required subscription status

### `400 Bad Request`

The request was malformed.

Check that:

* You entered the correct AI ID or group ID
* You selected the correct export type (AI vs. group chat)
* The API endpoint has not changed

### `429 Too Many Requests`

Kindroid is rate limiting the export.

The script will pause and retry automatically using the `Retry-After` header or exponential backoff. If this happens repeatedly, increase the delay between successful requests (see [Rate Limits and Server Errors](#rate-limits-and-server-errors)).

### `500` / `502` / `503` / `504` Server Errors

The script retries these automatically with exponential backoff. If retries are consistently failing, the Kindroid API may be experiencing an outage. The export will abort after the backoff ceiling is exceeded; your checkpoint will be preserved and the export can be resumed once the service recovers.

### Export Stops Midway

Run the script again with the same AI ID or group ID. If a checkpoint exists, the script will offer to resume.

## Disclaimer

This is an unofficial utility for personal data export using Kindroid's documented API.

It is not affiliated with, endorsed by, or maintained by Kindroid.

Use it responsibly, respect Kindroid's rate limits, and keep your API key private.

## License

Apache 2.0

You are free to use, modify, and distribute this script, provided you include the license notice.
