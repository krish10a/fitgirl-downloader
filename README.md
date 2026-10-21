# FitGirl Downloader

A Python + Playwright tool that automates batch downloading from sites like `fuckingfast.co`. It attaches to your existing Microsoft Edge browser (preserving your login, cookies, and extensions), clicks the real download button on each page, and keeps a persistent state so you can safely resume interrupted sessions.

> **For educational and personal use only.** Only use this on sites you have permission to access.

---

## Features

- **Attaches to your existing Edge session** — no need to log in again; your cookies, extensions, and tabs are preserved via Chrome DevTools Protocol (CDP).
- **Domain allowlist** — the script only navigates to domains you explicitly permit, blocking accidental redirects or rogue ads.
- **Automatic ad overlay dismissal** — tries to close common popup overlays before clicking the download button.
- **Persistent state & resume** — saves progress to `downloader_state.json` so a crash or interruption won't make you start over.
- **Retry with exponential backoff** — failed URLs are retried up to `MAX_RETRIES` times with increasing delays.
- **CSV report** — generates a `download_report_<timestamp>.csv` at the end with per-URL success/failure status.
- **Detailed logging** — timestamped log file written alongside the CSV for every session.

---

## Requirements

- Windows 10 or 11
- Python 3.8+  (with "Add Python to PATH" checked during install)
- Microsoft Edge (Chromium-based)

---

## Quick Start (Recommended)

1. **Double-click `run_downloader.bat`.**

   The batch file automatically:
   - Checks your Python installation
   - Installs dependencies from `requirements.txt`
   - Installs the Playwright browser driver for Edge
   - Launches `downloader.py`

2. **Before running**, start Edge with remote debugging enabled:
   ```
   msedge.exe --remote-debugging-port=9222
   ```
   You only need to do this once per session. Edge will restore your previous tabs automatically.

3. **Follow the on-screen prompts:**
   - *(Optional)* Enter a starting page URL, or just press Enter to skip.
   - Paste your list of download URLs, one per line.
   - Type `DONE` (or leave a blank line) when finished.

---

## Manual Setup (PowerShell / Command Prompt)

```powershell
# Install dependencies
pip install -r requirements.txt
python -m playwright install msedge

# Run
python downloader.py
```

---

## Configuration

Open `downloader.py` and edit the **USER CONFIGURATION** section at the top:

| Variable | Default | Description |
|---|---|---|
| `ALLOWED_DOMAINS` | `{"fuckingfast.co"}` | Domains the script is allowed to visit |
| `START_URL` | `about:blank` | Page opened at startup (reference only) |
| `OUTPUT_DIR` | `./downloads` | Where downloaded files are saved |
| `MAX_RETRIES` | `3` | Retry attempts per URL before marking failed |
| `RETRY_BASE_DELAY` | `2.0` | Base delay (seconds) for exponential backoff |
| `INTER_ITEM_DELAY` | `1.5` | Pause between each URL (be polite to servers) |
| `NAVIGATION_TIMEOUT` | `60000` | Page load timeout in milliseconds |
| `HEADLESS` | `False` | `True` = run browser silently in background |
| `DOWNLOAD_BUTTON_SELECTOR` | CSS selector | Targets the real download button on the page |
| `RESUME_ENABLED` | `True` | Resume from last saved state on restart |

---

## Troubleshooting

**`Unable to connect to Microsoft Edge via remote debugging`**
→ Make sure Edge is running with `--remote-debugging-port=9222`. Close all Edge windows first, then re-launch with that flag.

**`Edge is running but remote debugging is not enabled`**
→ Close all Edge windows and relaunch with the debugging flag above.

**`Playwright: Executable doesn't exist`**
→ Run `python -m playwright install msedge` inside your activated virtual environment.

**Timeout errors**
→ The page may be slow or serving heavy ads. Increase `NAVIGATION_TIMEOUT` in `downloader.py`.

**Download button not found**
→ The site may have changed its HTML. Inspect the button in Edge DevTools and update `DOWNLOAD_BUTTON_SELECTOR`.

**Domain blocked / skipped**
→ If the file is served from a CDN subdomain (e.g. `cdn.example.com`), add it to `ALLOWED_DOMAINS`.

---

## Project Structure

```
fitgirl-downloader/
├── downloader.py          # Main script
├── run_downloader.bat     # One-click Windows launcher
├── requirements.txt       # Python dependencies
└── downloads/             # Created at runtime — downloaded files land here
```

Runtime files (excluded from git via `.gitignore`):
- `downloader_state.json` — resume state
- `downloader_<timestamp>.log` — session log
- `download_report_<timestamp>.csv` — per-URL result report

