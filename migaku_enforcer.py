#!/usr/bin/env python3
"""
Migaku Study Enforcer - Complete Fixed Version
A Windows 11 Python script that manages internet and application access
based on review count on study.migaku.com

Key Improvements:
- Better JavaScript-based review count extraction
- Fixed Unicode logging issues
- Improved login detection
- Works from language selection page
- Enhanced error handling and retry logic
"""

import re
import os
import sys
import time
import json
import subprocess
import threading
from datetime import datetime, timedelta
from pathlib import Path

# A stray PYTHONPATH can inject another Python install's site-packages ahead of
# this interpreter's own on sys.path. Pure-Python packages still work either way,
# but compiled extensions (e.g. Pillow's _imaging) are tied to a specific CPython
# ABI, so a same-named package from a different Python version crashes on import.
# Strip any sys.path entry tagged for a different version before importing them.
_own_py_ver = f"{sys.version_info.major}{sys.version_info.minor}"
sys.path[:] = [
    p for p in sys.path
    if not (_m := re.search(r'[Pp]ython(3\d+)', p))
    or _m.group(1) == _own_py_ver
]

import tkinter as tk
from tkinter import messagebox
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import psutil
import logging
from typing import Optional
import pystray
from PIL import Image, ImageDraw

# Simplified logging - add a test_mode parameter


def setup_logging(test_mode=False):
    # Absolute path — a relative 'migaku_enforcer.log' only worked by accident of
    # cwd, which breaks once this runs as a frozen exe launched by Task Scheduler
    # from an arbitrary working directory.
    log_path = get_app_data_dir() / "migaku_enforcer.log"

    if test_mode:
        level = logging.INFO
        handlers = [
            logging.FileHandler(log_path, encoding='utf-8'),
            logging.StreamHandler()
        ]
    else:
        level = logging.WARNING  # Only show warnings/errors in production
        handlers = [logging.FileHandler(log_path, encoding='utf-8')]

    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=handlers,
        force=True  # Override any existing configuration
    )


logger = logging.getLogger(__name__)


def log(level, message):
    """Simple logging function"""
    getattr(logger, level)(message)


# Single source of truth for defaults. Both MigakuEnforcer.load_config() and the
# onboarding wizard import these, so the seed lists never drift out of sync the way
# migaku_enforcer.py's and setup_credentials.py's hardcoded copies used to.
DEFAULT_BLOCKED_DOMAINS = [
    "youtube.com", "netflix.com", "twitch.tv", "reddit.com",
    "facebook.com", "instagram.com", "twitter.com", "tiktok.com",
    "discord.com", "discord.gg", "steam.com", "store.steampowered.com", "tumblr.com",
    "claude.ai"
]
DEFAULT_ALLOWED_DOMAINS = ["migaku.com", "study.migaku.com"]
DEFAULT_BLOCKED_APPS = ["steam", "discord", "firefox"]
DEFAULT_DAILY_REVIEW_GOAL = 100
DEFAULT_RESET_HOUR = 4  # local 24h clock hour restrictions reset at (e.g. 4 = 4 AM)
DEFAULT_EMERGENCY_PASSES_ENABLED = True
DEFAULT_EMERGENCY_PASSES_PER_MONTH = 3
DEFAULT_CHECK_INTERVAL_MINUTES = 60
DEFAULT_BLOCKED_APPS_EXACT_MATCH = False  # substring match, matches pre-existing behavior


def get_app_data_dir() -> Path:
    """Per-user app data directory for config/logs (%APPDATA%\\MigakuEnforcer)."""
    base = os.environ.get('APPDATA')
    app_dir = Path(base) / "MigakuEnforcer" if base else Path.home() / ".migaku_enforcer"
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def _lock_file_to_current_user(path: Path) -> None:
    """
    Restrict a file's ACL to the current Windows user only.

    Credentials are stored in plaintext JSON (see config docs), so this is the
    practical mitigation: narrow it from "readable by anyone with local access"
    to "readable by this user account only". Best-effort — never fatal.
    """
    try:
        username = os.environ.get('USERNAME')
        if not username:
            return
        subprocess.run(
            ['icacls', str(path), '/inheritance:r', '/grant:r', f'{username}:F'],
            capture_output=True, timeout=10
        )
    except Exception as e:
        log('warning', f"Could not lock config file permissions: {e}")


def show_loading_animation(message="Checking reviews", stop_event=None):
    """Show animated loading dots"""
    if stop_event is None:
        stop_event = threading.Event()

    # pythonw.exe has no console - stdout is None
    if sys.stdout is None:
        stop_event.wait()
        return

    dots = 0
    while not stop_event.is_set():
        sys.stdout.write(
            f'\r{message}{"." * (dots % 4)}{" " * (3 - (dots % 4))}')
        sys.stdout.flush()
        dots += 1
        time.sleep(0.5)
    sys.stdout.write('\r' + ' ' * (len(message) + 4) + '\r')  # Clear line
    sys.stdout.flush()


