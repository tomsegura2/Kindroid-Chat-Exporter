# Contributing to Kindroid Chat Exporter

First off, thank you for considering contributing to **Kindroid Chat Exporter**! It's people like you who make tools like this safer, easier to use, and more reliable for the entire Kindroid community. 

Whether you are reporting a bug, suggesting a new feature, improving our documentation, or submitting a Pull Request, your involvement is warmly welcomed.

---

## 📋 Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [Got a Question or Feature Request?](#got-a-question-or-feature-request)
3. [Reporting Bugs & Security Vulnerabilities](#reporting-bugs--security-vulnerabilities)
4. [Development Setup](#development-setup)
5. [Coding Standards & Style Guide](#coding-standards--style-guide)
6. [Security & SonarQube Guidelines](#security--sonarqube-guidelines)
7. [Submitting a Pull Request (PR)](#submitting-a-pull-request-pr)

---

## 🤝 Code of Conduct

This project is built for a diverse community of users. We expect all contributors to adhere to a basic standard of kindness, empathy, and professional collaboration:
* **Be respectful and welcoming:** Treat everyone with courtesy. Harassment, derogatory language, or personal attacks will not be tolerated.
* **Focus on constructive feedback:** When reviewing code or discussing issues, aim to build up, not tear down.
* **Respect privacy:** Kindroid chat logs are deeply personal. Never ask users to share unredacted API keys, group IDs, or personal chat histories when troubleshooting issues.

---

## 💡 Got a Question or Feature Request?

If you have a question about how the script works or an idea for a new conversion format or beginner-friendly feature:
1. Check the existing **[Issues](../../issues)** to see if someone else has already asked or proposed it.
2. If not, open a new **Feature Request Issue**.
3. Clearly describe the feature, why it would be helpful for everyday users, and any design suggestions you might have. Keep in mind our core philosophy: **keep it beginner-friendly and plain-English**.

---

## 🐞 Reporting Bugs & Security Vulnerabilities

### Standard Bugs
When reporting a bug via GitHub Issues, please include:
* **Your operating system** (Windows 11, macOS Sonoma, Ubuntu 24.04, etc.) and terminal emulator.
* **Your Python version** (run `python --version` or `python3 --version`).
* **Steps to reproduce the behavior** consistently.
* **The complete error traceback or logs**, if applicable. *(Reminder: Always redact any API keys starting with `kn_` or personal IDs before posting!)*

### Security & Path Injection Vulnerabilities
Because this tool is used in automated and agentic workflows that write directly to the local filesystem, security is paramount. **If you discover a path injection vulnerability (directory traversal, symlink escape, or arbitrary file overwrite), please do NOT open a public GitHub issue.**
Instead, reach out to the maintainers directly via private vulnerability reporting or email so a patch can be developed and released safely.

---

## 🛠 Development Setup

To get a local copy of the project up and running for development:

### 1. Fork and Clone the Repository
```bash
git clone https://github.com/YOUR_USERNAME/kindroid-chat-exporter.git
cd kindroid-chat-exporter
```

### 2. Set Up a Virtual Environment (Recommended)
We strongly recommend using an isolated virtual environment to avoid dependency conflicts:
```bash
# Create a virtual environment
python3 -m venv venv

# Activate on macOS / Linux:
source venv/bin/activate

# Activate on Windows (Command Prompt):
venv\Scripts\activate.bat

# Activate on Windows (PowerShell):
venv\Scripts\Activate.ps1
```

### 3. Install Dependencies
Install the required HTTP library and PDF generation toolkit:
```bash
pip install --upgrade pip
pip install requests reportlab
```
*(Optional)* If you use static analysis or linters during development, you can also install tools like `flake8`, `black`, or `mypy`:
```bash
pip install flake8 black mypy
```

---

## 🎨 Coding Standards & Style Guide

To maintain a clean, readable, and approachable codebase, please adhere to the following principles:

* **Python Version Compatibility:** The project uses modern type hinting syntax (e.g., `str | Path`), requiring **Python 3.10 or higher**. Do not introduce features that break compatibility with Python 3.10 without prior discussion.
* **Beginner-Friendly UX:** Every console output, error message, and prompt must be written in **plain English**. Avoid obscure developer jargon or silent failures. Provide actionable "where-to-find" hints whenever prompting for Kindroid credentials.
* **Consistent Encoding:** Always explicitly pass `encoding="utf-8"` when reading or writing files (`.read_text(encoding="utf-8")`, `.write_text(..., encoding="utf-8")`).
* **Clean Layout:** Use descriptive variable names. Keep helper functions focused on a single responsibility (HTTP pagination, checkpointing, path validation, format conversion).

---

## 🛡 Security & SonarQube Guidelines

We actively monitor code quality and security using **SonarQube / SonarCloud**. When modifying file I/O, path handling, or argument parsing, you must follow our strict security patterns:

### 1. File Path Sanitization (`pythonsecurity:S2083` & `S8707`)
**Never** pass raw user input, CLI arguments, or Kindroid API metadata directly into file system calls (`open()`, `Path.write_text()`, `SimpleDocTemplate()`). 
* All output destinations and source files must be routed through our canonical `validated_path()` helper.
* `validated_path()` enforces symlink resolution (`os.path.realpath`), expands user home directories (`os.path.expanduser`), and validates that the resulting path stays strictly bounded inside the intended workspace directory via `os.path.commonpath`.

### 2. Safe Sequence Access (`pythonbugs:S6466`)
Always verify sequence bounds or use defensive slicing/indexing before accessing elements in strings, tuples, or lists:
```python
# ❌ Avoid: Unchecked slicing that static parsers flag or index assumptions
page_width = letter[0] 

# ✅ Good: Explicit bounds checking or length verification
page_width = letter[0] if len(letter) >= 1 else 612.0
if len(api_key) >= 6:
    preview = f"{api_key[:6]}{'*' * (len(api_key) - 6)}"
```

### 3. SonarQube Version Configuration
If you run local SonarScanner builds or modify CI workflows, ensure the target Python version is explicitly defined to prevent false incompatibility alerts:
```properties
# In sonar-project.properties:
sonar.python.version=3.10, 3.11, 3.12
```

---

## 🚀 Submitting a Pull Request (PR)

When you're ready to share your code:

1. **Create a dedicated branch** for your feature or bug fix:
   ```bash
   git checkout -b feature/pdf-styling-improvements
   ```
2. **Test your changes locally:**
   * Run a test export using both Single AI and Group Chat modes (or mock data).
   * Verify that checkpointing and interruption resumption (`Ctrl+C` -> resume) work as expected.
   * Test conversion to all supported formats (`.jsonl`, `.txt`, `.md`, and `.pdf`).
3. **Keep your commits clean:** Write clear, concise commit messages explaining *why* the change was made.
4. **Push your branch and open a PR:**
   * Reference any relevant GitHub Issue numbers in your PR description (e.g., `Closes #12` or `Fixes #34`).
   * Detail what changes were made and how you tested them.
   * Verify that no API keys or personal chat logs were accidentally committed!

Once submitted, a maintainer will review your code. We may suggest minor edits or formatting tweaks — this is a normal part of the review process. Thanks again for making Kindroid Chat Exporter better for everyone!
