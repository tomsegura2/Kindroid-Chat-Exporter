#!/usr/bin/env python3
"""
Kindroid Chat Exporter

Exports all messages for one or more Kindroid AIs or group chats using
the official /get-chat-messages endpoint.

Features:
- Beginner-friendly prompts with plain-English instructions and where-to-find hints
- API key entered once per session; reused for all exports
- Main menu loop: export as many AIs or groups as needed, then exit
- Confirmation prompt before each export starts
- Animated progress line: "Downloading your chat history... (400 messages so far)"
- Warm completion message with final message count and file location
- Session summary with friendly labels (✓ Done / ⏸ Paused / ✗ Failed)
- Explicitly requests the maximum page size of 100 (API default is 50)
- Handles 429 rate limits with Retry-After support and exponential backoff
- Retries on transient 5xx server errors with exponential backoff
- Plain-English error messages for all failure modes
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

Install dependencies:
    pip install requests
    pip install reportlab  # only needed for PDF conversion

Run:
    python app.py
"""

import json
import time
import random
import getpass
import sys
from xml.sax.saxutils import escape
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


def configure_console_encoding():
    """Avoid UnicodeEncodeError in packaged Windows console builds."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


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
            print(f"  Kindroid has asked us to slow down. Pausing for {sleep_for:.1f} seconds...")
            print("  Your progress is saved — no need to do anything, just wait.")
            time.sleep(sleep_for)
            delay = min(delay * 2, max_delay)
            continue

        if response.status_code in RETRYABLE_STATUS_CODES:
            sleep_for = delay + random.uniform(0, 3)
            print()
            print(
                f"  Kindroid's server hit a snag. "
                f"Trying again in {sleep_for:.1f} seconds — your progress is safe."
            )
            time.sleep(sleep_for)
            delay = min(delay * 2, max_delay)
            continue

        if response.status_code == 401:
            raise RuntimeError(
                "Your API key was not recognised by Kindroid.\n"
                "  • Make sure it starts with kn_\n"
                "  • Copy it again from Kindroid → Profile → Settings\n"
                "  • Check there are no extra spaces before or after it"
            )

        if response.status_code == 403:
            raise RuntimeError(
                "Kindroid won't allow this export.\n"
                "  • Make sure the AI ID (or group ID) belongs to your account\n"
                "  • Group chat exports may require a paid Kindroid subscription"
            )

        if response.status_code == 400:
            raise RuntimeError(
                "Kindroid didn't understand the request — the AI ID or group ID "
                "may be incorrect.\n"
                "  • Copy it again from Kindroid → Profile → Settings\n"
                f"  • Details: {response.text}"
            )

        raise RuntimeError(
            f"Something unexpected went wrong (server returned code {response.status_code}).\n"
            "  • Check your internet connection and try again\n"
            "  • Your progress has been saved and the export can be resumed\n"
            f"  • Details: {response.text}"
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
                print("  It looks like a previous export was interrupted partway through.")
                print(f"  File       : {previous_file}")
                print(f"  Saved so far: {checkpoint.get('message_count', 0):,} messages")

                choice = input("  Pick up where it left off? [Y/n]: ").strip().lower()
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

        print(
            f"\r  Downloading your chat history... ({len(all_messages):,} messages so far)  ",
            end="",
            flush=True,
        )

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

        if not has_more:
            print()
            print()
            print(f"  🎉 All done! Saved {len(all_messages):,} messages to {output_file}")
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
        time.sleep(sleep_for)

    return len(all_messages)


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------

def load_exported_messages(input_file: Path) -> list:
    """Read an exported Kindroid JSON file and return its message list."""
    try:
        data = json.loads(input_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{input_file} is not valid JSON: {exc}") from exc

    if not isinstance(data, list):
        raise ValueError(f"{input_file} must contain a JSON array of messages.")

    for index, message in enumerate(data, start=1):
        if not isinstance(message, dict):
            raise ValueError(
                f"{input_file} contains a non-object message at position {index}."
            )

    return data


def format_timestamp(value) -> str:
    """Return a readable timestamp while preserving unknown timestamp values."""
    if value in (None, ""):
        return ""

    try:
        timestamp = float(value)
    except (TypeError, ValueError):
        return str(value)

    if timestamp > 10_000_000_000:
        timestamp = timestamp / 1000

    try:
        return datetime.fromtimestamp(timestamp).isoformat(sep=" ", timespec="seconds")
    except (OSError, OverflowError, ValueError):
        return str(value)


def format_pdf_timestamp(value) -> str:
    """Return timestamps as M/D/YY HH:MM for PDF chat lines."""
    if value in (None, ""):
        return ""

    try:
        timestamp = float(value)
    except (TypeError, ValueError):
        return str(value)

    if timestamp > 10_000_000_000:
        timestamp = timestamp / 1000

    try:
        dt = datetime.fromtimestamp(timestamp)
    except (OSError, OverflowError, ValueError):
        return str(value)

    return f"{dt.month}/{dt.day}/{dt.strftime('%y %H:%M')}"


def message_author(message: dict) -> str:
    return (
        message.get("display_name")
        or message.get("sender")
        or message.get("sender_type")
        or "Unknown"
    )


def message_text(message: dict) -> str:
    parts = []

    text = message.get("message")
    if text:
        parts.append(str(text))

    for field, label in (
        ("image_urls", "Images"),
        ("image_description", "Image description"),
        ("video_description", "Video description"),
        ("internet_response", "Internet response"),
        ("link_url", "Link"),
        ("link_description", "Link description"),
    ):
        value = message.get(field)
        if not value:
            continue
        if isinstance(value, list):
            value = ", ".join(str(item) for item in value)
        parts.append(f"{label}: {value}")

    return "\n".join(parts)


def export_as_jsonl(messages: list, output_file: Path):
    lines = [
        json.dumps(reorder_message_fields(message), ensure_ascii=False)
        for message in messages
    ]
    output_file.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def export_as_plaintext(messages: list, output_file: Path):
    blocks = []
    for message in messages:
        timestamp = format_timestamp(message.get("timestamp"))
        author = message_author(message)
        header = f"[{timestamp}] {author}" if timestamp else author
        body = message_text(message)
        blocks.append(f"{header}\n{body}" if body else header)

    output_file.write_text("\n\n".join(blocks) + ("\n" if blocks else ""), encoding="utf-8")


def escape_markdown_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|")


def export_as_markdown(messages: list, output_file: Path, title: str):
    lines = [f"# {title}", ""]
    for message in messages:
        timestamp = format_timestamp(message.get("timestamp"))
        author = escape_markdown_text(str(message_author(message)))
        heading = f"## {author}"
        if timestamp:
            heading += f" - {escape_markdown_text(timestamp)}"

        lines.append(heading)
        lines.append("")

        body = message_text(message)
        lines.append(body if body else "_No message text_")
        lines.append("")

    output_file.write_text("\n".join(lines), encoding="utf-8")


def export_as_pdf(messages: list, output_file: Path, title: str):
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    except ImportError as exc:
        raise RuntimeError(
            "PDF conversion requires reportlab. Install it with: pip install reportlab"
        ) from exc

    page_width, page_height = letter
    background_hex = "#000000"
    text_hex = "#FBEDED"
    muted_hex = "#CBCBCB"
    accent_hex = "#C380A0"
    background_color = colors.HexColor(background_hex)
    text_color = colors.HexColor(text_hex)

    def paint_background(canvas, _doc):
        canvas.saveState()
        canvas.setFillColor(background_color)
        canvas.rect(0, 0, page_width, page_height, stroke=0, fill=1)
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(output_file),
        pagesize=letter,
        rightMargin=0.65 * inch,
        leftMargin=0.65 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.65 * inch,
        title=title,
        author="Kindroid Chat Exporter",
    )

    base_styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "KindroidTitle",
        parent=base_styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        textColor=text_color,
        alignment=TA_LEFT,
        spaceAfter=14,
    )
    message_style = ParagraphStyle(
        "KindroidMessage",
        parent=base_styles["BodyText"],
        fontName="Helvetica",
        fontSize=10.5,
        leading=14,
        textColor=text_color,
        spaceAfter=7,
    )

    story = [Paragraph(escape(title), title_style)]

    for message in messages:
        author = escape(str(message_author(message)))
        timestamp = escape(format_pdf_timestamp(message.get("timestamp")))
        body = escape(message_text(message) or "")
        body = body.replace("\n", "<br/>")

        prefix = f'<font color="{accent_hex}"><b>{author}</b></font>'
        if timestamp:
            prefix += f' <font color="{muted_hex}">({timestamp})</font>'

        text = f"{prefix}: {body}" if body else prefix
        story.append(Paragraph(text, message_style))
        story.append(Spacer(1, 0.03 * inch))

    doc.build(story, onFirstPage=paint_background, onLaterPages=paint_background)


def convert_export_file(input_file: Path, formats: list) -> list:
    messages = load_exported_messages(input_file)
    written = []

    for output_format in formats:
        if output_format == "jsonl":
            output_file = input_file.with_suffix(".jsonl")
            export_as_jsonl(messages, output_file)
        elif output_format == "txt":
            output_file = input_file.with_suffix(".txt")
            export_as_plaintext(messages, output_file)
        elif output_format == "md":
            output_file = input_file.with_suffix(".md")
            export_as_markdown(messages, output_file, input_file.stem)
        elif output_format == "pdf":
            output_file = input_file.with_suffix(".pdf")
            export_as_pdf(messages, output_file, input_file.stem)
        else:
            raise ValueError(f"Unsupported format: {output_format}")

        written.append(output_file)

    return written


# ---------------------------------------------------------------------------
# Menu actions
# ---------------------------------------------------------------------------

def run_export(api_key: str, session_log: list):
    """
    Prompt for a single AI or group export, run it, and append the result
    to session_log.
    """
    print_divider()
    print()
    print("  What would you like to export?")
    print("    1) Chat with a single AI")
    print("    2) Group chat")
    export_type = input("  Choose [1/2, default 1]: ").strip()

    character_name = ""
    user_name = ""

    if export_type == "2":
        id_type = "group_id"
        print()
        print("  Your group ID can be found in the Kindroid app under Profile → Settings.")
        identifier = prompt_nonempty("  Enter the group ID: ")
        character_name = ""
        user_name = ""
        date_str = datetime.now().strftime("%Y%m%d")
        default_name = f"Group_{safe_filename(identifier)}_Chat_Export_{date_str}.json"
    else:
        id_type = "ai_id"
        print()
        print("  Your AI ID can be found in the Kindroid app under Profile → Settings.")
        identifier = prompt_nonempty("  Enter the AI ID: ")
        print()
        character_name = prompt_nonempty(
            "  What is your AI's name? (e.g. Lisa): "
        )
        user_name = input(
            "  What name should your messages use? [User]: "
        ).strip() or "User"
        date_str = datetime.now().strftime("%Y%m%d")
        default_name = f"{safe_filename(character_name)}_Chat_Export_{date_str}.json"

    output_file = Path(default_name)

    # Confirmation before starting
    print()
    if id_type == "ai_id":
        print(f"  Ready to export {character_name}'s chat to:  {output_file}")
    else:
        print(f"  Ready to export group chat to:  {output_file}")
    input("  Press Enter to start, or Ctrl+C to cancel...")
    print()

    entry = {
        "id_type": id_type,
        "identifier": identifier,
        "character_name": character_name or identifier,
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
        print("  Export paused. Your progress has been saved automatically.")
        print("  Just run the script again and choose the same AI to pick up where you left off.")
        entry["status"] = "interrupted"

    except Exception as exc:
        print()
        print("  Something went wrong during the export:")
        print()
        for line in str(exc).splitlines():
            print(f"  {line}")
        print()
        print("  Your progress up to this point has been saved.")
        print("  Try running the script again — it should be able to resume.")
        entry["status"] = "failed"

    finally:
        session_log.append(entry)


def run_conversion():
    """Convert one exported JSON file, or every exported JSON file in a folder."""
    print_divider()
    print()
    print("  Convert your downloaded chat exports to another format.")
    print()
    source_input = input("  Path to JSON file or folder [current folder]: ").strip()
    source = Path(source_input or ".")

    print()
    print("  What format would you like?")
    print("    1) JSON Lines (.jsonl)  — one message per line, good for importing into other tools")
    print("    2) Plain text  (.txt)   — simple, readable in any text editor")
    print("    3) Markdown    (.md)    — formatted, good for note-taking apps like Obsidian")
    print("    4) PDF         (.pdf)   — nicely formatted, easy to print or share")
    print("    5) All of the above")
    format_choice = input("  Choose [1/2/3/4/5, default 5]: ").strip()

    format_map = {
        "1": ["jsonl"],
        "2": ["txt"],
        "3": ["md"],
        "4": ["pdf"],
        "5": ["jsonl", "txt", "md", "pdf"],
        "": ["jsonl", "txt", "md", "pdf"],
    }
    formats = format_map.get(format_choice)
    if formats is None:
        print("  Unrecognised option — please enter a number between 1 and 5.")
        return

    if source.is_dir():
        input_files = sorted(
            file
            for file in source.glob("*.json")
            if file.name != CHECKPOINT_FILE.name
        )
    else:
        input_files = [source]

    if not input_files:
        print("  No exported JSON files were found in that location.")
        return

    converted_count = 0
    for input_file in input_files:
        if not input_file.exists():
            print(f"  Skipped (file not found): {input_file}")
            continue

        try:
            written = convert_export_file(input_file, formats)
        except Exception as exc:
            print(f"  Could not convert {input_file.name}: {exc}")
            continue

        converted_count += 1
        print(f"  ✓ Converted {input_file.name}:")
        for output_file in written:
            print(f"      → {output_file}")

    print()
    if converted_count:
        print(f"  🎉 Done! Converted {converted_count} file(s).")
    else:
        print("  No files were converted. Check the path and try again.")


def show_session_summary(session_log: list):
    """Print a table of all exports attempted in this session."""
    print_divider()
    print()
    if not session_log:
        print("  No exports were run this session.")
        return

    status_labels = {
        "ok":          "✓ Done",
        "interrupted": "⏸ Paused",
        "failed":      "✗ Failed",
    }

    print("  Session summary:")
    print()
    name_col = max(len(e.get("character_name") or e["identifier"]) for e in session_log) + 2
    print(f"  {'Name':<{name_col}}  {'Type':<12}  {'Messages':>9}  {'Result':<12}  File")
    print(f"  {'-'*name_col}  {'-'*12}  {'-'*9}  {'-'*12}  ----")
    for e in session_log:
        name = e.get("character_name") or e["identifier"]
        kind = "Group chat" if e["id_type"] == "group_id" else "Single AI"
        status = status_labels.get(e["status"], e["status"])
        print(
            f"  {name:<{name_col}}  "
            f"{kind:<12}  "
            f"{e['message_count']:>9,}  "
            f"{status:<12}  "
            f"{e['output_file']}"
        )
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    configure_console_encoding()
    print_header()
    print()
    print("  Save your Kindroid chat history to your computer.")
    print()
    print("  Before you start, you'll need two things from the Kindroid app:")
    print("    • Your API key  — found in Profile → Settings → API Key")
    print("    • Your AI's ID  — found in Profile → Settings → AI ID")
    print()
    print("  Your progress is saved automatically, so it's safe to close")
    print("  the window at any time and pick up where you left off.")
    print()

    session_log: list = []
    api_key = ""

    while True:
        print_divider()
        print()
        print("  Main menu")
        print("    1) Download a chat export")
        print("    2) Convert a downloaded export to PDF, text, or Markdown")
        print("    3) View this session's exports")
        print("    4) Exit")
        print()
        choice = input("  Choose [1/2/3/4]: ").strip()

        if choice == "1":
            if not api_key:
                print()
                print("  Your API key can be found in the Kindroid app:")
                print("  Profile → Settings → API Key")
                print("  It starts with kn_ and stays on your computer — it is never uploaded.")
                print()
                print("  How would you like to enter your API key?")
                print("    1) Hidden  — characters are invisible as you type (more secure)")
                print("    2) Visible — characters appear as you type (easier to check for typos)")
                print()
                visibility_choice = input("  Choose [1/2, default 1]: ").strip()
                print()

                if visibility_choice == "2":
                    api_key = input("  Paste your API key here: ").strip()
                    if api_key:
                        print(f"  Key entered successfully ({len(api_key)} characters).")
                else:
                    api_key = getpass.getpass(
                        "  Paste your API key here (it won't be visible as you type): "
                    ).strip()

                if not api_key.startswith("kn_"):
                    print()
                    print("  That doesn't look like a Kindroid API key (should start with kn_).")
                    confirm = input("  Continue anyway? [y/N]: ").strip().lower()
                    if confirm not in ("y", "yes"):
                        print("  Canceled — go back to the Kindroid app and copy the key again.")
                        api_key = ""
                        continue

            run_export(api_key, session_log)

        elif choice == "2":
            run_conversion()

        elif choice == "3":
            show_session_summary(session_log)

        elif choice in ("4", ""):
            show_session_summary(session_log)
            print("  Goodbye!")
            break

        else:
            print("  Please enter 1, 2, 3, or 4.")


if __name__ == "__main__":
    main()
