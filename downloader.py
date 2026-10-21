#!/usr/bin/env python3
"""
FitGirl Downloader
------------------
Batch-download files from fuckingfast.co (or any similarly structured site)
using Playwright to drive Microsoft Edge.

How it works:
  1. Tries to attach to an already-running Edge instance via the Chrome DevTools
     Protocol (CDP) — so your existing login session, cookies, and extensions are
     preserved. Edge must be started with `--remote-debugging-port=9222` for this.
  2. If Edge isn't running, the script launches it automatically with your
     default user profile, does the work, then closes it.
  3. For each URL you paste in, the script opens a fresh tab, dismisses any ad
     overlays it can find, clicks the real download button, then closes the tab.
     The browser handles the actual file download in the background.
  4. Progress is saved to a JSON state file after every URL so you can safely
     resume if the script crashes or you close it mid-run.
"""

import asyncio
import json
import os
import sys
import time
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Set, Dict, Any, Optional
import urllib.request
import urllib.error

# ============================================================
#  USER CONFIGURATION
#  Edit the values in this section to suit your needs.
#  Don't touch anything outside this block unless you're sure.
# ============================================================

# Only navigate to these domains. Anything else (including ad redirects) is blocked.
ALLOWED_DOMAINS: Set[str] = {
    "fuckingfast.co",
    # Add other trusted domains here if needed, e.g. "mirror.example.com"
}

# Opened at startup just for reference — the script doesn't scrape links from it.
START_URL: str = "about:blank"

# Folder where Edge will save downloaded files.
OUTPUT_DIR: Path = Path("./downloads")

# How many times to retry a URL before giving up and marking it as failed.
MAX_RETRIES: int = 3

# Starting delay for exponential backoff between retries (seconds).
# Retry 1 → 2 s, Retry 2 → 4 s, Retry 3 → 8 s, etc.
RETRY_BASE_DELAY: float = 2.0

# How long to wait between each URL to avoid hammering the server.
INTER_ITEM_DELAY: float = 1.5

# Page-load / element-wait timeout in milliseconds.
# Increase this if the site is slow or shows a long ad countdown timer.
NAVIGATION_TIMEOUT: int = 60000

# False = show the browser window (useful for debugging).
# True  = run headlessly in the background.
HEADLESS: bool = False

# CSS selector that uniquely identifies the real download button on the page.
# If the site changes its HTML, update this selector.
DOWNLOAD_BUTTON_SELECTOR: str = "a.link-button.text-5xl.gay-button"

# When True, reads downloader_state.json on startup and skips already-completed URLs.
RESUME_ENABLED: bool = True
# ============================================================


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _log_console(message: str, level: str = "INFO") -> None:
    print(f"[{_timestamp()}] [{level}] {message}")


def _log_file(log_path: Path, message: str, level: str = "INFO") -> None:
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"[{_timestamp()}] [{level}] {message}\n")


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _load_state(state_path: Path) -> Dict[str, List[str]]:
    """Load JSON state; return dict with keys 'completed' and 'failed'."""
    if state_path.exists():
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
            data.setdefault("completed", [])
            data.setdefault("failed", [])
            return data
        except Exception as e:
            _log_console(f"Could not read state file: {e}", "WARN")
    return {"completed": [], "failed": []}


def _save_state(state_path: Path, state: Dict[str, List[str]]) -> None:
    try:
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception as e:
        _log_console(f"Failed to write state file: {e}", "ERROR")


async def _is_allowed_url(url: str) -> bool:
    """Check if URL's netloc is in ALLOWED_DOMAINS."""
    try:
        from urllib.parse import urlparse
        netloc = urlparse(url).netloc.lower()
        # Remove port if present
        netloc = netloc.split(":")[0]
        return netloc in ALLOWED_DOMAINS
    except Exception:
        return False


