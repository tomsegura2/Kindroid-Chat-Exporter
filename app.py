#!/usr/bin/env python3
"""
Kindroid Chat Exporter

Exports all messages for a single Kindroid AI using the official
/get-chat-messages endpoint.

Features:
- Prompts for API key and AI ID
- Hides API key input
- Uses max page size: limit=100
- Respects rate limits with Retry-After + exponential backoff
- Saves progress after every page
- Can resume from checkpoint
- Writes a clean JSON export file

Install dependency:
    pip install requests

Run:
    python kindroid_export.py
"""

import json
import time
import random
import getpass
from pathlib import Path
from datetime import datetime

import requests


BASE_URL = "https://api.kindroid.ai/v1/get-chat-messages"
MAX_LIMIT = 100

CHECKPOINT_FILE = Path("kindroid_export_checkpoint.json")


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


def load_checkpoint(ai_id: str):
    if not CHECKPOINT_FILE.exists():
        return None

    try:
        checkpoint = json.loads(CHECKPOINT_FILE.read_text(encoding="utf-8"))
    except Exception:
        print("Checkpoint file exists, but could not be read. Ignoring it.")
        return None

    if checkpoint.get("ai_id") != ai_id:
        return None

    return checkpoint


def save_checkpoint(ai_id: str, output_file: str, last_timestamp, message_count: int):
    checkpoint = {
        "ai_id": ai_id,
        "output_file": output_file,
        "last_timestamp": last_timestamp,
        "message_count": message_count,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
    }

    CHECKPOINT_FILE.write_text(
        json.dumps(checkpoint, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def request_page_with_backoff(headers, params):
    """
    Makes a GET request while respecting rate limits.

    If Kindroid returns 429:
    - Uses Retry-After header if present
    - Otherwise uses exponential backoff with jitter
    """

    delay = 10
    max_delay = 300

    while True:
        response = requests.get(
            BASE_URL,
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

        if response.status_code == 401:
            raise RuntimeError(
                "Unauthorized. Your API key was rejected. "
                "Check that it starts with kn_ and was copied correctly."
            )

        if response.status_code == 403:
            raise RuntimeError(
                "Forbidden. The API key is valid, but this request is not allowed. "
                "Check that the AI ID belongs to this account."
            )

        if response.status_code == 400:
            raise RuntimeError(
                f"Bad request. Check your AI ID.\n\nServer said:\n{response.text}"
            )

        raise RuntimeError(
            f"Unexpected error: HTTP {response.status_code}\n\nServer said:\n{response.text}"
        )


def export_ai_messages(api_key: str, ai_id: str, output_file: Path, resume: bool = True):
    headers = {
        "Authorization": f"Bearer {api_key}",
    }

    all_messages = []
    start_after_timestamp = None

    if resume:
        checkpoint = load_checkpoint(ai_id)

        if checkpoint:
            previous_file = Path(checkpoint["output_file"])

            if previous_file.exists():
                print()
                print("Found a previous checkpoint for this AI.")
                print(f"Previous output file: {previous_file}")
                print(f"Messages already saved: {checkpoint.get('message_count', 0)}")
                print(f"Last timestamp: {checkpoint.get('last_timestamp')}")

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
        params = {
            "ai_id": ai_id,
            "limit": MAX_LIMIT,
        }

        if start_after_timestamp is not None:
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

        save_checkpoint(
            ai_id=ai_id,
            output_file=str(output_file),
            last_timestamp=last_timestamp,
            message_count=len(all_messages),
        )

        print(f"Fetched {len(messages)} messages.")
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
        # Increase this if Kindroid is still hitting you with 429s constantly.
        sleep_for = random.uniform(2.0, 5.0)
        print(f"Waiting {sleep_for:.1f} seconds before the next page...")
        time.sleep(sleep_for)

    return all_messages


def main():
    print("Kindroid Chat Exporter")
    print("======================")
    print()
    print("This exports messages for one Kindroid AI using your kn_ API key.")
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

    ai_id = prompt_nonempty("Enter the AI ID to export: ")

    default_name = f"kindroid_export_{safe_filename(ai_id)}.json"
    output_input = input(f"Output file [{default_name}]: ").strip()
    output_file = Path(output_input or default_name)

    print()
    print("Starting export.")
    print(f"AI ID: {ai_id}")
    print(f"Output file: {output_file}")
    print()

    try:
        messages = export_ai_messages(
            api_key=api_key,
            ai_id=ai_id,
            output_file=output_file,
            resume=True,
        )

        print()
        print(f"Saved {len(messages)} messages to:")
        print(output_file.resolve())

        if CHECKPOINT_FILE.exists():
            cleanup = input("Delete checkpoint file now that export is complete? [Y/n]: ").strip().lower()
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