---

## License

MIT


---

## 1. Architecture Overview

- **Terminal Interface**: Greets the user, optionally prompts for a starting page URL, and accepts a paste-ready list of target filenames in the terminal prompt.
- **Browser Automation Core (`Playwright`)**: Controls Microsoft Edge or Chromium with a visible browser window (default). Locates download links through accessible names, anchor text, attributes, and href matching rather than arbitrary pixel coordinates.
- **Strict Domain Allowlist & Tab Isolation**: Tracks popup tabs and child windows. Only allows navigation to domains explicitly defined in `ALLOWED_DOMAINS`. Rogue popups/ads are immediately closed without interrupting the main page task.
- **State Management & Resuming (`download_state.json`)**: Persists downloaded file state to prevent duplicate operations when restarting interrupted sessions.
- **Download Verification**: Confirms browser download events and verifies physical file existence and non-zero size in the output directory.
- **Audit Reports & Logs**: Generates real-time terminal progress indicators, detailed timestamped log files in `logs/`, and a final machine-readable `download_report.csv`.

---

## 2. Windows 10/11 Setup and Execution Instructions

### Prerequisites
1. **Python 3.8+** installed with **"Add Python to PATH"** checked during installation.
2. Windows 10 or Windows 11.

### One-Click Execution (Recommended)
1. Double-click `run_downloader.bat`.
2. The batch script will automatically:
   - Check your Python installation.
   - Create an isolated virtual environment (`venv`).
   - Install required packages (`requirements.txt`).
   - Verify/install browser drivers (`playwright install chromium`).
   - Launch `downloader.py` in the terminal.

### Manual Terminal Execution (PowerShell or Command Prompt)
```powershell
# 1. Create and activate virtual environment
python -m venv venv
.\venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt
python -m playwright install chromium

# 3. Run downloader
python downloader.py
```

---

## 3. Configuration Guide

Open [`downloader.py`](file:///c:/Users/ASUS/Desktop/fitgirl/downloader.py) in any text editor. The top section contains all configuration variables:

- `START_URL`: Default URL to open if not specified during terminal prompt.
- `ALLOWED_DOMAINS`: Strict list of permitted hostnames for downloads and popups.
- `DOWNLOAD_DIR`: Absolute or relative path to store downloaded files (defaults to `./downloads`).
- `MAX_RETRIES`: Number of retry attempts per file before marking as failed.
- `PAGE_TIMEOUT_MS`: Milliseconds to wait for pages to load.
- `DOWNLOAD_TIMEOUT_MS`: Milliseconds to wait for a download stream to initialize.
- `DELAY_BETWEEN_FILES_SEC`: Cooldown period between individual file downloads.
- `HEADLESS`: Set to `False` to view the browser live, or `True` to run silently in the background.
- `RESUME_EXISTING`: When `True`, skips files that are already completed and verified.
- `TARGET_FILES`: Fallback list of filenames to process if interactive input is left empty.

---

## 4. Local Test Procedure

You can quickly verify the entire automation workflow using a local Python HTTP test server:

1. Create a test directory with sample files:
   ```powershell
   mkdir test_server
   echo "sample content 1" > test_server\test_file_01.zip
   echo "sample content 2" > test_server\test_file_02.bin
   ```
2. Start a local server:
   ```powershell
   python -m http.server 8000 --directory test_server
   ```
3. Run `run_downloader.bat` (or `python downloader.py`):
   - When asked for starting URL, enter: `http://localhost:8000/`
   - Paste the following filenames:
     ```text
     test_file_01.zip
     test_file_02.bin
     ```
   - Type `DONE` and press Enter.
4. Watch the browser locate and download each file into `./downloads/` and verify the summary.

---

## 5. Troubleshooting Guide

- **`Playwright: Executable doesn't exist`**:
  Run `python -m playwright install chromium` or `python -m playwright install msedge` inside the activated virtual environment.
- **`Timeout 30000ms exceeded`**:
  The webpage or host server may be slow. Increase `PAGE_TIMEOUT_MS` or `DOWNLOAD_TIMEOUT_MS` in `downloader.py`.
- **`Skipping link ... not in ALLOWED_DOMAINS`**:
  If the download server uses a separate CDN or mirror domain (e.g. `cdn.example.org`), add that domain to the `ALLOWED_DOMAINS` list in `downloader.py`.
- **Permission Errors on Windows**:
  Ensure you have write permissions to the destination folder and your antivirus is not locking newly downloaded archives or binary files.