class MigakuEnforcer:
    def __init__(self):
        self.config_file = get_app_data_dir() / "config.json"
        self._migrate_legacy_config()
        self.load_config()
        self.is_running = True
        self.driver = None
        self.headless = True  # Default to headless mode
        self.test_mode = False  # Default to non-test mode
        self.max_retries = 3
        self.retry_delay = 5
        # GUI state (polled by MigakuStatusWindow)
        self.current_review_count = None
        self.current_status = "Starting up..."
        self._gui_messages = []
        self.reviews_complete = False  # set True to trigger auto-close

    def _migrate_legacy_config(self) -> None:
        """
        One-time copy from the old Path.home()/migaku_enforcer_config.json location
        (pre-%APPDATA% versions) to the new config_file path, if the new file doesn't
        exist yet. Copies rather than moves — leaves the old file in place so rolling
        back to an old build still works.
        """
        if self.config_file.exists():
            return
        legacy_path = Path.home() / "migaku_enforcer_config.json"
        if not legacy_path.exists():
            return
        try:
            with open(legacy_path, 'r') as f:
                legacy_config = json.load(f)
            with open(self.config_file, 'w') as f:
                json.dump(legacy_config, f, indent=2)
            log('info', f"Migrated legacy config from {legacy_path} to {self.config_file}")
        except (json.JSONDecodeError, IOError, OSError) as e:
            log('warning', f"Could not migrate legacy config: {e}")

    def load_config(self) -> None:
        """Load configuration from file or create default"""
        default_config = {
            "config_version": 2,
            "emergency_passes_used": 0,
            "emergency_passes_reset_date": datetime.now().strftime("%Y-%m"),
            "restrictions_disabled_until": None,
            "migaku_credentials": {
                "email": "",
                "password": "",
                "auto_login": True
            },
            "blocked_domains": list(DEFAULT_BLOCKED_DOMAINS),
            "allowed_domains": list(DEFAULT_ALLOWED_DOMAINS),
            "blocked_apps": list(DEFAULT_BLOCKED_APPS),
            "daily_review_goal": DEFAULT_DAILY_REVIEW_GOAL,
            "reset_hour": DEFAULT_RESET_HOUR,
            "emergency_passes_enabled": DEFAULT_EMERGENCY_PASSES_ENABLED,
            "emergency_passes_per_month": DEFAULT_EMERGENCY_PASSES_PER_MONTH,
            "check_interval_minutes": DEFAULT_CHECK_INTERVAL_MINUTES,
            "blocked_apps_exact_match": DEFAULT_BLOCKED_APPS_EXACT_MATCH,
            "onboarding_completed": False,
            "install_to_startup": False,
            "last_successful_check": None,
            "consecutive_errors": 0,
            "reviews_completed_today": 0,
            "last_seen_review_count": None,
            "progress_date": None
        }

        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    self.config = json.load(f)
                had_onboarding_key = 'onboarding_completed' in self.config
                # Ensure all default keys exist
                for key, value in default_config.items():
                    if key not in self.config:
                        self.config[key] = value
                # An existing config from before onboarding_completed existed (or a
                # migrated pre-wizard legacy config) already has working credentials
                # — don't force a returning user through the wizard just because this
                # key is new.
                if not had_onboarding_key:
                    creds = self.config.get('migaku_credentials', {})
                    if creds.get('email') and creds.get('password'):
                        self.config['onboarding_completed'] = True
            except (json.JSONDecodeError, IOError) as e:
                log(
                    'error', f"Error loading config: {e}. Using defaults.")
                self.config = default_config
        else:
            self.config = default_config

        self.save_config()

    def save_config(self) -> None:
        """Save configuration to file"""
        try:
            is_new_file = not self.config_file.exists()
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            if is_new_file:
                _lock_file_to_current_user(self.config_file)
        except IOError as e:
            log('error', f"Error saving config: {e}")

    def _find_cached_chromedriver(self) -> Optional[str]:
        """
        Locate the newest chromedriver Selenium Manager has already downloaded.

        Selenium Manager resolves/downloads a matching chromedriver over the
        network on every launch. Right after the machine wakes from sleep the
        network can be up for the app but not yet for that resolution call,
        so webdriver.Chrome() fails even though a perfectly usable driver is
        already sitting in the cache from a previous successful run.
        """
        cache_dir = Path.home() / ".cache" / "selenium" / "chromedriver" / "win64"
        if not cache_dir.exists():
            return None
        candidates = [d / "chromedriver.exe" for d in cache_dir.iterdir() if d.is_dir()]
        candidates = [c for c in candidates if c.exists()]
        if not candidates:
            return None
        return str(max(candidates, key=lambda p: p.stat().st_mtime))

    def setup_webdriver(self) -> bool:
        """Initialize Chrome webdriver"""
        if self.driver:
            return True

        options = Options()
        if self.headless:
            options.add_argument("--headless=new")

        # Suppress Chrome logs in production mode
        if not getattr(self, 'test_mode', False):
            options.add_argument("--log-level=3")  # Only fatal errors
            options.add_argument("--disable-logging")
            options.add_argument("--disable-gpu-logging")
            options.add_argument("--silent")

        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-images")

        # Suppress additional Chrome messages
        options.add_experimental_option('excludeSwitches', ['enable-logging'])
        options.add_experimental_option('useAutomationExtension', False)

        try:
            self.driver = webdriver.Chrome(options=options)
        except Exception as e:
            cached_driver = self._find_cached_chromedriver()
            if not cached_driver:
                log('error', f"WebDriver setup failed: {e}")
                return False
            log('warning',
                f"Selenium Manager failed ({e}); retrying with cached driver {cached_driver}")
            try:
                self.driver = webdriver.Chrome(
                    service=Service(executable_path=cached_driver), options=options)
            except Exception as e2:
                log('error', f"WebDriver setup failed even with cached driver: {e2}")
                return False

        self.driver.set_page_load_timeout(30)
        if getattr(self, 'test_mode', False):
            log('info', "WebDriver initialized")
        return True

    def setup_credentials(self) -> bool:
        """Check if credentials are available"""
        creds = self.config.get('migaku_credentials', {})
        if not creds.get('email') or not creds.get('password'):
            log('error', "No Migaku credentials found!")
            log(
                'info', "Please run 'python setup_credentials.py' to set up your login")
            return False
        return True

    def login_to_migaku(self) -> bool:
        """Login and handle language selection"""
        if not self.driver:
            return False

        try:
            log('info', "Logging into Migaku...")
            creds = self.config['migaku_credentials']

            # Navigate and wait for form
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, 'input[type="email"]'))
            )

            # Fill and submit form
            email_field = self.driver.find_element(
                By.CSS_SELECTOR, 'input[type="email"]')
            password_field = self.driver.find_element(
                By.CSS_SELECTOR, 'input[type="password"]')
            login_button = self.driver.find_element(
                By.CSS_SELECTOR, 'button.UiButton.-gradient.-full-width')

            email_field.send_keys(creds['email'])
            password_field.send_keys(creds['password'])
            login_button.click()

            time.sleep(5)  # Wait for redirect

            # Always attempt language selection
            return self.select_japanese_language()

        except Exception as e:
            log('error', f"Login failed: {e}")
            return False

    def select_japanese_language(self) -> bool:
        """Select Japanese language"""
        if not self.driver:
            log('error', "WebDriver not initialized")
            return False

        try:
            selectors = [
                'button[aria-label="ID:LanguageSelect.ja"]',
                'button[aria-label*="LanguageSelect.ja"]'
            ]

            for selector in selectors:
                try:

                    button = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    if button.is_displayed():
                        button.click()
                        log('info', "Japanese language selected")
                        time.sleep(3)
                        return True
                except Exception:
                    continue

            log('info', "Language selection not needed or failed")
            return True  # Continue anyway

        except Exception as e:
            log('warning', f"Language selection error: {e}")
            return True

    def _save_debug_files(self, body_text: str) -> None:
        """Save page HTML and visible text for selector diagnosis."""
        try:
            script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
            html_path = script_dir / 'migaku_debug.html'
            txt_path = script_dir / 'migaku_debug.txt'
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(self.driver.page_source)
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(f"URL: {self.driver.current_url}\n\n{body_text}")
            log('info', f"Debug files saved: {html_path}, {txt_path}")
            print(f"\nDebug files saved:\n  {html_path}\n  {txt_path}\n")
        except Exception as e:
            log('error', f"Could not save debug files: {e}")

    def get_review_count_dom_scraping(self) -> Optional[int]:
        """Extract review count from page text."""

        if not self.driver:
            log('error', "WebDriver not initialized")
            return None

        log('info', "Extracting review count from DOM...")

        try:
            WebDriverWait(self.driver, 10).until(
                lambda d: d.execute_script(
                    'return document.readyState') == 'complete'
            )
            time.sleep(5)
        except TimeoutException:
            log('warning', "Page load timeout, attempting scrape anyway")
            time.sleep(3)

        try:
            body_text = self.driver.execute_script(
                'return document.body ? document.body.innerText : ""'
            ) or ''

            if getattr(self, '_debug_html', False):
                self._save_debug_files(body_text)

            if getattr(self, 'test_mode', False):
                log('info', f"Page URL: {self.driver.current_url}")
                log('info', f"Page text (first 400 chars): {body_text[:400]}")

            # Match "N review" or "N reviews" with word boundary so "reviewed"
            # is never mistaken for a pending count.
            pending_pattern = re.compile(r'\b(\d+)\s+reviews?\b', re.IGNORECASE)
            matches = pending_pattern.findall(body_text)
            valid_counts = [int(m) for m in matches if int(m) <= 9999]
            if valid_counts:
                count = valid_counts[0]
                log('info', f"SUCCESS: Review count = {count}")
                return count

            # Fallback: explicit completion phrase with no number
            if re.search(
                r'\b(?:all\s+done|no\s+reviews?|0\s+reviews?)\b',
                body_text, re.IGNORECASE
            ):
                log('info', "SUCCESS: Completion indicator found - 0 reviews remaining")
                return 0

            log('warning', "Could not find review count")
            return None

        except Exception as e:
            log('error', f"DOM scraping error: {e}")
            return None

    def get_review_count(self) -> int:
        """Get review count from Migaku"""
        if not self.setup_webdriver() or not self.setup_credentials():
            return -1

        # Start loading animation if not in test mode
        stop_loading = threading.Event()
        loading_thread = None
        if not getattr(self, 'test_mode', False):
            loading_thread = threading.Thread(
                target=show_loading_animation,
                args=("Checking reviews", stop_loading),
                daemon=True
            )
            loading_thread.start()

        try:
            for attempt in range(self.max_retries):
                try:
                    if not self.driver:
                        log('error', "WebDriver not initialized")
                        return -1

                    if getattr(self, 'test_mode', False):
                        log('info',
                            f"Getting review count (attempt {attempt + 1}/{self.max_retries})")

                    # Navigate to Migaku
                    self.driver.get("https://study.migaku.com/")
                    WebDriverWait(self.driver, 20).until(
                        EC.presence_of_element_located((By.TAG_NAME, "body"))
                    )

                    # Give React time to hydrate
                    time.sleep(5)  # Increased from 3 to 5 seconds

                    # Handle login if needed
                    current_url = self.driver.current_url.lower()
                    if "login" in current_url:
                        if not self.login_to_migaku():
                            if attempt < self.max_retries - 1:
                                time.sleep(self.retry_delay)
                                continue
                            return -1
                    elif "language" in current_url or "select" in current_url:
                        # Language selection page
                        if not self.select_japanese_language():
                            log('warning',
                                "Language selection failed, continuing anyway")
                        time.sleep(3)

                    # Ensure we're on the study dashboard
                    if "study.migaku.com" in self.driver.current_url and "login" not in self.driver.current_url:
                        # Wait for study dashboard to fully load
                        time.sleep(5)  # Additional wait for dynamic content
                    else:
                        log('warning',
                            f"Unexpected URL: {self.driver.current_url}")

                    # Wait for page to load then scrape
                    time.sleep(5)
                    review_count = self.get_review_count_dom_scraping()

                    if review_count is not None:
                        self.config['last_successful_check'] = datetime.now(
                        ).isoformat()
                        self.config['consecutive_errors'] = 0
                        self.save_config()
                        return review_count

                except Exception as e:
                    log('warning', f"Attempt {attempt + 1} failed: {type(e).__name__}: {e}")

                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)

            log('error', "All attempts failed")
            self.config['consecutive_errors'] = self.config.get(
                'consecutive_errors', 0) + 1
            self.save_config()
            return -1

        finally:
            # Stop loading animation
            if loading_thread:
                stop_loading.set()
                loading_thread.join(timeout=1)

    def track_study_progress(self):
        """Track and celebrate study consistency"""
        today = datetime.now().date().isoformat()
        study_log = self.config.get('study_log', {})

        # If reviews completed (count reached 0), log it
        if self.get_review_count() == 0:
            study_log[today] = True
            streak_days = 0
            current_date = datetime.now().date()

            # Calculate current streak
            while current_date.isoformat() in study_log:
                streak_days += 1
                current_date -= timedelta(days=1)

            self.config['study_log'] = study_log
            self.config['current_streak'] = streak_days
            self.save_config()

            # Celebrate milestones
            if streak_days == 1:
                print("Great start! Day 1 complete.")
            elif streak_days == 7:
                print("Amazing! One week streak achieved!")
            elif streak_days % 30 == 0:
                print(
                    f"Incredible! {streak_days} day streak - you're building a real habit!")
            elif streak_days > 1:
                print(
                    f"Day {streak_days} complete. Consistency builds success!")

    def show_motivational_context(self, review_count):
        """Show encouraging context about review load"""
        if review_count <= 5:
            print(f"Just {review_count} reviews - that's only a few minutes!")
        elif review_count <= 15:
            print(
                f"{review_count} reviews - perfect for a focused 10-minute session.")
        elif review_count <= 50:
            print(
                f"{review_count} reviews - break it into 2-3 small sessions if needed.")
        else:
            print(
                f"{review_count} reviews - consider doing batches throughout the day.")

        # Show streak info if available
        streak = self.config.get('current_streak', 0)
        if streak > 0:
            print(f"Your current streak: {streak} days. Keep it going!")

    def _tomorrow_reset(self) -> datetime:
        """
        Tomorrow's configured reset time (default 4 AM) — the moment restrictions
        lift until. Centralizes what used to be six separate hardcoded
        `hour=4` literals so the reset time is configurable (see reset_hour).
        """
        reset_hour = self.config.get('reset_hour', DEFAULT_RESET_HOUR)
        return (datetime.now() + timedelta(days=1)).replace(
            hour=reset_hour, minute=0, second=0, microsecond=0)

    def use_emergency_pass(self) -> bool:
        """Emergency pass with reflection step"""
        current_month = datetime.now().strftime("%Y-%m")

        if self.config.get('pass_reset_month') != current_month:
            self.config['monthly_passes_used'] = 0
            self.config['pass_reset_month'] = current_month

        passes_used = self.config.get('monthly_passes_used', 0)

        if passes_used >= 3:
            print("All emergency passes used this month.")
            print("Emergency situations: Consider calling a friend/family member for help accessing needed resources.")
            return False

        # Reflection prompt to discourage casual use
        print("\nEmergency passes are for genuine urgent situations.")
        print("Examples: Medical emergency, work deadline, family crisis")
        reason = input(
            "Briefly describe your emergency (or 'cancel' to return): ").strip()

        if reason.lower() == 'cancel':
            print("Returning to enforcement mode.")
            return False

        # Log the reason (helps identify patterns)
        emergency_log = self.config.get('emergency_log', [])
        emergency_log.append({
            'date': datetime.now().isoformat(),
            'reason': reason[:100]  # Truncate long reasons
        })
        self.config['emergency_log'] = emergency_log[-10:]  # Keep last 10

        self.config['monthly_passes_used'] = passes_used + 1
        self.config['restrictions_disabled_until'] = self._tomorrow_reset().isoformat()
        self.save_config()

        remaining = 3 - self.config['monthly_passes_used']
        print(f"Emergency pass activated. {remaining} remaining this month.")
        print("Restrictions disabled until 4 AM tomorrow.")
        return False

    def interactive_console_mode(self):
        """Run with time delays to prevent escape-seeking behavior"""
        last_check_time = self.config.get('last_manual_check', 0)
        current_time = time.time()

        # Minimum 30 minutes between manual checks
        if current_time - last_check_time < 1800:
            remaining_wait = int(1800 - (current_time - last_check_time))
            print(
                f"Next manual check available in {remaining_wait//60} minutes, {remaining_wait % 60} seconds")
            return self.get_review_count() > 0

        review_count = self.get_review_count()
        self.config['last_manual_check'] = current_time
        self.save_config()

        if self._reviews_done(review_count):
            print(f"{self._done_reason(review_count)} Restrictions OFF until 4 AM tomorrow.")
            self.track_study_progress()
            return False

        print(f"You have {review_count} reviews remaining.")
        self.show_motivational_context(review_count)

        # Single choice - no repeated checking
        response = input(
            "\nChoose: start reviews now, use emergency pass, or continue enforcement? reviews/pass/enforce: ").lower().strip()

        if response == 'reviews':
            print("Great choice! Opening Migaku study page...")
            try:
                import webbrowser
                webbrowser.open("https://study.migaku.com/")
            except:
                pass
            return True
        elif response == 'pass':
            return not self.use_emergency_pass()  # Returns True if pass was NOT used
        else:
            print("Enforcement continues.")
            return True

    # Never killed via blocked_apps, in either match mode: chromedriver.exe is
    # spawned by this app itself for review checks, so a substring match on
    # e.g. "chrome" would otherwise kill the browser driver out from under
    # itself the next time it tries to check your reviews.
    _PROTECTED_PROCESS_NAMES = {'chromedriver.exe', 'chromedriver'}

    def _process_matches(self, proc_name: str, blocked_entry: str) -> bool:
        """
        True if a running process name matches a blocked_apps entry, honoring
        blocked_apps_exact_match. Exact mode compares names with any trailing
        ".exe" stripped from both sides (blocked_apps entries are typically
        given without it, e.g. "steam", but psutil reports "steam.exe").
        """
        proc_lower = proc_name.lower()
        if proc_lower in self._PROTECTED_PROCESS_NAMES:
            return False

        entry_lower = blocked_entry.lower()
        if self.config.get('blocked_apps_exact_match', DEFAULT_BLOCKED_APPS_EXACT_MATCH):
            strip = lambda s: s[:-4] if s.endswith('.exe') else s
            return strip(proc_lower) == strip(entry_lower)
        return entry_lower in proc_lower

    def is_process_running(self, process_name: str) -> bool:
        """Check if a process is running, honoring blocked_apps_exact_match."""
        try:
            for proc in psutil.process_iter(['name']):
                proc_name = proc.as_dict(attrs=['name']).get('name')
                if proc_name and self._process_matches(proc_name, process_name):
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        return False

    def kill_processes(self, process_name: str) -> bool:
        """Terminate processes by name, honoring blocked_apps_exact_match."""
        if getattr(self, 'test_mode', False):
            msg = f"[TEST] Would kill: {process_name}"
            log('info', msg)
            self._gui_messages.append(msg)
            return True
        killed = False
        try:
            for proc in psutil.process_iter(['name', 'pid']):
                proc_name = proc.name()
                proc_pid = proc.as_dict(attrs=['pid']).get('pid')
                if proc_name and self._process_matches(proc_name, process_name):
                    try:
                        # Check if process still exists before terminating
                        if proc.is_running():
                            log('info',
                                f"Terminating {proc_name} (PID: {proc_pid})")
                            proc.terminate()
                            proc.wait(timeout=3)
                            killed = True
                    except psutil.TimeoutExpired:
                        try:
                            if proc.is_running():
                                proc.kill()
                                killed = True
                        except psutil.NoSuchProcess:
                            pass  # Process already gone
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        # Process already terminated or no access
                        pass
                    except Exception as e:
                        log('warning',
                            f"Could not terminate {proc_name}: {e}")
        except Exception as e:
            log('error', f"Error killing {process_name} processes: {e}")
        return killed

    def modify_hosts_file(self, block: bool = True) -> bool:
        """
        Modify hosts file to block/unblock websites
        Returns True if successful, False otherwise
        """
        if getattr(self, 'test_mode', False):
            domains = self.config.get('blocked_domains', [])
            action = "block" if block else "unblock"
            msg = f"[TEST] Would {action} {len(domains)} domains (e.g. {', '.join(domains[:3])}...)"
            log('info', msg)
            self._gui_messages.append(msg)
            return True
        hosts_path = Path("C:/Windows/System32/drivers/etc/hosts")
        blocked_marker = "# MIGAKU_ENFORCER_BLOCKED"

        try:
            # Check if we can write to hosts file
            if not os.access(hosts_path, os.W_OK):
                log(
                    'error', "No write permission to hosts file. Run as administrator.")
                return False

            # Read current hosts file
            current_content = ""
            if hosts_path.exists():
                try:
                    with open(hosts_path, 'r', encoding='utf-8') as f:
                        current_content = f.read()
                except UnicodeDecodeError:
                    # Try with different encoding
                    with open(hosts_path, 'r', encoding='cp1252') as f:
                        current_content = f.read()

            # Remove existing blocks
            lines = current_content.split('\n')
            cleaned_lines = [
                line for line in lines if blocked_marker not in line]

            if block:
                # Add new blocks
                blocked_entries = []
                for domain in self.config['blocked_domains']:
                    blocked_entries.extend([
                        f"127.0.0.1 {domain} {blocked_marker}",
                        f"127.0.0.1 www.{domain} {blocked_marker}"
                    ])

                new_content = '\n'.join(cleaned_lines + [''] + blocked_entries)
                log(
                    'info', f"Blocking {len(self.config['blocked_domains'])} domains")
            else:
                new_content = '\n'.join(cleaned_lines).strip()
                log('info', "Unblocking all domains")

            # Write back to hosts file
            with open(hosts_path, 'w', encoding='utf-8') as f:
                f.write(new_content + '\n')

            # Flush DNS cache
            try:
                subprocess.run(['ipconfig', '/flushdns'],
                               shell=True, capture_output=True, timeout=30)
                log('info', "DNS cache flushed")
            except subprocess.TimeoutExpired:
                log(
                    'warning', "DNS flush timed out but hosts file was modified")

            return True

        except PermissionError:
            log(
                'error', "Permission denied. Run as administrator to modify hosts file.")
            return False
        except Exception as e:
            log('error', f"Error modifying hosts file: {e}")
            return False

    def _reset_time_label(self) -> str:
        """Human-readable form of the configured reset_hour, e.g. '4 AM'."""
        hour = self.config.get('reset_hour', DEFAULT_RESET_HOUR)
        period = 'AM' if hour < 12 else 'PM'
        hour12 = hour % 12 or 12
        return f"{hour12} {period}"

    def show_emergency_pass_dialog(self, parent=None) -> bool:
        """
        Show dialog for emergency pass usage.

        IMPORTANT: pass `parent` (an existing Tk widget) whenever one is
        available — e.g. MigakuStatusWindow.root. Without it this used to spin
        up a brand-new tk.Tk() root of its own, which is unsafe/flaky when
        another Tk mainloop (the main status window) is already running, and
        was the root cause of the "used a pass but restrictions didn't lift"
        bug: an always-on-top main window could render above this dialog's
        own untracked root, leaving it invisible/unclickable behind it.
        Using `parent` makes this a proper child dialog of the real window
        instead. NEVER call this from a background thread — Tkinter is not
        thread-safe; see the caller note in are_restrictions_active().
        """
        if not self.config.get('emergency_passes_enabled', DEFAULT_EMERGENCY_PASSES_ENABLED):
            messagebox.showinfo(
                "Emergency Pass", "Emergency passes are disabled in Settings.",
                parent=parent)
            return False

        owns_root = parent is None
        try:
            if owns_root:
                parent = tk.Tk()
                parent.withdraw()
                parent.attributes('-topmost', True)

            current_month = datetime.now().strftime("%Y-%m")
            if self.config['emergency_passes_reset_date'] != current_month:
                self.config['emergency_passes_used'] = 0
                self.config['emergency_passes_reset_date'] = current_month
                self.save_config()

            passes_per_month = self.config.get(
                'emergency_passes_per_month', DEFAULT_EMERGENCY_PASSES_PER_MONTH)
            passes_remaining = passes_per_month - self.config['emergency_passes_used']

            if passes_remaining <= 0:
                messagebox.showerror(
                    "No Emergency Passes",
                    f"You have used all {passes_per_month} emergency pass(es) for this month.\n"
                    "Complete your Migaku reviews to regain access.",
                    parent=parent
                )
                return False

            result = messagebox.askyesno(
                "Restricted Access",
                f"RESTRICTIONS ACTIVE\n\n"
                f"You have {passes_remaining} emergency pass(es) remaining this month.\n\n"
                f"Would you like to use one emergency pass?\n"
                f"(This will disable restrictions until {self._reset_time_label()} tomorrow)",
                parent=parent
            )

            if result:
                self.config['emergency_passes_used'] += 1
                self.config['restrictions_disabled_until'] = self._tomorrow_reset().isoformat()
                self.save_config()
                log(
                    'info', f"Emergency pass used. {passes_remaining - 1} remaining.")
                return True

            return False

        except Exception as e:
            log('error', f"Error showing emergency dialog: {e}")
            return False
        finally:
            if owns_root:
                parent.destroy()

    def _update_progress(self, review_count: int) -> None:
        """
        Track cumulative reviews completed today.

        Migaku's due-queue grows during the day as new cards become due, so a
        single "starting count" snapshot can never be caught up to once the
        queue refills. Instead, credit is banked every time the count drops
        from its last-seen value, so a later refill can't erase progress
        already earned.
        """
        today_str = datetime.now().date().isoformat()
        if self.config.get('progress_date') != today_str:
            self.config['progress_date'] = today_str
            self.config['reviews_completed_today'] = 0
            self.config['last_seen_review_count'] = review_count
        else:
            last_seen = self.config.get('last_seen_review_count')
            if last_seen is not None and review_count < last_seen:
                self.config['reviews_completed_today'] = (
                    self.config.get('reviews_completed_today', 0)
                    + (last_seen - review_count)
                )
            self.config['last_seen_review_count'] = review_count
        self.save_config()

    def _reviews_done(self, review_count: int) -> bool:
        """
        Return True if the review session counts as complete.
        Two conditions:
          1. Count is 0 (fully finished), or
          2. At least daily_review_goal reviews have been cumulatively completed today.
        """
        if review_count == 0:
            return True
        goal = self.config.get('daily_review_goal', DEFAULT_DAILY_REVIEW_GOAL)
        return self.config.get('reviews_completed_today', 0) >= goal

    def _done_reason(self, review_count: int) -> str:
        """Human-readable reason why the session is considered done."""
        if review_count == 0:
            return "All reviews done!"
        done = self.config.get('reviews_completed_today', 0)
        goal = self.config.get('daily_review_goal', DEFAULT_DAILY_REVIEW_GOAL)
        return f"{goal} reviews completed today! (cumulative: {done})"

    def are_restrictions_active(self) -> bool:
        """
        Determine if restrictions should be active
        Returns True if restrictions should be enforced
        """
        # Check if restrictions are temporarily disabled
        if self.config['restrictions_disabled_until']:
            try:
                disabled_until = datetime.fromisoformat(
                    self.config['restrictions_disabled_until'])
                if datetime.now() < disabled_until:
                    log('info', "Restrictions temporarily disabled")
                    self.reviews_complete = True
                    self.current_status = f"Goal met! Restrictions lift at {self._reset_time_label()}."
                    return False
                else:
                    # Restriction period ended (reset hour passed) — new day begins
                    self.config['restrictions_disabled_until'] = None
                    self.config['progress_date'] = None
                    self.save_config()
                    self.reviews_complete = False
                    log('info', "Temporary restriction disable period ended")
            except ValueError as e:
                log(
                    'error', f"Invalid restriction disable time format: {e}")
                self.config['restrictions_disabled_until'] = None
                self.save_config()

        # Get review count
        review_count = self.get_review_count()
        self.current_review_count = review_count

        if review_count == -1:
            # Error getting count - check consecutive errors
            consecutive_errors = self.config.get('consecutive_errors', 0)
            if consecutive_errors >= 5:
                # NOTE: this runs on the background enforcement thread, and
                # Tkinter is not thread-safe — never create/drive a Tk dialog
                # from here (that used to happen and was flaky/unsafe). Just
                # surface it in the activity log; the user grants themselves a
                # pass via the Emergency Pass button, which runs the dialog
                # safely on the GUI thread.
                if not getattr(self, '_emergency_notice_shown', False):
                    self._emergency_notice_shown = True
                    msg = ("Repeated errors checking reviews. If you're stuck, "
                           "use the Emergency Pass button.")
                    log('warning', msg)
                    self._gui_messages.append(msg)
            log(
                'warning', "Error getting review count, defaulting to restrictions ON")
            self.current_status = "Check failed - restrictions on by default"
            return True
        self._emergency_notice_shown = False

        # Track today's cumulative progress so _reviews_done() can measure it
        self._update_progress(review_count)

        if self._reviews_done(review_count):
            # Goal met — disable restrictions until tomorrow's reset time
            self.config['restrictions_disabled_until'] = self._tomorrow_reset().isoformat()
            self.save_config()
            reason = self._done_reason(review_count)
            reset_label = self._reset_time_label()
            log('info', f"{reason} Restrictions disabled until {reset_label} tomorrow.")
            self.current_status = f"{reason} Restrictions lift at {reset_label}."
            self.reviews_complete = True
            return False

        else:
            # Reviews remaining - enforce restrictions
            done_so_far = self.config.get('reviews_completed_today', 0)
            goal = self.config.get('daily_review_goal', DEFAULT_DAILY_REVIEW_GOAL)
            log('info', f"{review_count} reviews remaining - restrictions active")
            self.current_status = (
                f"Enforcing: {review_count} reviews remaining"
                f" ({done_so_far}/{goal} done today)"
            )
            return True

    def check_if_restrictions_currently_active(self) -> bool:
        """
        Check if restrictions are currently active by examining hosts file
        Returns True if blocked entries exist, False otherwise
        """
        hosts_path = Path("C:/Windows/System32/drivers/etc/hosts")
        blocked_marker = "# MIGAKU_ENFORCER_BLOCKED"

        try:
            if not hosts_path.exists():
                return False

            # Read hosts file
            try:
                with open(hosts_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except UnicodeDecodeError:
                with open(hosts_path, 'r', encoding='cp1252') as f:
                    content = f.read()

            # Check if any blocked entries exist
            return blocked_marker in content

        except Exception as e:
            log('warning', f"Could not check restrictions status: {e}")
            return False

    def enforce_restrictions(self) -> None:
        """Main enforcement loop with improved error handling"""
        log('info', "Migaku Study Enforcer started")
        error_count = 0
        max_errors = 10
        last_review_check = 0

        while self.is_running and error_count < max_errors:
            try:
                current_time = time.time()

                # Read fresh from config every iteration (same pattern as
                # blocked_apps/blocked_domains below) so a check-interval change
                # in Settings takes effect on the very next 10s tick instead of
                # needing a restart.
                check_interval = self.config.get(
                    'check_interval_minutes', DEFAULT_CHECK_INTERVAL_MINUTES) * 60

                # Only check reviews every check_interval seconds, or if forced
                should_check_reviews = (
                    current_time - last_review_check >= check_interval or
                    last_review_check == 0
                )

                if should_check_reviews:
                    self.current_status = "Checking Migaku for reviews..."
                    last_review_check = current_time
                    restrictions_active = self.are_restrictions_active()
                else:
                    # Check if config was updated by manual check
                    if self.config['restrictions_disabled_until']:
                        try:
                            disabled_until = datetime.fromisoformat(
                                self.config['restrictions_disabled_until'])
                            if datetime.now() < disabled_until:
                                restrictions_active = False
                            else:
                                restrictions_active = getattr(
                                    self, '_last_restriction_state', True)
                        except ValueError:
                            restrictions_active = getattr(
                                self, '_last_restriction_state', True)
                    else:
                        # Use cached restriction state between review checks
                        restrictions_active = getattr(
                            self, '_last_restriction_state', True)

                if restrictions_active:
                    # Block applications (read fresh from config every iteration, same
                    # as modify_hosts_file does for blocked_domains, so Settings changes
                    # apply on the next tick with no extra plumbing)
                    apps_to_block = self.config.get('blocked_apps', [])
                    for app in apps_to_block:
                        if self.is_process_running(app):
                            if self.kill_processes(app):
                                if not getattr(self, 'test_mode', False):
                                    self.show_notification(
                                        f"{app.capitalize()} has been closed!\n"
                                        f"Complete your Migaku reviews to regain access."
                                    )

                    # Block websites (only if not already blocked)
                    if not getattr(self, '_websites_blocked', False):
                        if self.modify_hosts_file(block=True):
                            self._websites_blocked = True
                        else:
                            error_count += 1
                else:
                    # Restrictions not active - unblock everything
                    if getattr(self, '_websites_blocked', True):
                        if self.modify_hosts_file(block=False):
                            self._websites_blocked = False
                        else:
                            error_count += 1

                # Store last restriction state
                self._last_restriction_state = restrictions_active

                # Reset error count on successful cycle
                if error_count > 0:
                    error_count = max(0, error_count - 1)

                # Sleep for shorter intervals but only check reviews hourly
                # Check processes every 10 seconds, reviews every hour
                time.sleep(10)

            except KeyboardInterrupt:
                log('info', "Shutdown requested by user")
                break
            except Exception as e:
                log('error', f"Critical error in enforcement loop: {e}")
                error_count += 1
                time.sleep(60)

        if error_count >= max_errors:
            log('error', "Too many errors occurred. Stopping enforcement for safety.")

        self.cleanup()

    def is_past_4am_reset(self) -> bool:
        """Check if we've passed today's reset time (default 4 AM)"""
        reset_hour = self.config.get('reset_hour', DEFAULT_RESET_HOUR)
        now = datetime.now()
        today_reset = now.replace(hour=reset_hour, minute=0, second=0, microsecond=0)

        # If current time is before the reset hour, check yesterday's instead
        if now.hour < reset_hour:
            today_reset -= timedelta(days=1)

        last_check = self.config.get('last_successful_check')
        if not last_check:
            return True  # First run

        try:
            last_check_time = datetime.fromisoformat(last_check)
            return last_check_time < today_reset < now
        except ValueError:
            return True

    def show_notification(self, message: str) -> None:
        """Show system notification to user"""
        try:
            # Try Windows 10/11 toast notification first
            try:
                import win10toast
                toaster = win10toast.ToastNotifier()
                # Use a more reliable approach
                threading.Thread(
                    target=lambda: toaster.show_toast(
                        "Migaku Study Enforcer",
                        message,
                        duration=5,
                        threaded=False  # Don't use threaded mode
                    ),
                    daemon=True
                ).start()
                return
            except (ImportError, AttributeError, Exception):
                pass

            # Fallback to tkinter messagebox
            try:
                root = tk.Tk()
                root.withdraw()
                root.attributes('-topmost', True)
                root.after(0, lambda: messagebox.showinfo(
                    "Migaku Study Enforcer", message))
                root.mainloop()
                root.destroy()
            except Exception:
                # Last resort: print to console
                print(f"\n*** NOTIFICATION: {message} ***\n")

        except Exception as e:
            if getattr(self, 'test_mode', False):
                log('error', f"Error showing notification: {e}")

    def confirm_shutdown_with_reflection(self) -> bool:
        """Require thoughtful reflection before allowing shutdown"""
        print("\n" + "="*60)
        print("ENFORCEMENT SHUTDOWN - REFLECTION REQUIRED")
        print("="*60)

        questions = [
            "What specific situation requires stopping enforcement right now?",
            "Have you tried doing just 5 reviews first?",
            "What will you do instead if enforcement stops?",
            "How will you feel about this decision tomorrow morning?"
        ]

        for i, question in enumerate(questions, 1):
            print(f"\nQuestion {i}: {question}")
            answer = input("Your answer: ").strip()
            if len(answer) < 65:
                print(
                    f"Please provide a more thoughtful response (at least 65 characters, you wrote {len(answer)})")
                return False

        print("\n" + "="*60)
        print("Shutdown confirmed after reflection.")
        print("="*60)
        return True

    def cleanup(self) -> None:
        """Clean up resources and restore system state"""
        log('info', "Cleaning up...")
        self.is_running = False

        if self.driver:
            try:
                # Check if driver is still accessible
                if self.driver and hasattr(self.driver, 'service') and self.driver.service and hasattr(self.driver.service, 'is_connectable') and self.driver.service.is_connectable():
                    self.driver.quit()
                    log('info', "Browser closed gracefully")
                else:
                    # Force cleanup if connection is lost
                    try:
                        if self.driver.service:
                            self.driver.service.stop()
                    except:
                        pass
                    log('info', "Browser connection was already closed")
            except Exception as e:
                log('warning', f"Browser cleanup issue (this is normal): {e}")
            finally:
                self.driver = None

        # Remove website blocks
        try:
            self.modify_hosts_file(block=False)
            log('info', "Website blocks removed")
        except Exception as e:
            log('error', f"Error removing blocks: {e}")

    def refresh_driver(self) -> bool:
        """Refresh the WebDriver for a clean state"""
        if self.driver:
            try:
                self.driver.quit()
                log('info', "Closed existing WebDriver")
            except Exception as e:
                log('warning', f"Error closing driver: {e}")
            finally:
                self.driver = None

        return self.setup_webdriver()

    def run_with_manual_check(self) -> None:
        """Run enforcement with ability to manually trigger review checks"""
        # Start enforcement in background thread
        enforcement_thread = threading.Thread(
            target=self.enforce_restrictions,
            daemon=True
        )
        enforcement_thread.start()

        # Main thread handles user input
        while self.is_running:
            try:
                user_input = input().strip().lower()

                if user_input == 'check':
                    print("\nManually checking review count...")

                    # Refresh driver for a clean state
                    if not self.refresh_driver():
                        print("❌ Error reinitializing browser. Please try again.")
                        continue

                    # Force a fresh review check
                    review_count = self.get_review_count()

                    if review_count == -1:
                        print("❌ Error checking reviews. Please try again.")
                        continue

                    self._update_progress(review_count)

                    if self._reviews_done(review_count):
                        reason = self._done_reason(review_count)
                        reset_label = self._reset_time_label()
                        print(f"✅ {reason} Restrictions lifted until {reset_label} tomorrow.")
                        print("Great work! 🎉\n")
                        # Update config to disable restrictions
                        self.config['restrictions_disabled_until'] = self._tomorrow_reset().isoformat()
                        self.save_config()
                        # Trigger immediate unblock
                        self.modify_hosts_file(block=False)
                        print("Type 'check' to recheck anytime, or Ctrl+C to exit.")
                    else:
                        progress_made = self.config.get('reviews_completed_today', 0)
                        goal = self.config.get('daily_review_goal', DEFAULT_DAILY_REVIEW_GOAL)
                        needed = max(0, goal - progress_made)
                        print(
                            f"📚 You still have {review_count} reviews remaining.")
                        print(f"   Progress today: {progress_made} done, {needed} more to unlock.")
                        self.show_motivational_context(review_count)
                        print("\nKeep going! Type 'check' when you're done.\n")

                elif user_input == 'help':
                    print("\nAvailable commands:")
                    print("  check - Manually check your review count")
                    print("  help  - Show this help message")
                    print("  exit  - Stop the enforcer (requires reflection)")

                elif user_input == 'exit':
                    if self.confirm_shutdown_with_reflection():
                        break
                    else:
                        print(
                            "Continuing enforcement. Type 'check' to recheck reviews.\n")

                elif user_input:
                    print(f"Unknown command: '{user_input}'")
                    print("Type 'help' for available commands.\n")

            except EOFError:
                # Handle Ctrl+D or input stream closure
                break
            except KeyboardInterrupt:
                # Handle Ctrl+C
                if self.confirm_shutdown_with_reflection():
                    break
                else:
                    print(
                        "\nContinuing enforcement. Type 'check' to recheck reviews.\n")

        self.cleanup()

    def run(self) -> None:
        """Main entry point"""
        try:
            # Start enforcement in background thread
            enforcement_thread = threading.Thread(
                target=self.enforce_restrictions,
                daemon=True
            )
            enforcement_thread.start()

            # Keep main thread alive and handle shutdown gracefully
            while self.is_running:
                time.sleep(1)

        except KeyboardInterrupt:
            if self.confirm_shutdown_with_reflection():
                log('info', "Shutting down after reflection...")
                self.cleanup()
            else:
                print("Returning to enforcement mode...")
                # Continue the enforcement loop
                self.run()


def check_admin_privileges() -> bool:
    """Check if script is running with administrator privileges"""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def install_startup(reset_hour: int = DEFAULT_RESET_HOUR) -> None:
    """
    Install script to run at startup using Task Scheduler.

    reset_hour drives the daily CalendarTrigger below — pass the caller's
    configured config['reset_hour'] so the scheduled 4am-equivalent re-check
    actually matches what the user picked in the wizard/Settings. Re-calling
    this (idempotent — schtasks /create uses /f to overwrite) after the user
    changes reset_hour is how that setting propagates to the scheduled task.
    """
    if not check_admin_privileges():
        log(
            'error', "Administrator privileges required for startup installation")
        return

    if getattr(sys, 'frozen', False):
        # Packaged exe: sys.executable IS the app itself (built --windowed, so it
        # already has no console) — no separate script path or pythonw hop needed.
        pythonw_exe = sys.executable
        script_path = sys.executable
        script_dir = os.path.dirname(sys.executable)
        script_arg = ""
    else:
        script_path = os.path.abspath(__file__)
        python_exe = sys.executable
        script_dir = os.path.dirname(script_path)

        # Use pythonw.exe directly so there is zero console window on startup
        pythonw_exe = python_exe
        if python_exe.lower().endswith('python.exe'):
            candidate = python_exe[:-len('python.exe')] + 'pythonw.exe'
            if Path(candidate).exists():
                pythonw_exe = candidate
        script_arg = f'"{script_path}" '

    # Create scheduled task XML
    # Calls pythonw.exe directly with --no-relaunch so nothing happens on screen
    task_xml = f'''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Migaku Study Enforcer - blocks distractions until Migaku reviews are done</Description>
    <Author>User</Author>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <Delay>PT30S</Delay>
    </LogonTrigger>
    <CalendarTrigger>
      <StartBoundary>2024-01-01T{reset_hour:02d}:00:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
    <RestartOnFailure>
      <Interval>PT1M</Interval>
      <Count>999</Count>
    </RestartOnFailure>
  </Settings>
  <Actions>
    <Exec>
      <Command>"{pythonw_exe}"</Command>
      <Arguments>{script_arg}--no-relaunch --scheduled</Arguments>
      <WorkingDirectory>{script_dir}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>'''

    # Save task XML
    task_xml_path = os.path.join(script_dir, "migaku_task.xml")
    try:
        with open(task_xml_path, 'w', encoding='utf-16') as f:
            f.write(task_xml)
        log('info', f"Task XML created: {task_xml_path}")
    except Exception as e:
        log('error', f"Error creating task XML: {e}")
        return

    # Import task using schtasks
    try:
        result = subprocess.run([
            'schtasks', '/create', '/tn', 'MigakuStudyEnforcer',
            '/xml', task_xml_path, '/f'
        ], capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            log('info', "Successfully installed startup task!")
            log(
                'info', "The enforcer will start automatically when you log in.")
        else:
            log(
                'error', f"Error creating scheduled task: {result.stderr}")

    except subprocess.TimeoutExpired:
        log('error', "Task creation timed out")
    except Exception as e:
        log('error', f"Error running schtasks: {e}")

    # Clean up temporary XML file
    try:
        os.remove(task_xml_path)
    except Exception:
        pass


def uninstall_startup() -> None:
    """Remove startup task"""
    try:
        result = subprocess.run([
            'schtasks', '/delete', '/tn', 'MigakuStudyEnforcer', '/f'
        ], capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            log('info', "Startup task removed successfully!")
        else:
            log('warning', f"Task removal result: {result.stderr}")

    except Exception as e:
        log('error', f"Error removing startup task: {e}")


class ReflectionDialog(tk.Toplevel):
    """Modal dialog requiring thoughtful answers before allowing shutdown."""

    QUESTIONS = [
        "What specific situation requires stopping enforcement right now?",
        "Have you tried doing just 5 reviews first?",
        "What will you do instead if enforcement stops?",
        "How will you feel about this decision tomorrow morning?",
    ]
    MIN_LENGTH = 65

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Shutdown - Reflection Required")
        self.configure(bg='#2d0000')
        self.resizable(False, False)
        self.attributes('-topmost', True)
        self.protocol("WM_DELETE_WINDOW", lambda: None)  # This dialog cannot be X'd out
        self.grab_set()
        self.focus_force()

        self.result = False
        self.q_index = 0

        self._build_ui()
        self._show_question()

        # Center on screen
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")

    def _build_ui(self):
        frame = tk.Frame(self, padx=22, pady=16, bg='#2d0000')
        frame.pack(fill='both', expand=True)

        tk.Label(frame, text="SHUTDOWN REQUIRES REFLECTION",
                 font=('Arial', 12, 'bold'), fg='#ff4444', bg='#2d0000').pack(pady=(0, 4))

        self.progress_label = tk.Label(frame, text="Question 1 of 4",
                                       font=('Arial', 9, 'italic'), fg='#aaaaaa', bg='#2d0000')
        self.progress_label.pack()

        self.question_label = tk.Label(frame, text="", wraplength=430,
                                       font=('Arial', 11), justify='left',
                                       fg='white', bg='#2d0000')
        self.question_label.pack(pady=10)

        self.answer_text = tk.Text(frame, height=4, width=58, wrap='word',
                                   font=('Arial', 10), bg='#1a0000', fg='white',
                                   insertbackground='white', relief='flat')
        self.answer_text.pack(pady=4)
        self.answer_text.bind('<KeyRelease>', self._update_char_count)

        self.char_label = tk.Label(frame,
                                   text=f"0 / {self.MIN_LENGTH} characters minimum",
                                   font=('Arial', 9), fg='#888888', bg='#2d0000')
        self.char_label.pack()

        self.warning_label = tk.Label(frame, text="", fg='#ff4444',
                                      font=('Arial', 9), bg='#2d0000')
        self.warning_label.pack(pady=(2, 0))

        self.next_btn = tk.Button(frame, text="Next Question \u2192",
                                  command=self._next_question,
                                  bg='#555555', fg='white',
                                  font=('Arial', 10, 'bold'),
                                  padx=15, pady=5, relief='flat', cursor='hand2')
        self.next_btn.pack(pady=10)

        tk.Button(frame, text="Cancel \u2014 Keep Enforcing",
                  command=self.destroy,
                  bg='#1a0000', fg='#aaaaaa',
                  font=('Arial', 9), padx=10, pady=3, relief='flat',
                  cursor='hand2').pack()

    def _show_question(self):
        self.progress_label.config(
            text=f"Question {self.q_index + 1} of {len(self.QUESTIONS)}")
        self.question_label.config(text=self.QUESTIONS[self.q_index])
        self.answer_text.delete('1.0', 'end')
        self.char_label.config(
            text=f"0 / {self.MIN_LENGTH} characters minimum", fg='#888888')
        self.warning_label.config(text="")
        if self.q_index == len(self.QUESTIONS) - 1:
            self.next_btn.config(text="Confirm Shutdown")

    def _update_char_count(self, _event=None):
        count = len(self.answer_text.get('1.0', 'end-1c').strip())
        color = '#44ff44' if count >= self.MIN_LENGTH else '#888888'
        self.char_label.config(
            text=f"{count} / {self.MIN_LENGTH} characters minimum", fg=color)

    def _next_question(self):
        answer = self.answer_text.get('1.0', 'end-1c').strip()
        if len(answer) < self.MIN_LENGTH:
            self.warning_label.config(
                text=f"Too short! At least {self.MIN_LENGTH} chars needed. "
                     f"You wrote {len(answer)}.")
            return
        self.warning_label.config(text="")
        self.q_index += 1
        if self.q_index >= len(self.QUESTIONS):
            self.result = True
            self.destroy()
        else:
            self._show_question()


class MigakuStatusWindow:
    """
    Persistent GUI window that replaces the terminal.
    Cannot be closed without completing a reflection exercise.
    """

    def __init__(self, enforcer: 'MigakuEnforcer', test_mode: bool = False):
        self.enforcer = enforcer
        self.test_mode = test_mode
        self.root = tk.Tk()
        self._setup_window()
        self._build_ui()
        # Begin polling the enforcer state
        self.root.after(1500, self._poll_status)

    def _setup_window(self):
        title = "Migaku Enforcer" + (" [TEST MODE]" if self.test_mode else "")
        self.root.title(title)
        self.root.configure(bg='#1a1a2e')
        self.root.resizable(False, False)
        # Always-on-top only in production so it can't be ignored
        self.root.attributes('-topmost', not self.test_mode)

        if self.test_mode:
            self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)
        else:
            self.root.protocol("WM_DELETE_WINDOW", self._attempt_close)

        # Center on screen after building
        self.root.update_idletasks()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"+{(sw - 430) // 2}+{(sh - 450) // 2}")

    def _build_ui(self):
        main = tk.Frame(self.root, bg='#1a1a2e', padx=16, pady=14)
        main.pack(fill='both', expand=True)

        tk.Label(main, text="MIGAKU ENFORCER",
                 font=('Arial', 17, 'bold'), fg='#e94560', bg='#1a1a2e').pack()

        if self.test_mode:
            tk.Label(main, text="[TEST MODE \u2014 no actual blocking]",
                     font=('Arial', 9, 'italic'), fg='#ffff00', bg='#1a1a2e').pack()

        tk.Frame(main, bg='#e94560', height=2).pack(fill='x', pady=8)

        # Status line
        self.status_label = tk.Label(main, text="Starting up...",
                                     font=('Arial', 10), fg='#a8a8b3', bg='#1a1a2e',
                                     wraplength=390)
        self.status_label.pack(pady=(0, 4))

        # Review count
        self.count_label = tk.Label(main, text="Checking reviews...",
                                    font=('Arial', 14, 'bold'), fg='#a8a8b3', bg='#1a1a2e')
        self.count_label.pack(pady=4)

        tk.Frame(main, bg='#2d2d4e', height=1).pack(fill='x', pady=8)

        # Buttons
        btn_frame = tk.Frame(main, bg='#1a1a2e')
        btn_frame.pack(pady=4)

        self.check_btn = tk.Button(btn_frame, text="Check Reviews",
                                   command=self._manual_check,
                                   bg='#16213e', fg='white',
                                   font=('Arial', 10), padx=12, pady=6,
                                   relief='flat', cursor='hand2',
                                   activebackground='#1e3a5f', activeforeground='white')
        self.check_btn.pack(side='left', padx=4)

        tk.Button(btn_frame, text="Emergency Pass",
                  command=self._emergency_pass,
                  bg='#8b0000', fg='white',
                  font=('Arial', 10), padx=12, pady=6,
                  relief='flat', cursor='hand2',
                  activebackground='#aa0000', activeforeground='white').pack(side='left', padx=4)

        self.settings_btn = tk.Button(btn_frame, text="Settings",
                  command=self._open_settings,
                  bg='#16213e', fg='white',
                  font=('Arial', 10), padx=12, pady=6,
                  relief='flat', cursor='hand2',
                  disabledforeground='#666666',
                  activebackground='#1e3a5f', activeforeground='white')
        self.settings_btn.pack(side='left', padx=4)

        exit_label = "Exit" if self.test_mode else "Exit (Reflection)"
        self.exit_btn = tk.Button(btn_frame, text=exit_label,
                  command=self._attempt_close,
                  bg='#333333', fg='#888888',
                  font=('Arial', 10), padx=12, pady=6,
                  relief='flat', cursor='hand2',
                  activebackground='#555555', activeforeground='white')
        self.exit_btn.pack(side='left', padx=4)

        tk.Frame(main, bg='#2d2d4e', height=1).pack(fill='x', pady=8)

        # Log area
        tk.Label(main, text="Activity Log:", font=('Arial', 9, 'bold'),
                 fg='#a8a8b3', bg='#1a1a2e').pack(anchor='w')

        log_frame = tk.Frame(main, bg='#1a1a2e')
        log_frame.pack(fill='both', expand=True)

        self.log_text = tk.Text(log_frame, height=9, width=54,
                                bg='#0d0d1a', fg='#6a6a8a',
                                font=('Courier', 8), state='disabled',
                                relief='flat', bd=0)
        scrollbar = tk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.grid(row=0, column=0, sticky='nsew')
        scrollbar.grid(row=0, column=1, sticky='ns')
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        self._log("Migaku Enforcer started.")
        if self.test_mode:
            self._log("TEST MODE: websites won't be blocked, apps won't be killed.")
        self._update_settings_lock()

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _log(self, msg: str):
        self.log_text.configure(state='normal')
        ts = datetime.now().strftime('%H:%M:%S')
        self.log_text.insert('end', f"[{ts}] {msg}\n")
        self.log_text.see('end')
        self.log_text.configure(state='disabled')

    def _update_count_display(self, count):
        if self.enforcer.reviews_complete:
            self.count_label.config(
                text=f"Goal met! Resting until {self.enforcer._reset_time_label()}", fg='#00ff88')
        elif count is None:
            self.count_label.config(text="Checking reviews...", fg='#a8a8b3')
        elif count == 0:
            self.count_label.config(text="All reviews done!", fg='#00ff88')
        elif count > 0:
            self.count_label.config(text=f"{count} reviews remaining", fg='#ff6b6b')
        elif count == -1:
            self.count_label.config(text="Check failed", fg='#888888')
        else:
            self.count_label.config(text="Checking...", fg='#a8a8b3')

    def _poll_status(self):
        """Called every 2 s from the tkinter event loop to sync enforcer state."""
        self.status_label.config(text=self.enforcer.current_status)

        count = self.enforcer.current_review_count
        # _update_count_display checks reviews_complete before count, so this
        # must run even while count is still None (e.g. restrictions were
        # already disabled from an earlier check, so get_review_count() is
        # never called this session).
        self._update_count_display(count)

        # Drain message queue (list slice + clear is GIL-safe)
        messages = self.enforcer._gui_messages[:]
        self.enforcer._gui_messages.clear()
        for msg in messages:
            self._log(msg)

        # Log a one-time message when goal is met (no auto-close — stay alive for the reset)
        if self.enforcer.reviews_complete and not getattr(self, '_showed_done', False):
            self._showed_done = True
            self._log(f"Goal met! Enforcement resumes automatically at {self.enforcer._reset_time_label()}.")
            self.exit_btn.config(text="Exit (Minimize to Tray)")

        # If a new day arrived (reviews_complete reset by the daily expiry), clear the flag
        if not self.enforcer.reviews_complete:
            if getattr(self, '_showed_done', False):
                self.exit_btn.config(text="Exit" if self.test_mode else "Exit (Reflection)")
            self._showed_done = False
            # A new day started restrictions again while minimized — bring the window back
            if getattr(self, '_tray_icon', None) is not None:
                self._stop_tray()
                self.root.deiconify()
                if not self.test_mode:
                    self.root.attributes('-topmost', True)
                self._log("New day started — restrictions active again. Window restored.")

        self._update_settings_lock()

        if self.enforcer.is_running:
            self.root.after(2000, self._poll_status)
        else:
            self._log("Enforcement stopped.")

    # ------------------------------------------------------------------ #
    #  Button handlers                                                     #
    # ------------------------------------------------------------------ #

    def _manual_check(self):
        self.check_btn.config(state='disabled', text="Checking...")
        self._log("Manual review check triggered...")

        def do_check():
            self.enforcer.refresh_driver()
            count = self.enforcer.get_review_count()
            self.enforcer.current_review_count = count

            if count >= 0:
                self.enforcer._update_progress(count)

            if count >= 0 and self.enforcer._reviews_done(count):
                reason = self.enforcer._done_reason(count)
                reset_label = self.enforcer._reset_time_label()
                self.enforcer.current_status = f"{reason} Restrictions lift at {reset_label}."
                self.enforcer.config['restrictions_disabled_until'] = self.enforcer._tomorrow_reset().isoformat()
                self.enforcer.save_config()
                if not self.test_mode:
                    self.enforcer.modify_hosts_file(block=False)
                self.enforcer._websites_blocked = False
                self.enforcer._gui_messages.append(f"{reason} Restrictions lift at {reset_label}.")
                self.enforcer.reviews_complete = True
            elif count > 0:
                done_so_far = self.enforcer.config.get('reviews_completed_today', 0)
                goal = self.enforcer.config.get('daily_review_goal', DEFAULT_DAILY_REVIEW_GOAL)
                self.enforcer.current_status = f"{count} reviews remaining."
                self.enforcer._gui_messages.append(
                    f"{count} reviews remaining ({done_so_far}/{goal} done today). Keep going!")
            else:
                self.enforcer.current_status = "Could not check reviews."
                self.enforcer._gui_messages.append("Review check failed. Try again.")

            self.root.after(0, lambda: self.check_btn.config(
                state='normal', text="Check Reviews"))

        threading.Thread(target=do_check, daemon=True).start()

    def _emergency_pass(self):
        # parent=self.root: reuse the existing Tk mainloop instead of spinning up
        # a second untracked tk.Tk() root (see show_emergency_pass_dialog's
        # docstring — that was the actual cause of "pass used but nothing lifted").
        if not self.enforcer.show_emergency_pass_dialog(parent=self.root):
            return

        # Apply immediately rather than waiting for the next enforcement-loop
        # tick (which would work too, since the loop re-reads
        # restrictions_disabled_until every 10s — but immediate + explicit is
        # more robust and gives instant feedback in the activity log).
        if not self.test_mode:
            self.enforcer.modify_hosts_file(block=False)
        self.enforcer._websites_blocked = False
        self.enforcer._last_restriction_state = False
        self.enforcer.reviews_complete = True
        reset_label = self.enforcer._reset_time_label()
        self.enforcer.current_status = f"Emergency pass used. Restrictions lift at {reset_label}."
        self.enforcer._gui_messages.append(
            f"Emergency pass used — restrictions lifted until {reset_label} tomorrow.")

    def _settings_unlocked(self) -> bool:
        """
        Settings are only reachable once today's reviews are fully done —
        strictly gated on reviews_complete, no exceptions. Editing
        blocked_domains/blocked_apps mid-restriction would otherwise just be a
        built-in way to remove your own blocks and defeat the whole point of
        the app — including a "check failed" state, which a determined user
        could trigger on purpose (e.g. by entering a wrong password) to keep
        Settings permanently unlocked, if that state were treated as an
        exception.

        Recovery path if you're genuinely stuck (e.g. really did enter the
        wrong password in the wizard and it's blocking every check): use
        Emergency Pass. It doesn't depend on a successful review check, and
        granting one also sets reviews_complete = True, which unlocks Settings
        too — so it's the intended way back in, not a special-cased bypass
        here.
        """
        return self.enforcer.reviews_complete

    def _update_settings_lock(self):
        unlocked = self._settings_unlocked()
        self.settings_btn.config(
            state='normal' if unlocked else 'disabled',
            text="Settings" if unlocked else "Settings (locked)")

    def _open_settings(self):
        if not self._settings_unlocked():
            messagebox.showinfo(
                "Migaku Enforcer",
                "Settings unlock once today's reviews are done. Finish your "
                "reviews, or if you're genuinely stuck (e.g. a wrong password is "
                "blocking every check), use Emergency Pass — that also unlocks "
                "Settings so you can fix it.")
            return
        try:
            from settings_dialog import SettingsWindow
        except Exception as e:
            log('error', f"Could not open Settings: {e}")
            messagebox.showerror("Migaku Enforcer", f"Could not open Settings: {e}")
            return
        SettingsWindow(self.root, self.enforcer, log_callback=self._log)

    def _attempt_close(self):
        if self.test_mode:
            self.root.destroy()
            return

        if self.enforcer.reviews_complete:
            # Goal already met today — no reflection needed, just tuck out of the way.
            self._hide_to_tray()
            return

        dialog = ReflectionDialog(self.root)
        self.root.wait_window(dialog)

        if dialog.result:
            self._log("Shutdown confirmed after reflection.")
            self.enforcer.cleanup()
            self.root.destroy()

    def _make_tray_image(self):
        image = Image.new('RGB', (64, 64), '#1a1a2e')
        draw = ImageDraw.Draw(image)
        draw.ellipse((8, 8, 56, 56), fill='#e94560')
        return image

    def _hide_to_tray(self):
        self.root.withdraw()
        if getattr(self, '_tray_icon', None) is None:
            menu = pystray.Menu(
                pystray.MenuItem("Show Migaku Enforcer", self._restore_from_tray, default=True),
                pystray.MenuItem("Exit", self._tray_exit),
            )
            self._tray_icon = pystray.Icon(
                "migaku_enforcer", self._make_tray_image(), "Migaku Enforcer — goal met", menu)
            self._tray_icon.run_detached()
        self._log(f"Minimized to tray — goal met, resting until {self.enforcer._reset_time_label()}.")

    def _stop_tray(self):
        if getattr(self, '_tray_icon', None) is not None:
            self._tray_icon.stop()
            self._tray_icon = None

    def _restore_from_tray(self, icon=None, item=None):
        def _do():
            self._stop_tray()
            self.root.deiconify()
            self.root.lift()
        self.root.after(0, _do)

    def _tray_exit(self, icon=None, item=None):
        def _do():
            self._stop_tray()
            self.enforcer.cleanup()
            self.root.destroy()
        self.root.after(0, _do)

    # ------------------------------------------------------------------ #

    def run(self):
        self.root.mainloop()


def show_startup_banner():
    """Display startup banner with ASCII art and loading message"""
    banner = """
    ███╗   ███╗██╗ ██████╗  █████╗ ██╗  ██╗██╗███╗   ██╗ █████╗ ███████╗ █████╗ ██╗
    ████╗ ████║██║██╔════╝ ██╔══██╗██║ ██╔╝██║████╗  ██║██╔══██╗██╔════╝██╔══██╗██║
    ██╔████╔██║██║██║  ███╗███████║█████╔╝ ██║██╔██╗ ██║███████║███████╗███████║██║
    ██║╚██╔╝██║██║██║   ██║██╔══██║██╔═██╗ ██║██║╚██╗██║██╔══██║╚════██║██╔══██║██║
    ██║ ╚═╝ ██║██║╚██████╔╝██║  ██║██║  ██╗██║██║ ╚████║██║  ██║███████║██║  ██║██║
    ╚═╝     ╚═╝╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝
    
            MIGAKU STUDY ENFORCER - Keeping you focused!
            *Not officially associated with Migaku. I made this out of ADHDesperation in my free time*
    """
    print(banner)

    import random
    loading_messages = [
        "Checkin' yer wee reviews...",
        "Fetching your review numbers, my liege...",
        "Consulting the study spirits...",
        "Counting your academic obligations...",
        "Checking if you've been a good student..."
    ]

    message = random.choice(loading_messages)
    print(f"\n{message}")
    print("Please wait...\n")


def _notify(message: str, title: str = "Migaku Enforcer", is_error: bool = False) -> None:
    """
    Show a message to the user regardless of whether a console is attached.
    A --windowed frozen build has no stdout (print() is silently lost), so this
    always shows a message box; it also prints when a console IS attached (dev
    runs), matching the previous console-only behavior.
    """
    if sys.stdout is not None:
        print(message)
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        if is_error:
            messagebox.showerror(title, message)
        else:
            messagebox.showinfo(title, message)
        root.destroy()
    except Exception as e:
        log('warning', f"Could not show message dialog: {e}")


def main():
    """Main entry point with command line argument handling."""
    args = sys.argv[1:]
    test_mode = '--test' in args
    debug_html = '--debug-html' in args

    # ---- Utility flags (no console assumed — see _notify) ----
    if '--install' in args:
        reset_hour = MigakuEnforcer().config.get('reset_hour', DEFAULT_RESET_HOUR)
        install_startup(reset_hour)
        _notify("Startup task installed. Migaku Enforcer will start automatically when you log in.")
        return
    if '--uninstall' in args:
        uninstall_startup()
        _notify("Startup task removed.")
        return
    if '--help' in args:
        _notify("""Migaku Study Enforcer - Usage:

  migaku_enforcer.exe              Run normally (hides terminal window)
  migaku_enforcer.exe --test       Test mode: GUI shown, nothing blocked
  migaku_enforcer.exe --debug-html Visible browser + save page HTML for diagnosis
  migaku_enforcer.exe --reset      Clear today's "done" state and re-check reviews
  migaku_enforcer.exe --install    Install Windows startup task
  migaku_enforcer.exe --uninstall  Remove startup task
  migaku_enforcer.exe --help       This help

First run shows a setup wizard for your Migaku login and blocking preferences.
Admin privileges required for website blocking.""")
        return

    if '--reset' in args:
        try:
            _enforcer = MigakuEnforcer()
            _enforcer.config['restrictions_disabled_until'] = None
            _enforcer.config['consecutive_errors'] = 0
            _enforcer.save_config()
            _notify("Config reset: today's progress cleared. Reviews will be re-checked now.")
        except Exception as _e:
            _notify(f"Could not reset config: {_e}", is_error=True)
        return

    # ---- Production mode: eliminate the closeable terminal window ----
    # By relaunching via pythonw.exe the console disappears entirely.
    # There is then no [X] button for the user to click.
    # Not needed (and not possible) in a frozen build: sys.executable IS the app
    # itself there, and a --windowed PyInstaller build never has a console to begin
    # with, so this whole relaunch dance is dev-run-only.
    if (not test_mode and '--debug-html' not in args and '--no-relaunch' not in args
            and not getattr(sys, 'frozen', False)):
        exe = sys.executable
        if exe.lower().endswith('python.exe'):
            pythonw = exe[:-len('python.exe')] + 'pythonw.exe'
            if Path(pythonw).exists():
                script = os.path.abspath(__file__)
                subprocess.Popen(
                    [pythonw, script, '--no-relaunch'],
                    creationflags=subprocess.DETACHED_PROCESS,
                )
                print("Migaku Enforcer launched without a terminal window.")
                print("The GUI window will appear shortly.")
                print("Use Task Manager (carefully) if you ever need to force-stop it.")
                sys.exit(0)

    # ---- Set up logging ----
    setup_logging(test_mode=test_mode or debug_html)

    # ---- Admin check ----
    if not check_admin_privileges():
        if test_mode:
            print("WARNING: Not running as administrator! Website blocking will not work.")
        else:
            try:
                _r = tk.Tk()
                _r.withdraw()
                messagebox.showwarning(
                    "Migaku Enforcer",
                    "Not running as administrator!\n"
                    "Website blocking requires admin privileges.\n\n"
                    "Right-click the script and choose 'Run as administrator'."
                )
                _r.destroy()
            except Exception:
                pass

    if test_mode:
        show_startup_banner()
        print("\n[TEST MODE] No websites will be blocked, no apps will be killed.\n")

    # ---- Create enforcer ----
    enforcer = MigakuEnforcer()
    enforcer.test_mode = test_mode or debug_html  # debug implies test-like console
    enforcer.headless = not debug_html  # visible browser when debugging
    enforcer._debug_html = debug_html

    # ---- First-run setup wizard ----
    # Triggered whenever onboarding hasn't been completed yet. Skipped for
    # '--scheduled' launches (Task Scheduler, unattended — no one is present to
    # click through a wizard) so an unfinished setup just logs and exits quietly
    # rather than popping a dialog with no context at logon.
    if not enforcer.config.get('onboarding_completed'):
        if '--scheduled' in args:
            log('warning', "Onboarding not completed; skipping scheduled run.")
            return
        try:
            from onboarding_wizard import WizardWindow
            wizard = WizardWindow(enforcer)
            wizard.run()
        except Exception as e:
            log('error', f"Onboarding wizard failed: {e}")
            _notify(f"Setup wizard failed to start: {e}", is_error=True)
            return
        if not enforcer.config.get('onboarding_completed'):
            log('info', "Setup cancelled by user.")
            return

    if debug_html:
        print("[DEBUG] Browser will be visible. Page HTML/text saved to migaku_debug.html/.txt after check.")
        print("[DEBUG] This mode forces test_mode (no actual blocking).\n")

    # Clear any stale restrictions on startup
    if enforcer.check_if_restrictions_currently_active() and not test_mode:
        enforcer.modify_hosts_file(block=False)
        enforcer._websites_blocked = False

    # ---- Start enforcement loop in background ----
    enforcement_thread = threading.Thread(
        target=enforcer.enforce_restrictions,
        name="EnforcementThread",
        daemon=True,
    )
    enforcement_thread.start()

    # ---- Show the GUI window (blocks until closed) ----
    try:
        window = MigakuStatusWindow(enforcer, test_mode=test_mode)
        window.run()
    except Exception as e:
        log('error', f"GUI failed to start: {e}")
        # Fallback: keep enforcement running headlessly until interrupted
        try:
            enforcement_thread.join()
        except KeyboardInterrupt:
            pass

    enforcer.cleanup()


if __name__ == "__main__":
    main()