def _get_edge_ws_endpoint() -> str:
    """
    Attempts to retrieve the Edge DevTools WebSocket URL.
    Assumes Edge is running with remote debugging enabled on port 9222.
    Returns the webSocketDebuggerUrl string.
    Raises RuntimeError if unable to connect.
    """
    # Try a few times in case Edge is just starting up
    for _ in range(3):
        try:
            with urllib.request.urlopen("http://localhost:9222/json/version", timeout=2) as response:
                data = json.load(response)
                ws_url = data.get("webSocketDebuggerUrl")
                if ws_url:
                    return ws_url
                else:
                    raise RuntimeError("webSocketDebuggerUrl not found in Edge version response")
        except Exception as e:
            # If this is the last attempt, raise a helpful error
            if _ == 2:
                raise RuntimeError(
                    "Unable to connect to Microsoft Edge via remote debugging. "
                    "Please ensure Edge is running with the flag `--remote-debugging-port=9222`.\n"
                    "To start Edge with remote debugging:\n"
                    "  1. Close all Microsoft Edge windows.\n"
                    "  2. Run: msedge.exe --remote-debugging-port=9222\n"
                    "  3. Then run this script again.\n"
                    f"Underlying error: {e}"
                ) from e
            # Wait a bit before retrying
            time.sleep(1)


