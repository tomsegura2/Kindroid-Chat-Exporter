#!/usr/bin/env python3
"""
Kindroid Chat Exporter

Exports all messages for a single Kindroid AI or group chat using the official
/get-chat-messages endpoint.

Features:
- Prompts for API key and AI ID (or group ID)
- Hides API key input
- Explicitly requests the maximum page size of 100 (API default is 50)
- Handles 429 rate limits with Retry-After support and exponential backoff
- Retries on transient 5xx server errors with exponential backoff
- Saves a checkpoint after every successful page
- Resumes from the last saved timestamp if interrupted
- Writes a clean JSON export file

Message fields exported (fields absent on a given message are omitted):
  id, sender, sender_type, display_name, timestamp, message,
  image_urls, image_description, video_description,
  internet_response, link_url, link_description

Install dependency:
    pip install requests

Run:
    python app.py
"""

import json
import time
import random
import getpass
from pathlib import Path
from datetime import datetime

import requests


BASE_URL = "https://api.kindroid.ai/v1"
GET_CHAT_MESSAGES_URL = f"{BASE_URL}/get-chat-messages"

# The API accepts 1–100; explicitly request the maximum.
# The API default is 50 — do not omit this parameter if you want full pages.
MAX_LIMIT = 100

CHECKPOINT_FILE = Path("kindroid_export_checkpoint.json")

# Transient server-side status codes that should be retried rather than aborted.
RETRYABLE_STATUS_CODES = {500, 502, 503, 504}


def prompt_nonempty(prompt_text: str) -> str:
    while True:
        value = input(prompt_text).strip()
        if value:
            return value
        print("Please enter a value.")


def safe_filename(value: str) -> str:
    keep = []
    for char in value:
        if char.isalnum() or char in ("-", "_"):
            keep.append(char)
        else:
            keep.append("_")
    return "".join(keep)


def load_checkpoint(identifier: str):
    """
    Load a checkpoint for the given ai_id or group_id.
    Returns the checkpoint dict, or None if none exists or it doesn't match.
    """
    if not CHECKPOINT_FILE.exists():
        return None

    try:
        checkpoint = json.loads(CHECKPOINT_FILE.read_text(encoding="utf-8"))
    except Exception:
        print("Checkpoint file exists, but could not be read. Ignoring it.")
        return None

    # Support both old (ai_id-keyed) and new (identifier-keyed) checkpoints.
    stored_id = checkpoint.get("identifier") or checkpoint.get("ai_id")
    if stored_id != identifier:
        return None

    return checkpoint


