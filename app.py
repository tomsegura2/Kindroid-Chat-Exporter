#!/usr/bin/env python3
"""
Kindroid Chat Exporter

Exports all messages for one or more Kindroid AIs or group chats using
the official /get-chat-messages endpoint.

Features:
- API key entered once per session; reused for all exports
- Main menu loop: export as many AIs or groups as needed, then quit
- Session summary: lists every completed export with message counts
- Explicitly requests the maximum page size of 100 (API default is 50)
- Handles 429 rate limits with Retry-After support and exponential backoff
- Retries on transient 5xx server errors with exponential backoff
- Saves a checkpoint after every successful page
- Resumes from the last saved timestamp if interrupted
- Writes a clean JSON export file per AI / group, named
  {CharName}_Chat_Export_YYYYMMDD.json (e.g. Lisa_Chat_Export_20260604.json)
- For single-AI exports only, can add missing display_name values locally
  (for example, "Lisa" for AI messages) when the API omits them

Message fields exported (fields absent on a given message are omitted):
  display_name, id, sender, sender_type, timestamp, message,
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def print_header():
    print()
    print("Kindroid Chat Exporter")
    print("======================")


def print_divider():
    print()
    print("──────────────────────────────────────────")


def prompt_nonempty(prompt_text: str) -> str:
    while True:
        value = input(prompt_text).strip()
        if value:
            return value
        print("  Please enter a value.")


def safe_filename(value: str) -> str:
    return "".join(
        c if (c.isalnum() or c in ("-", "_")) else "_"
        for c in value
    )


def reorder_message_fields(message: dict) -> dict:
    """
    Return a copy of message with display_name moved to the first position,
    followed by all remaining fields in their original order.
    Fields other than display_name are untouched whether or not it is present.
    """
    reordered = {}
    if "display_name" in message:
        reordered["display_name"] = message["display_name"]
    for key, value in message.items():
        if key != "display_name":
            reordered[key] = value
    return reordered


def add_single_ai_display_names(
    messages: list,
    character_name: str = "",
    user_name: str = "",
) -> int:
    """
    Add missing display_name values for one-on-one AI exports only.

    The Kindroid API schema allows display_name, but some single-chat exports
    omit it and only return sender values like "ai" or "user". This helper
    fills in the missing display_name locally without overwriting official values
    that the API may provide now or in the future.

    Group chats should not use this helper because sender="ai" is ambiguous
    when multiple characters can participate.
    """
    added_count = 0

    for message in messages:
        if not isinstance(message, dict):
            continue

        if message.get("display_name"):
            continue

        sender = message.get("sender")

        if sender == "ai" and character_name:
            message["display_name"] = character_name
            added_count += 1

        elif sender == "user" and user_name:
            message["display_name"] = user_name
            added_count += 1

    return added_count


# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------

def load_checkpoint(identifier: str):
    """
    Return the checkpoint dict for identifier, or None if absent / mismatched.
    Supports both old (ai_id-keyed) and new (identifier-keyed) checkpoint files.
    """
    if not CHECKPOINT_FILE.exists():
        return None

    try:
        checkpoint = json.loads(CHECKPOINT_FILE.read_text(encoding="utf-8"))
    except Exception:
        print("  Checkpoint file exists but could not be read. Ignoring it.")
        return None

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
    """Persist pagination state so an export can be resumed after interruption."""
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


def cleanup_checkpoint():
    """Delete the checkpoint file if it exists, after confirming with the user."""
    if CHECKPOINT_FILE.exists():
        choice = (
            input("  Delete checkpoint file now that export is complete? [Y/n]: ")
            .strip()
            .lower()
        )
        if choice in ("", "y", "yes"):
            CHECKPOINT_FILE.unlink()
            print("  Checkpoint deleted.")


# ---------------------------------------------------------------------------
# HTTP layer
# ---------------------------------------------------------------------------

def request_page_with_backoff(headers: dict, params: dict) -> dict:
    """
    GET /get-chat-messages with automatic retry on rate limits and server errors.

    Retry behaviour:
      429  — waits for Retry-After (if provided) or uses exponential backoff
      5xx  — uses exponential backoff (transient server-side errors)
      4xx  — raises immediately (caller error; retrying will not help)
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
            print(f"  Rate limited. Pausing for {sleep_for:.1f} seconds...")
            print("  Progress is saved; this can safely take its time.")
            time.sleep(sleep_for)
            delay = min(delay * 2, max_delay)
            continue

        if response.status_code in RETRYABLE_STATUS_CODES:
            sleep_for = delay + random.uniform(0, 3)
            print()
            print(
                f"  Server error {response.status_code}. "
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
                "Check that the AI ID (or group ID) belongs to this account and that "
                "your subscription level permits the requested resource."
            )

        if response.status_code == 400:
            raise RuntimeError(
                f"Bad request. Check your AI ID or group ID.\n\nServer said:\n{response.text}"
            )

        raise RuntimeError(
            f"Unexpected error: HTTP {response.status_code}\n\nServer said:\n{response.text}"
        )


