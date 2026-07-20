#!/usr/bin/env python3
"""Tkinter GUI for Kindroid Chat Exporter."""

from __future__ import annotations

import queue
import threading
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import app

JSON_GLOB_PATTERN = "*.json"
JSON_FILETYPES = [("JSON files", JSON_GLOB_PATTERN), ("All files", "*.*")]


class KindroidExporterGui(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Kindroid Chat Exporter")
        self.geometry("980x720")
        self.minsize(860, 620)

        self.events: queue.Queue = queue.Queue()
        self.session_log: list[dict] = []
        self.worker: threading.Thread | None = None

        self._build_variables()
        self._build_ui()
        self._poll_events()

    def _build_variables(self):
        self.api_key_var = tk.StringVar()
        self.show_key_var = tk.BooleanVar(value=False)
        self.export_type_var = tk.StringVar(value="ai_id")
        self.identifier_var = tk.StringVar()
        self.character_name_var = tk.StringVar()
        self.group_export_name_var = tk.StringVar()
        self.user_name_var = tk.StringVar(value="User")
        self.output_file_var = tk.StringVar()
        self.resume_var = tk.BooleanVar(value=True)
        self.delete_checkpoint_var = tk.BooleanVar(value=True)

        self.source_var = tk.StringVar(value=str(Path.cwd()))
        self.format_vars = {
            "jsonl": tk.BooleanVar(value=True),
            "txt": tk.BooleanVar(value=True),
            "md": tk.BooleanVar(value=True),
            "pdf": tk.BooleanVar(value=True),
        }

    def _build_ui(self):
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True)

        self.export_tab = ttk.Frame(self.notebook, padding=12)
        self.convert_tab = ttk.Frame(self.notebook, padding=12)
        self.summary_tab = ttk.Frame(self.notebook, padding=12)

        self.notebook.add(self.export_tab, text="Download Export")
        self.notebook.add(self.convert_tab, text="Convert Files")
        self.notebook.add(self.summary_tab, text="Session Summary")

        self._build_export_tab()
        self._build_convert_tab()
        self._build_summary_tab()

    def _build_export_tab(self):
        self.export_tab.columnconfigure(1, weight=1)
        row = 0

        ttk.Label(self.export_tab, text="API key").grid(row=row, column=0, sticky="w", pady=4)
        self.api_key_entry = ttk.Entry(self.export_tab, textvariable=self.api_key_var, show="*")
        self.api_key_entry.grid(row=row, column=1, sticky="ew", pady=4)
        ttk.Checkbutton(
            self.export_tab,
            text="Show",
            variable=self.show_key_var,
            command=self._toggle_api_key_visibility,
        ).grid(row=row, column=2, sticky="w", padx=(8, 0), pady=4)
        row += 1

        type_frame = ttk.Frame(self.export_tab)
        type_frame.grid(row=row, column=1, sticky="w", pady=4)
        ttk.Label(self.export_tab, text="Export type").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Radiobutton(
            type_frame,
            text="Single AI",
            value="ai_id",
            variable=self.export_type_var,
            command=self._update_export_type,
        ).pack(side="left")
        ttk.Radiobutton(
            type_frame,
            text="Group chat",
            value="group_id",
            variable=self.export_type_var,
            command=self._update_export_type,
        ).pack(side="left", padx=(16, 0))
        row += 1

        ttk.Label(self.export_tab, text="AI ID / group ID").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(self.export_tab, textvariable=self.identifier_var).grid(row=row, column=1, sticky="ew", pady=4)
        row += 1

        self.character_label = ttk.Label(self.export_tab, text="AI display name")
        self.character_label.grid(row=row, column=0, sticky="w", pady=4)
        self.character_entry = ttk.Entry(self.export_tab, textvariable=self.character_name_var)
        self.character_entry.grid(row=row, column=1, sticky="ew", pady=4)
        row += 1

        self.group_export_name_label = ttk.Label(self.export_tab, text="Group export name")
        self.group_export_name_label.grid(row=row, column=0, sticky="w", pady=4)
        self.group_export_name_entry = ttk.Entry(self.export_tab, textvariable=self.group_export_name_var)
        self.group_export_name_entry.grid(row=row, column=1, sticky="ew", pady=4)
        row += 1

        self.user_label = ttk.Label(self.export_tab, text="Your display name")
        self.user_label.grid(row=row, column=0, sticky="w", pady=4)
        self.user_entry = ttk.Entry(self.export_tab, textvariable=self.user_name_var)
        self.user_entry.grid(row=row, column=1, sticky="ew", pady=4)
        row += 1

        ttk.Label(self.export_tab, text="Output JSON").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(self.export_tab, textvariable=self.output_file_var).grid(row=row, column=1, sticky="ew", pady=4)
        ttk.Button(self.export_tab, text="Browse", command=self._browse_output_file).grid(
            row=row, column=2, sticky="ew", padx=(8, 0), pady=4
        )
        row += 1

        options = ttk.Frame(self.export_tab)
        options.grid(row=row, column=1, sticky="w", pady=4)
        ttk.Checkbutton(options, text="Resume from checkpoint when available", variable=self.resume_var).pack(side="left")
        ttk.Checkbutton(options, text="Delete checkpoint after success", variable=self.delete_checkpoint_var).pack(
            side="left", padx=(16, 0)
        )
        row += 1

        buttons = ttk.Frame(self.export_tab)
        buttons.grid(row=row, column=1, sticky="w", pady=(10, 6))
        self.start_export_button = ttk.Button(buttons, text="Start Export", command=self._start_export)
        self.start_export_button.pack(side="left")
        ttk.Button(buttons, text="Clear Log", command=lambda: self._clear_text(self.export_log)).pack(
            side="left", padx=(8, 0)
        )
        row += 1

        self.export_status_var = tk.StringVar(value="Ready")
        ttk.Label(self.export_tab, textvariable=self.export_status_var).grid(row=row, column=0, columnspan=3, sticky="w")
        row += 1

        self.export_progress = ttk.Progressbar(self.export_tab, mode="indeterminate")
        self.export_progress.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(4, 8))
        row += 1

        self.export_log = tk.Text(self.export_tab, height=18, wrap="word")
        self.export_log.grid(row=row, column=0, columnspan=3, sticky="nsew")
        self.export_tab.rowconfigure(row, weight=1)

        self._update_export_type()

    def _build_convert_tab(self):
        self.convert_tab.columnconfigure(1, weight=1)
        row = 0

        ttk.Label(self.convert_tab, text="JSON file or folder").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(self.convert_tab, textvariable=self.source_var).grid(row=row, column=1, sticky="ew", pady=4)
        browse = ttk.Frame(self.convert_tab)
        browse.grid(row=row, column=2, sticky="ew", padx=(8, 0), pady=4)
        ttk.Button(browse, text="File", command=self._browse_source_file).pack(side="left")
        ttk.Button(browse, text="Folder", command=self._browse_source_folder).pack(side="left", padx=(6, 0))
        row += 1

        ttk.Label(self.convert_tab, text="Formats").grid(row=row, column=0, sticky="w", pady=4)
        formats = ttk.Frame(self.convert_tab)
        formats.grid(row=row, column=1, sticky="w", pady=4)
        for label, key in (("JSON Lines", "jsonl"), ("Text", "txt"), ("Markdown", "md"), ("PDF", "pdf")):
            ttk.Checkbutton(formats, text=label, variable=self.format_vars[key]).pack(side="left", padx=(0, 14))
        row += 1

        buttons = ttk.Frame(self.convert_tab)
        buttons.grid(row=row, column=1, sticky="w", pady=(10, 6))
        self.start_convert_button = ttk.Button(buttons, text="Convert", command=self._start_conversion)
        self.start_convert_button.pack(side="left")
        ttk.Button(buttons, text="Clear Log", command=lambda: self._clear_text(self.convert_log)).pack(
            side="left", padx=(8, 0)
        )
        row += 1

        self.convert_status_var = tk.StringVar(value="Ready")
        ttk.Label(self.convert_tab, textvariable=self.convert_status_var).grid(
            row=row, column=0, columnspan=3, sticky="w"
        )
        row += 1

        self.convert_progress = ttk.Progressbar(self.convert_tab, mode="indeterminate")
        self.convert_progress.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(4, 8))
        row += 1

        self.convert_log = tk.Text(self.convert_tab, height=22, wrap="word")
        self.convert_log.grid(row=row, column=0, columnspan=3, sticky="nsew")
        self.convert_tab.rowconfigure(row, weight=1)

    def _build_summary_tab(self):
        self.summary_tab.rowconfigure(0, weight=1)
        self.summary_tab.columnconfigure(0, weight=1)
        columns = ("name", "type", "messages", "result", "file")
        self.summary_tree = ttk.Treeview(self.summary_tab, columns=columns, show="headings")
        for column, label, width in (
            ("name", "Name", 170),
            ("type", "Type", 110),
            ("messages", "Messages", 90),
            ("result", "Result", 100),
            ("file", "File", 430),
        ):
            self.summary_tree.heading(column, text=label)
            self.summary_tree.column(column, width=width, anchor="w")
        self.summary_tree.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(self.summary_tab, orient="vertical", command=self.summary_tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.summary_tree.configure(yscrollcommand=scrollbar.set)

        ttk.Button(self.summary_tab, text="Refresh", command=self._refresh_summary).grid(
            row=1, column=0, sticky="w", pady=(8, 0)
        )

    def _toggle_api_key_visibility(self):
        self.api_key_entry.configure(show="" if self.show_key_var.get() else "*")

    def _update_export_type(self):
        is_single = self.export_type_var.get() == "ai_id"
        single_state = "normal" if is_single else "disabled"
        group_state = "disabled" if is_single else "normal"
        self.character_entry.configure(state=single_state)
        self.user_entry.configure(state=single_state)
        self.character_label.configure(state=single_state)
        self.user_label.configure(state=single_state)
        self.group_export_name_entry.configure(state=group_state)
        self.group_export_name_label.configure(state=group_state)

    def _browse_output_file(self):
        default = self._default_output_file()
        path = filedialog.asksaveasfilename(
            title="Save export as",
            initialfile=default.name,
            defaultextension=".json",
            filetypes=JSON_FILETYPES,
        )
        if path:
            self.output_file_var.set(path)

    def _browse_source_file(self):
        path = filedialog.askopenfilename(
            title="Select exported JSON",
            filetypes=JSON_FILETYPES,
        )
        if path:
            self.source_var.set(path)

    def _browse_source_folder(self):
        path = filedialog.askdirectory(title="Select folder containing exports")
        if path:
            self.source_var.set(path)

    def _default_output_file(self) -> Path:
        date_str = datetime.now().strftime("%Y%m%d")
        if self.export_type_var.get() == "group_id":
            identifier = self.identifier_var.get().strip() or "Group"
            group_name = self.group_export_name_var.get().strip()
            filename_name = group_name or f"Group_{identifier}"
            return Path(f"{app.safe_filename(filename_name)}_Chat_Export_{date_str}.json")
        name = self.character_name_var.get().strip() or "Kindroid"
        return Path(f"{app.safe_filename(name)}_Chat_Export_{date_str}.json")

    def _validate_export_form(self, api_key: str, identifier: str, id_type: str, character_name: str) -> bool:
        """Validate the export form fields, showing an error dialog for the first problem found."""
        if not api_key:
            messagebox.showerror("Missing API key", "Enter your Kindroid API key.")
            return False
        if not api_key.startswith("kn_") and not messagebox.askyesno(
            "API key check", "This key does not start with kn_. Continue anyway?"
        ):
            return False
        if not identifier:
            messagebox.showerror("Missing ID", "Enter the AI ID or group ID to export.")
            return False
        if id_type == "ai_id" and not character_name:
            messagebox.showerror("Missing AI name", "Enter the AI display name for single-AI exports.")
            return False
        return True

    def _maybe_prompt_resume(self, identifier: str) -> bool | None:
        """Ask the user whether to resume from an existing checkpoint, if one is found."""
        if not self.resume_var.get():
            return None
        checkpoint = app.load_checkpoint(identifier)
        if not checkpoint or not Path(checkpoint.get("output_file", "")).exists():
            return None
        return messagebox.askyesno(
            "Resume checkpoint",
            "A checkpoint exists for this ID.\n\n"
            f"File: {checkpoint.get('output_file')}\n"
            f"Saved messages: {checkpoint.get('message_count', 0):,}\n\n"
            "Resume from it?",
        )

    def _start_export(self):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Export running", "An export or conversion is already running.")
            return

        api_key = self.api_key_var.get().strip()
        identifier = self.identifier_var.get().strip()
        id_type = self.export_type_var.get()
        character_name = self.character_name_var.get().strip()
        group_export_name = self.group_export_name_var.get().strip()
        user_name = self.user_name_var.get().strip() or "User"

        if not self._validate_export_form(api_key, identifier, id_type, character_name):
            return

        output_file_text = self.output_file_var.get().strip()
        output_file = Path(output_file_text) if output_file_text else self._default_output_file()
        resume_choice = self._maybe_prompt_resume(identifier)

        entry = {
            "id_type": id_type,
            "identifier": identifier,
            "character_name": character_name if id_type == "ai_id" else group_export_name or identifier,
            "output_file": str(output_file),
            "message_count": 0,
            "status": "failed",
        }

        self._clear_text(self.export_log)
        self.export_progress.start(12)
        self.export_status_var.set("Starting export...")
        self.start_export_button.configure(state="disabled")

        self.worker = threading.Thread(
            target=self._export_worker,
            args=(
                api_key,
                identifier,
                id_type,
                output_file,
                character_name,
                user_name,
                self.resume_var.get(),
                resume_choice,
                self.delete_checkpoint_var.get(),
                entry,
            ),
            daemon=True,
        )
        self.worker.start()

    def _export_worker(
        self,
        api_key,
        identifier,
        id_type,
        output_file,
        character_name,
        user_name,
        resume_enabled,
        resume_choice,
        delete_checkpoint,
        entry,
    ):
        try:
            count = app.export_messages(
                api_key=api_key,
                identifier=identifier,
                id_type=id_type,
                output_file=output_file,
                resume=resume_enabled,
                character_name=character_name,
                user_name=user_name,
                resume_choice=resume_choice,
                cleanup_checkpoint_choice=delete_checkpoint,
                progress_callback=lambda count, text: self.events.put(("export_status", text)),
                log_callback=lambda text: self.events.put(("export_log", text)),
            )
            entry["message_count"] = count
            entry["status"] = "ok"
            self.events.put(("export_done", entry, None))
        except Exception as exc:
            entry["status"] = "failed"
            self.events.put(("export_done", entry, exc))

    def _start_conversion(self):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Work running", "An export or conversion is already running.")
            return

        formats = [key for key, var in self.format_vars.items() if var.get()]
        if not formats:
            messagebox.showerror("No formats selected", "Choose at least one output format.")
            return

        source = Path(self.source_var.get().strip() or ".")
        self._clear_text(self.convert_log)
        self.convert_progress.start(12)
        self.convert_status_var.set("Converting...")
        self.start_convert_button.configure(state="disabled")

        self.worker = threading.Thread(target=self._conversion_worker, args=(source, formats), daemon=True)
        self.worker.start()

    def _conversion_worker(self, source: Path, formats: list[str]):
        converted = 0
        try:
            if source.is_dir():
                input_files = sorted(
                    file for file in source.glob(JSON_GLOB_PATTERN) if file.name != app.CHECKPOINT_FILE.name
                )
            else:
                input_files = [source]

            if not input_files:
                self.events.put(("convert_log", "No exported JSON files were found."))
                self.events.put(("convert_done", converted, None))
                return

            for input_file in input_files:
                if not input_file.exists():
                    self.events.put(("convert_log", f"Skipped missing file: {input_file}"))
                    continue
                try:
                    written = app.convert_export_file(input_file, formats)
                except Exception as exc:
                    self.events.put(("convert_log", f"Could not convert {input_file.name}: {exc}"))
                    continue
                converted += 1
                self.events.put(("convert_log", f"Converted {input_file.name}:"))
                for output_file in written:
                    self.events.put(("convert_log", f"  -> {output_file}"))

            self.events.put(("convert_done", converted, None))
        except Exception as exc:
            self.events.put(("convert_done", converted, exc))

    def _poll_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "export_status":
                    self.export_status_var.set(event[1])
                elif kind == "export_log":
                    self._append_text(self.export_log, event[1])
                elif kind == "export_done":
                    self._handle_export_done(event[1], event[2])
                elif kind == "convert_log":
                    self._append_text(self.convert_log, event[1])
                elif kind == "convert_done":
                    self._handle_convert_done(event[1], event[2])
        except queue.Empty:
            pass
        self.after(100, self._poll_events)

    def _handle_export_done(self, entry: dict, exc: Exception | None):
        self.export_progress.stop()
        self.start_export_button.configure(state="normal")
        self.session_log.append(entry)
        self._refresh_summary()
        if exc:
            self.export_status_var.set("Export failed.")
            self._append_text(self.export_log, f"Error: {exc}")
            messagebox.showerror("Export failed", str(exc))
        else:
            self.export_status_var.set(f"Done. Saved {entry['message_count']:,} messages.")
            self._append_text(self.export_log, f"Done. Saved {entry['message_count']:,} messages to {entry['output_file']}")
            messagebox.showinfo("Export complete", f"Saved {entry['message_count']:,} messages.")

    def _handle_convert_done(self, converted: int, exc: Exception | None):
        self.convert_progress.stop()
        self.start_convert_button.configure(state="normal")
        if exc:
            self.convert_status_var.set("Conversion failed.")
            self._append_text(self.convert_log, f"Error: {exc}")
            messagebox.showerror("Conversion failed", str(exc))
        else:
            self.convert_status_var.set(f"Done. Converted {converted} file(s).")
            self._append_text(self.convert_log, f"Done. Converted {converted} file(s).")

    def _refresh_summary(self):
        for item in self.summary_tree.get_children():
            self.summary_tree.delete(item)
        labels = {"ok": "Done", "interrupted": "Paused", "failed": "Failed"}
        for entry in self.session_log:
            kind = "Group chat" if entry["id_type"] == "group_id" else "Single AI"
            self.summary_tree.insert(
                "",
                "end",
                values=(
                    entry.get("character_name") or entry["identifier"],
                    kind,
                    f"{entry['message_count']:,}",
                    labels.get(entry["status"], entry["status"]),
                    entry["output_file"],
                ),
            )

    def _append_text(self, widget: tk.Text, message: str):
        widget.insert("end", f"{message}\n")
        widget.see("end")

    def _clear_text(self, widget: tk.Text):
        widget.delete("1.0", "end")


def main():
    app.configure_console_encoding()
    KindroidExporterGui().mainloop()


if __name__ == "__main__":
    main()