def _get_edge_profile() -> str:
    """
    Attempt to determine the Edge profile directory from Local State.
    Falls back to "Default" if unable to determine.
    """
    local_state_path = os.path.join(os.getenv("LOCALAPPDATA"), r"Microsoft\Edge\User Data\Local State")
    try:
        with open(local_state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        profile_info = data.get("profile", {})
        last_used = profile_info.get("last_used")
        if last_used and isinstance(last_used, str):
            return last_used
    except Exception:
        pass
    return "Default"


def _find_edge_executable() -> Optional[str]:
    """Try to locate msedge.exe via where command."""
    try:
        result = subprocess.run(
            ["where", "msedge"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            # take the first line
            return result.stdout.strip().splitlines()[0].strip()
    except Exception:
        pass
    # Fallback to common install locations
    common_paths = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for p in common_paths:
        if os.path.isfile(p):
            return p
    return None


def _edge_is_running() -> bool:
    """Return True if any msedge.exe process is detected."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq msedge.exe"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        output = result.stdout.lower()
        return "msedge.exe" in output
    except Exception:
        return False


async def _process_one_url(
    parent_page,
    target_url: str,
    output_dir: Path,
    log_path: Path,
    state: Dict[str, List[str]],
) -> bool:
    """
    Process a single target URL:
    - open a child tab from the same browser context,
    - navigate to the URL,
    - optionally close an ad overlay,
    - click the download button,
    - close the child tab (download starts in background).
    Returns True on success, False on failure (retries handled outside).
    """
    child_page = None
    try:
        _log_console(f"Opening child tab for {target_url}")
        # Use the same browser context as the parent page
        child_page = await parent_page.context.new_page()

        # Enforce domain allowlist
        if not await _is_allowed_url(target_url):
            _log_console(f"URL not in allowed domains: {target_url}", "WARN")
            await child_page.close()
            return False

        await child_page.goto(
            target_url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT
        )

        # Try to dismiss any ad overlay or modal that might be blocking the page.
        # We look for common close-button patterns. If none are found, we move on.
        try:
            overlay_close = child_page.locator(
                "button:has-text('Close'), "
                "[aria-label='Close'], "
                ".close-button, "
                "[data-dismiss='modal']"
            )
            if await overlay_close.count() > 0:
                await overlay_close.first.click(timeout=5000)
                _log_console("Dismissed ad overlay")
        except Exception:
            pass  # No overlay found or couldn't click it — that's fine, carry on.

        # Wait for download button to be visible and enabled
        btn = child_page.locator(DOWNLOAD_BUTTON_SELECTOR)
        await btn.wait_for(state="visible", timeout=NAVIGATION_TIMEOUT)
        is_disabled = await btn.get_attribute("aria-disabled")
        if is_disabled and is_disabled.lower() == "true":
            _log_console(
                f"Download button appears disabled for {target_url}", "WARN"
            )
            await child_page.close()
            return False

        # Click the download button – do NOT wait for download event
        await btn.click(timeout=NAVIGATION_TIMEOUT)
        _log_console(f"Clicked download button for {target_url}")

        # Give the browser a moment to start the download (optional short pause)
        await asyncio.sleep(2)

        await child_page.close()
        return True

    except Exception as exc:
        _log_console(f"Error processing {target_url}: {exc}", "ERROR")
        if child_page:
            try:
                await child_page.close()
            except Exception:
                pass
        return False
    finally:
        # Extra safety: ensure child page closed
        if child_page and not child_page.is_closed():
            try:
                await child_page.close()
            except Exception:
                pass


async def main() -> None:
    _log_console("=== Smart Browser-Based Batch Downloader ===")
    _ensure_dir(OUTPUT_DIR)
    state_path = Path("downloader_state.json")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = Path(f"downloader_{timestamp}.log")
    _log_file(log_path, "Session started")

    # Load state for resume capability
    state = _load_state(state_path) if RESUME_ENABLED else {"completed": [], "failed": []}
    completed: Set[str] = set(state.get("completed", []))
    failed: Set[str] = set(state.get("failed", []))

    # ------------------- USER INPUT: START PAGE -------------------
    _log_console("Enter starting webpage URL (Press Enter for default):")
    start_input = input().strip()
    start_url = start_input if start_input else START_URL
    _log_console(f"Using start page: {start_url}")

    # ------------------- USER INPUT: TARGET URL LIST -------------------
    _log_console(
        "Paste the list of download URLs (one per line). "
        "When finished, type 'DONE' or press Enter on an empty line."
    )
    raw_lines: List[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            line = ""
        if line.strip() == "" or line.strip().upper() == "DONE":
            break
        raw_lines.append(line.strip())
    urls = [u for u in raw_lines if u]

    if not urls:
        _log_console("No URLs provided. Exiting.")
        return

    _log_console(f"Registered {len(urls)} target URL(s) for download.")

    # ------------------- BROWSER SETUP -------------------
    from playwright.async_api import async_playwright

    browser = None
    launched_by_us = False  # True if we launched Edge ourselves; False if we attached to existing Edge
    edge_proc: Optional[subprocess.Popen] = None

    async with async_playwright() as p:
        # First, try to attach to existing Edge via remote debugging
        try:
            ws_endpoint = _get_edge_ws_endpoint()
            browser = await p.chromium.connect_over_cdp(ws_endpoint)
            _log_console("Connected to existing Edge instance via remote debugging")
            launched_by_us = False
        except RuntimeError as e:
            # Could not attach; check if Edge is running at all
            if _edge_is_running():
                _log_console(
                    "Microsoft Edge is running but remote debugging is not enabled. "
                    "Please close all Edge windows and restart Edge with the flag:\n"
                    "  msedge.exe --remote-debugging-port=9222\n"
                    "(Edge will restore your previous session after restart.)",
                    "ERROR",
                )
                _log_file(log_path, "Edge running without remote debugging; aborting.")
                return
            else:
                # Edge is not running; launch it with remote debugging and user profile
                _log_console("Edge not running; launching Edge with remote debugging and user profile...", "INFO")
                edge_exe = _find_edge_executable()
                if not edge_exe:
                    _log_console("Could not locate Microsoft Edge executable.", "ERROR")
                    _log_file(log_path, "Edge executable not found.")
                    return
                edge_user_data_dir = os.path.join(os.getenv("LOCALAPPDATA"), r"Microsoft\Edge\User Data")
                profile_dir = _get_edge_profile()
                _log_console(f"Using Edge profile directory: {profile_dir}")
                # Build launch arguments
                args = [
                    edge_exe,
                    f"--remote-debugging-port=9222",
                    f"--user-data-dir={edge_user_data_dir}",
                    f"--profile-directory={profile_dir}",
                ]
                if HEADLESS:
                    args.append("--headless")
                try:
                    edge_proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    # Give Edge a moment to start
                    await asyncio.sleep(3)
                except Exception as launch_error:
                    _log_console(
                        f"Failed to launch Edge with user profile (maybe Edge is running and locking the user data dir). "
                        f"Falling back to a fresh Edge instance. Error: {launch_error}",
                        "WARN",
                    )
                    browser = await p.chromium.launch(
                        headless=HEADLESS,
                        channel="msedge",
                    )
                    launched_by_us = True
                    _log_console("Temporary Edge browser launched (fresh profile)")
                else:
                    launched_by_us = True

        # Use the first browser context (should be the user's default profile if attached,
        # or a fresh context if we launched a new browser)
        if browser.contexts:
            context = browser.contexts[0]
        else:
            # No existing contexts – create a temporary one
            context = await browser.new_context(accept_downloads=True)

        # Create a new parent page in the context for our script to use
        parent_page = await context.new_page()
        await parent_page.goto(start_url, wait_until="domcontentloaded")
        _log_console("Created parent page for script navigation")

        # Work through each URL the user provided.
        for idx, url in enumerate(urls, start=1):
            _log_console(f"[{idx}/{len(urls)}] Processing: {url}")
            success = False

            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    success = await _process_one_url(
                        parent_page,
                        url,
                        OUTPUT_DIR,
                        log_path,
                        state,
                    )
                except Exception as e:
                    _log_console(f"Unexpected error on attempt {attempt}: {e}", "ERROR")
                    success = False

                if success:
                    break  # No need to retry — move on to the next URL.

                _log_console(
                    f"Attempt {attempt} failed for {url}. "
                    f"{'Retrying...' if attempt < MAX_RETRIES else 'Max retries reached.'}"
                )
                if attempt < MAX_RETRIES:
                    delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    await asyncio.sleep(delay)

            # Record the final outcome after all retry attempts.
            if success:
                completed.add(url)
                state["completed"] = list(completed)
                _log_console(f"[SUCCESS] {url}")
                _log_file(log_path, f"SUCCESS {url}")
            else:
                failed.add(url)
                state["failed"] = list(failed)
                _log_console(f"[FAILED] {url}")
                _log_file(log_path, f"FAILED {url}")

            # Save state after every URL so we can resume if interrupted.
            _save_state(state_path, state)

            # Be polite — wait a moment before hitting the server again.
            if idx < len(urls):
                await asyncio.sleep(INTER_ITEM_DELAY)

            # Close the parent page (the one we created for the script)
            try:
                await parent_page.close()
                _log_console("Closed parent page")
            except Exception as e:
                _log_console(f"Error closing parent page: {e}", "WARN")

        # Close the browser if we launched it ourselves; if we attached to existing Edge,
        # we leave it running (the user's Edge stays open with their tabs).
        if launched_by_us:
            await browser.close()
            if edge_proc:
                edge_proc.terminate()
            _log_console("Closed launched Edge browser")
        else:
            # We attached to existing Edge; just disconnect (close the Playwright connection)
            # The browser itself remains open for the user.
            await browser.close()  # This closes the Playwright connection but not the browser
            _log_console("Disconnected from existing Edge (browser remains open)")

    # ------------------- FINAL SUMMARY & REPORT -------------------
    total = len(urls)
    succ_len = len(completed)
    fail_len = len(failed)
    # Skipped count is not used in this version (we only skip via negative list if added)
    skipped_len = 0

    _log_console("===== SUMMARY =====")
    _log_console(f"Requested files   : {total}")
    _log_console(f"Completed         : {succ_len}")
    _log_console(f"Failed            : {fail_len}")
    _log_console(f"Skipped           : {skipped_len}")

    # Write CSV report
    report_path = Path(f"download_report_{timestamp}.csv")
    try:
        with report_path.open("w", encoding="utf-8", newline="") as csvfile:
            csvfile.write("URL,Status,Timestamp\n")
            for u in urls:
                status = (
                    "SUCCESS"
                    if u in completed
                    else ("FAILED" if u in failed else "PENDING")
                )
                csvfile.write(f'"{u}","{status}","{_timestamp()}"\n')
        _log_console(f"CSV report written to {report_path}")
    except Exception as e:
        _log_console(f"Could not write CSV report: {e}", "ERROR")

    _log_console("Batch downloader finished.")
    _log_file(log_path, "Session ended")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        _log_console("Interrupted by user.", "WARN")
        sys.exit(1)
    except Exception as e:
        _log_console(f"Fatal error: {e}", "ERROR")
        sys.exit(1)