# ---------------------------------------------------------------------------
# Core export logic
# ---------------------------------------------------------------------------

def export_messages(
    api_key: str,
    identifier: str,
    id_type: str,
    output_file: Path,
    resume: bool = True,
    character_name: str = "",
    user_name: str = "",
) -> int:
    """
    Paginate through /get-chat-messages and write every message to output_file.

    Returns the total number of messages exported.

    identifier     : the value of ai_id or group_id
    id_type        : "ai_id" or "group_id"
    character_name : optional local display_name for AI messages; only used
                     when id_type is "ai_id"
    user_name      : optional local display_name for user messages; only used
                     when id_type is "ai_id"
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    all_messages: list = []
    start_after_timestamp = None

    if resume:
        checkpoint = load_checkpoint(identifier)
        if checkpoint:
            previous_file = Path(checkpoint["output_file"])
            if previous_file.exists():
                print()
                print("  Found a previous checkpoint for this export.")
                print(f"  Previous output file  : {previous_file}")
                print(f"  Messages already saved: {checkpoint.get('message_count', 0)}")
                print(f"  Last timestamp        : {checkpoint.get('last_timestamp')}")

                choice = input("  Resume from this checkpoint? [Y/n]: ").strip().lower()
                if choice in ("", "y", "yes"):
                    output_file = previous_file
                    start_after_timestamp = checkpoint.get("last_timestamp")
                    try:
                        all_messages = json.loads(
                            output_file.read_text(encoding="utf-8")
                        )
                        if id_type == "ai_id":
                            added_names = add_single_ai_display_names(
                                all_messages,
                                character_name=character_name,
                                user_name=user_name,
                            )
                            if added_names:
                                output_file.write_text(
                                    json.dumps(
                                        [reorder_message_fields(m) for m in all_messages],
                                        indent=2,
                                        ensure_ascii=False,
                                    ),
                                    encoding="utf-8",
                                )
                                print(
                                    f"  Added missing display_name to {added_names} "
                                    "previously saved messages."
                                )
                    except Exception:
                        print("  Could not read previous output file. Starting fresh.")
                        all_messages = []
                        start_after_timestamp = None
                else:
                    print("  Starting a fresh export.")

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

        print(f"  Fetching page {page_number}...", end="", flush=True)

        data = request_page_with_backoff(headers, params)

        messages = data.get("messages", [])
        pagination = data.get("pagination", {})

        if not isinstance(messages, list):
            raise RuntimeError("Unexpected response: 'messages' was not a list.")

        added_names = 0
        if id_type == "ai_id":
            added_names = add_single_ai_display_names(
                messages,
                character_name=character_name,
                user_name=user_name,
            )

        all_messages.extend(messages)

        output_file.write_text(
            json.dumps(
                [reorder_message_fields(m) for m in all_messages],
                indent=2,
                ensure_ascii=False,
            ),
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

        name_note = (
            f" Added display_name to {added_names}."
            if added_names
            else ""
        )
        print(
            f" {len(messages)} messages fetched "
            f"(API page limit: {returned_limit}). "
            f"Total: {len(all_messages)}."
            f"{name_note}"
        )

        if not has_more:
            print()
            print(f"  Export complete — {len(all_messages)} messages saved to {output_file}.")
            break

        if last_timestamp is None:
            raise RuntimeError(
                "Kindroid said there are more messages but did not return lastTimestamp."
            )

        start_after_timestamp = last_timestamp
        page_number += 1

        # Gentle pacing even when not rate-limited.
        # Increase this if Kindroid is still hitting you with 429s.
        sleep_for = random.uniform(2.0, 5.0)
        print(f"  Waiting {sleep_for:.1f}s before next page...")
        time.sleep(sleep_for)

    return len(all_messages)


# ---------------------------------------------------------------------------
# Menu actions
# ---------------------------------------------------------------------------

def run_export(api_key: str, session_log: list):
    """
    Prompt for a single AI or group export, run it, and append the result
    to session_log as a dict with keys: id_type, identifier, output_file,
    message_count, status.
    """
    print_divider()
    print()
    print("  Export type:")
    print("    1) Single AI  (ai_id)")
    print("    2) Group chat (group_id)")
    export_type = input("  Choose [1/2, default 1]: ").strip()

    character_name = ""
    user_name = ""

    if export_type == "2":
        id_type = "group_id"
        identifier = prompt_nonempty("  Enter the group ID to export: ")
        character_name = ""
        user_name = ""
        date_str = datetime.now().strftime("%Y%m%d")
        default_name = f"Group_{safe_filename(identifier)}_Chat_Export_{date_str}.json"
    else:
        id_type = "ai_id"
        identifier = prompt_nonempty("  Enter the AI ID to export: ")
        print()
        print("  Single-AI display-name enrichment")
        print("  These names are added only when the API omits display_name.")
        character_name = prompt_nonempty(
            "  Enter the character name for AI messages: "
        )
        user_name = input("  Enter your display name for user messages [User]: "
                         ).strip() or "User"
        date_str = datetime.now().strftime("%Y%m%d")
        default_name = f"{safe_filename(character_name)}_Chat_Export_{date_str}.json"

    output_input = input(f"  Output file [{default_name}]: ").strip()
    output_file = Path(output_input or default_name)

    label = "Group ID" if id_type == "group_id" else "AI ID"
    print()
    print(f"  {label}    : {identifier}")
    if id_type == "ai_id":
        print(f"  Character: {character_name}")
        print(f"  User name: {user_name}")
    print(f"  Output file: {output_file}")
    print()

    entry = {
        "id_type": id_type,
        "identifier": identifier,
        "output_file": str(output_file),
        "message_count": 0,
        "status": "failed",
    }

    try:
        count = export_messages(
            api_key=api_key,
            identifier=identifier,
            id_type=id_type,
            output_file=output_file,
            resume=True,
            character_name=character_name,
            user_name=user_name,
        )
        entry["message_count"] = count
        entry["status"] = "ok"
        cleanup_checkpoint()

    except KeyboardInterrupt:
        print()
        print("  Export interrupted. Progress is saved; return to menu to resume.")
        entry["status"] = "interrupted"

    except Exception as exc:
        print()
        print("  Export failed:")
        print(f"  {exc}")
        print()
        print(f"  Progress may still be saved in: {CHECKPOINT_FILE.resolve()}")
        entry["status"] = "failed"

    finally:
        session_log.append(entry)


def show_session_summary(session_log: list):
    """Print a table of all exports attempted in this session."""
    print_divider()
    print()
    if not session_log:
        print("  No exports were run this session.")
        return

    print("  Session summary:")
    print()
    col_w = max(len(e["identifier"]) for e in session_log) + 2
    print(f"  {'ID':<{col_w}}  {'Type':<10}  {'Messages':>9}  {'Status':<12}  Output file")
    print(f"  {'-'*col_w}  {'-'*10}  {'-'*9}  {'-'*12}  -----------")
    for e in session_log:
        print(
            f"  {e['identifier']:<{col_w}}  "
            f"{e['id_type']:<10}  "
            f"{e['message_count']:>9}  "
            f"{e['status']:<12}  "
            f"{e['output_file']}"
        )
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    print_header()
    print()
    print("  Exports messages for Kindroid AIs and group chats.")
    print("  Your API key is used only in this session and is never saved.")
    print()

    # --- API key (once per session) ----------------------------------------
    api_key = getpass.getpass("  Enter your Kindroid API key (starts with kn_): ").strip()

    if not api_key.startswith("kn_"):
        print()
        print("  Warning: that does not look like a Kindroid kn_ API key.")
        choice = input("  Continue anyway? [y/N]: ").strip().lower()
        if choice not in ("y", "yes"):
            print("  Canceled.")
            return

    # --- Main menu loop -----------------------------------------------------
    session_log: list = []

    while True:
        print_divider()
        print()
        print("  Main menu")
        print("    1) Export an AI or group chat")
        print("    2) View session summary")
        print("    3) Quit")
        print()
        choice = input("  Choose [1/2/3]: ").strip()

        if choice == "1":
            run_export(api_key, session_log)

        elif choice == "2":
            show_session_summary(session_log)

        elif choice in ("3", "q", "quit", "exit", ""):
            show_session_summary(session_log)
            print("  Goodbye.")
            break

        else:
            print("  Unrecognised option. Please enter 1, 2, or 3.")


if __name__ == "__main__":
    main()