def save_checkpoint(
    identifier: str,
    id_type: str,
    output_file: str,
    last_timestamp,
    message_count: int,
):
    """
    Persist pagination state so the export can be resumed after an interruption.

    identifier : the ai_id or group_id value
    id_type    : "ai_id" or "group_id"
    """
    checkpoint = {
        "identifier": identifier,
        "id_type": id_type,
        "output_file": output_file,
        "last_timestamp": last_timestamp,
        "message_count": message_count,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
    }

    CHECKPOINT_FILE.write_text(
        json.dumps(checkpoint, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def request_page_with_backoff(headers: dict, params: dict) -> dict:
    """
    GET /get-chat-messages with automatic retry on rate limits and server errors.

    Retry behaviour:
      429  — waits for Retry-After (if provided) or uses exponential backoff
      5xx  — uses exponential backoff (transient server-side errors)
      4xx  — raises immediately (caller error, retrying will not help)
    """
    delay = 10
    max_delay = 300

    while True:
        response = requests.get(
            GET_CHAT_MESSAGES_URL,
            headers=headers,
            params=params,
            timeout=90,
        )

        if response.status_code == 200:
            return response.json()

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")

            if retry_after:
                try:
                    sleep_for = int(retry_after)
                except ValueError:
                    sleep_for = delay
            else:
                sleep_for = delay + random.uniform(0, 3)

            print()
            print(f"Rate limited by Kindroid. Pausing for {sleep_for:.1f} seconds...")
            print("Progress is saved, so this can safely take its time.")

            time.sleep(sleep_for)
            delay = min(delay * 2, max_delay)
            continue

        if response.status_code in RETRYABLE_STATUS_CODES:
            sleep_for = delay + random.uniform(0, 3)
            print()
            print(
                f"Server error {response.status_code}. "
                f"Retrying in {sleep_for:.1f} seconds..."
            )
            time.sleep(sleep_for)
            delay = min(delay * 2, max_delay)
            continue

        if response.status_code == 401:
            raise RuntimeError(
                "Unauthorized. Your API key was rejected. "
                "Check that it starts with kn_ and was copied correctly."
            )

        if response.status_code == 403:
            raise RuntimeError(
                "Forbidden. The API key is valid, but this request is not allowed. "
                "Check that the AI ID (or group ID) belongs to this account, and that "
                "your subscription level permits the requested resource."
            )

        if response.status_code == 400:
            raise RuntimeError(
                f"Bad request. Check your AI ID or group ID.\n\nServer said:\n{response.text}"
            )

        raise RuntimeError(
            f"Unexpected error: HTTP {response.status_code}\n\nServer said:\n{response.text}"
        )


def export_messages(
    api_key: str,
    identifier: str,
    id_type: str,
    output_file: Path,
    resume: bool = True,
) -> list:
    """
    Paginate through /get-chat-messages and write every message to output_file.

    identifier : the value of ai_id or group_id
    id_type    : "ai_id" or "group_id"
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
    }

    all_messages = []
    start_after_timestamp = None

    if resume:
        checkpoint = load_checkpoint(identifier)

        if checkpoint:
            previous_file = Path(checkpoint["output_file"])

            if previous_file.exists():
                print()
                print("Found a previous checkpoint for this export.")
                print(f"Previous output file : {previous_file}")
                print(f"Messages already saved: {checkpoint.get('message_count', 0)}")
                print(f"Last timestamp        : {checkpoint.get('last_timestamp')}")

                choice = input("Resume from this checkpoint? [Y/n]: ").strip().lower()

                if choice in ("", "y", "yes"):
                    output_file = previous_file
                    start_after_timestamp = checkpoint.get("last_timestamp")

                    try:
                        all_messages = json.loads(
                            output_file.read_text(encoding="utf-8")
                        )
                    except Exception:
                        print("Could not read previous output file. Starting fresh.")
                        all_messages = []
                        start_after_timestamp = None
                else:
                    print("Starting a fresh export.")

    page_number = 1

    while True:
        # The API accepts exactly one of ai_id or group_id — never both.
        params: dict = {
            id_type: identifier,
            "limit": MAX_LIMIT,
        }

        if start_after_timestamp is not None:
            # Must be a number (Unix ms timestamp), not a string.
            params["start_after_timestamp"] = start_after_timestamp

        print()
        print(f"Fetching page {page_number}...")

        data = request_page_with_backoff(headers, params)

        messages = data.get("messages", [])
        pagination = data.get("pagination", {})

        if not isinstance(messages, list):
            raise RuntimeError("Unexpected response: 'messages' was not a list.")

        all_messages.extend(messages)

        output_file.write_text(
            json.dumps(all_messages, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        last_timestamp = pagination.get("lastTimestamp")
        has_more = pagination.get("hasMore", False)
        returned_limit = pagination.get("limit")

        save_checkpoint(
            identifier=identifier,
            id_type=id_type,
            output_file=str(output_file),
            last_timestamp=last_timestamp,
            message_count=len(all_messages),
        )

        print(f"Fetched {len(messages)} messages (page limit reported by API: {returned_limit}).")
        print(f"Total saved: {len(all_messages)} messages.")

        if not has_more:
            print()
            print("Export complete.")
            break

        if last_timestamp is None:
            raise RuntimeError(
                "Kindroid said there are more messages, but did not return lastTimestamp."
            )

        start_after_timestamp = last_timestamp
        page_number += 1

        # Gentle pacing even when not rate-limited.
        # Increase this if Kindroid is still hitting you with 429s.
        sleep_for = random.uniform(2.0, 5.0)
        print(f"Waiting {sleep_for:.1f} seconds before the next page...")
        time.sleep(sleep_for)

    return all_messages


def main():
    print("Kindroid Chat Exporter")
    print("======================")
    print()
    print("Exports messages for a Kindroid AI or group chat using your kn_ API key.")
    print("Your API key is only used locally for this script and is not saved.")
    print()

    api_key = getpass.getpass("Enter your Kindroid API key, starting with kn_: ").strip()

    if not api_key.startswith("kn_"):
        print()
        print("Warning: That does not look like a Kindroid kn_ API key.")
        choice = input("Continue anyway? [y/N]: ").strip().lower()
        if choice not in ("y", "yes"):
            print("Canceled.")
            return

    print()
    print("Export type:")
    print("  1) Single AI  (ai_id)")
    print("  2) Group chat (group_id)")
    export_type = input("Choose [1/2, default 1]: ").strip()

    if export_type == "2":
        id_type = "group_id"
        identifier = prompt_nonempty("Enter the group ID to export: ")
    else:
        id_type = "ai_id"
        identifier = prompt_nonempty("Enter the AI ID to export: ")

    default_name = f"kindroid_export_{safe_filename(identifier)}.json"
    output_input = input(f"Output file [{default_name}]: ").strip()
    output_file = Path(output_input or default_name)

    print()
    print("Starting export.")
    print(f"{'Group ID' if id_type == 'group_id' else 'AI ID'}: {identifier}")
    print(f"Output file: {output_file}")
    print()

    try:
        messages = export_messages(
            api_key=api_key,
            identifier=identifier,
            id_type=id_type,
            output_file=output_file,
            resume=True,
        )

        print()
        print(f"Saved {len(messages)} messages to:")
        print(output_file.resolve())

        if CHECKPOINT_FILE.exists():
            cleanup = (
                input("Delete checkpoint file now that export is complete? [Y/n]: ")
                .strip()
                .lower()
            )
            if cleanup in ("", "y", "yes"):
                CHECKPOINT_FILE.unlink()
                print("Checkpoint deleted.")

    except KeyboardInterrupt:
        print()
        print("Export interrupted.")
        print("Progress should be saved. Run the script again to resume.")

    except Exception as exc:
        print()
        print("Export failed:")
        print(exc)
        print()
        print("Progress may still be saved in:")
        print(CHECKPOINT_FILE.resolve())


if __name__ == "__main__":
    main()
