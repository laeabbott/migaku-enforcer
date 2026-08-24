"""
Shared, reusable Tk form-building blocks for the onboarding wizard and Settings
dialog. Pure widget construction + a couple of behaviors (test-login threading) —
deliberately NOT shared "page" classes, since the wizard's step-by-step framing
and the Settings dialog's all-at-once tabbed framing are structurally different.
"""

import logging
import threading
import tkinter as tk

from gui_theme import (
    BG, BG_PANEL, FG, FG_MUTED, FONT_BODY, FONT_SMALL, make_dark_button,
)
from migaku_enforcer import (
    DEFAULT_DAILY_REVIEW_GOAL, DEFAULT_RESET_HOUR, DEFAULT_EMERGENCY_PASSES_ENABLED,
    DEFAULT_EMERGENCY_PASSES_PER_MONTH, DEFAULT_CHECK_INTERVAL_MINUTES,
    DEFAULT_BLOCKED_APPS_EXACT_MATCH,
)

HOUR_LABELS = tuple(
    f"{h % 12 or 12}:00 {'AM' if h < 12 else 'PM'}" for h in range(24)
)


def build_credentials_form(parent, email='', password=''):
    """Email + password fields. Returns (email_var, password_var) StringVars."""
    frame = tk.Frame(parent, bg=BG)
    frame.pack(fill='x')

    tk.Label(frame, text="Migaku email", font=FONT_SMALL, fg=FG_MUTED, bg=BG).pack(anchor='w')
    email_var = tk.StringVar(value=email)
    tk.Entry(frame, textvariable=email_var, font=FONT_BODY, bg=BG_PANEL, fg=FG,
              insertbackground=FG, relief='flat').pack(fill='x', ipady=4, pady=(0, 8))

    tk.Label(frame, text="Migaku password", font=FONT_SMALL, fg=FG_MUTED, bg=BG).pack(anchor='w')
    password_var = tk.StringVar(value=password)
    tk.Entry(frame, textvariable=password_var, font=FONT_BODY, bg=BG_PANEL, fg=FG,
              insertbackground=FG, relief='flat', show='*').pack(fill='x', ipady=4)

    return email_var, password_var


def build_string_list_editor(parent, items, label):
    """
    A listbox + add/remove row for editing a list of strings. Used for both
    blocked domains and blocked apps/processes — same shape, just relabeled.
    Returns get_items() -> list[str].
    """
    wrapper = tk.Frame(parent, bg=BG)
    wrapper.pack(fill='both', expand=True, pady=(0, 8))

    tk.Label(wrapper, text=label, font=FONT_SMALL, fg=FG_MUTED, bg=BG).pack(anchor='w')

    list_frame = tk.Frame(wrapper, bg=BG)
    list_frame.pack(fill='both', expand=True)

    listbox = tk.Listbox(list_frame, height=6, bg=BG_PANEL, fg=FG,
                          font=('Courier', 9), relief='flat',
                          selectbackground='#1e3a5f', activestyle='none')
    scrollbar = tk.Scrollbar(list_frame, command=listbox.yview)
    listbox.configure(yscrollcommand=scrollbar.set)
    listbox.pack(side='left', fill='both', expand=True)
    scrollbar.pack(side='right', fill='y')

    for item in items:
        listbox.insert('end', item)

    entry_row = tk.Frame(wrapper, bg=BG)
    entry_row.pack(fill='x', pady=(4, 0))

    entry_var = tk.StringVar()
    entry = tk.Entry(entry_row, textvariable=entry_var, font=FONT_BODY, bg=BG_PANEL, fg=FG,
                      insertbackground=FG, relief='flat')
    entry.pack(side='left', fill='x', expand=True, ipady=3, padx=(0, 6))

    def add_item(_event=None):
        value = entry_var.get().strip()
        if value and value not in listbox.get(0, 'end'):
            listbox.insert('end', value)
            entry_var.set('')

    def remove_selected():
        for index in reversed(listbox.curselection()):
            listbox.delete(index)

    entry.bind('<Return>', add_item)
    make_dark_button(entry_row, "Add", add_item, padx=10, pady=3).pack(side='left', padx=(0, 4))
    make_dark_button(entry_row, "Remove Selected", remove_selected,
                      bg='#333333', hover='#555555', padx=10, pady=3).pack(side='left')

    def get_items():
        return list(listbox.get(0, 'end'))

    return get_items


def build_goal_control(parent, current_goal):
    """Daily review goal spinner. Returns get_goal() -> int."""
    frame = tk.Frame(parent, bg=BG)
    frame.pack(fill='x', pady=(0, 8))

    tk.Label(frame,
             text=("All restrictions are lifted when you have 0 remaining reviews, "
                   "or when you have completed this many review cards:"),
             font=FONT_SMALL, fg=FG_MUTED, bg=BG, wraplength=380, justify='left').pack(anchor='w')

    goal_var = tk.IntVar(value=current_goal or DEFAULT_DAILY_REVIEW_GOAL)
    tk.Spinbox(frame, from_=1, to=9999, textvariable=goal_var, width=8,
               font=FONT_BODY, bg=BG_PANEL, fg=FG, insertbackground=FG,
               relief='flat', buttonbackground=BG_PANEL).pack(anchor='w', pady=(4, 0))

    def get_goal():
        try:
            value = int(goal_var.get())
            return value if value > 0 else DEFAULT_DAILY_REVIEW_GOAL
        except (ValueError, tk.TclError):
            return DEFAULT_DAILY_REVIEW_GOAL

    return get_goal


def build_reset_hour_control(parent, current_hour):
    """
    Daily reset-time picker (what used to be a hardcoded 4 AM everywhere).
    Returns get_reset_hour() -> int (0-23).
    """
    frame = tk.Frame(parent, bg=BG)
    frame.pack(fill='x', pady=(0, 8))

    tk.Label(frame,
             text="Reset time — restrictions lift for the day at this time, and the "
                  "next day's tracking starts fresh then:",
             font=FONT_SMALL, fg=FG_MUTED, bg=BG, wraplength=380, justify='left').pack(anchor='w')

    # A readonly Spinbox with values= doesn't reliably honor its textvariable's
    # initial value (it can silently show values[0] instead) — OptionMenu does,
    # so use that instead for a default that actually reflects current_hour.
    hour_var = tk.StringVar(value=HOUR_LABELS[current_hour if current_hour in range(24) else DEFAULT_RESET_HOUR])
    menu = tk.OptionMenu(frame, hour_var, *HOUR_LABELS)
    menu.config(bg=BG_PANEL, fg=FG, font=FONT_BODY, relief='flat', width=10,
                highlightthickness=0, activebackground='#1e3a5f', activeforeground=FG)
    menu['menu'].config(bg=BG_PANEL, fg=FG)
    menu.pack(anchor='w', pady=(4, 0))

    def get_reset_hour():
        try:
            return HOUR_LABELS.index(hour_var.get())
        except ValueError:
            return DEFAULT_RESET_HOUR

    return get_reset_hour


def build_emergency_passes_toggle(parent, enabled, passes_per_month=None):
    """
    Enable/disable the Emergency Pass feature, plus how many are granted per
    month. Returns (get_enabled, get_passes_per_month).
    """
    frame = tk.Frame(parent, bg=BG)
    frame.pack(fill='x', pady=(0, 8))

    enabled_var = tk.BooleanVar(value=enabled if enabled is not None else DEFAULT_EMERGENCY_PASSES_ENABLED)
    tk.Checkbutton(
        frame, text="Allow Emergency Passes (lets you through when truly stuck)",
        variable=enabled_var, font=FONT_BODY, fg=FG, bg=BG, selectcolor=BG,
        activebackground=BG, activeforeground=FG,
    ).pack(anchor='w')
    tk.Label(frame, text="Turn this off if emergency passes tempt you to cheat.",
             font=FONT_SMALL, fg=FG_MUTED, bg=BG, wraplength=380, justify='left').pack(anchor='w')

    count_row = tk.Frame(frame, bg=BG)
    count_row.pack(anchor='w', pady=(6, 0))
    tk.Label(count_row, text="Passes per month:", font=FONT_SMALL, fg=FG_MUTED, bg=BG).pack(side='left')
    count_var = tk.IntVar(value=passes_per_month or DEFAULT_EMERGENCY_PASSES_PER_MONTH)
    tk.Spinbox(count_row, from_=0, to=31, textvariable=count_var, width=5,
               font=FONT_BODY, bg=BG_PANEL, fg=FG, insertbackground=FG,
               relief='flat', buttonbackground=BG_PANEL).pack(side='left', padx=(6, 0))

    def get_enabled():
        return enabled_var.get()

    def get_passes_per_month():
        try:
            value = int(count_var.get())
            return value if value >= 0 else DEFAULT_EMERGENCY_PASSES_PER_MONTH
        except (ValueError, tk.TclError):
            return DEFAULT_EMERGENCY_PASSES_PER_MONTH

    return get_enabled, get_passes_per_month


def build_check_interval_control(parent, current_minutes):
    """How often (in minutes) the background loop checks your review count.
    Returns get_interval_minutes() -> int."""
    frame = tk.Frame(parent, bg=BG)
    frame.pack(fill='x', pady=(0, 8))

    tk.Label(frame,
             text="Check reviews every this many minutes (lower = more responsive, "
                  "but checks Migaku's site more often):",
             font=FONT_SMALL, fg=FG_MUTED, bg=BG, wraplength=380, justify='left').pack(anchor='w')

    minutes_var = tk.IntVar(value=current_minutes or DEFAULT_CHECK_INTERVAL_MINUTES)
    tk.Spinbox(frame, from_=5, to=1440, increment=5, textvariable=minutes_var, width=8,
               font=FONT_BODY, bg=BG_PANEL, fg=FG, insertbackground=FG,
               relief='flat', buttonbackground=BG_PANEL).pack(anchor='w', pady=(4, 0))

    def get_interval_minutes():
        try:
            value = int(minutes_var.get())
            return value if value >= 1 else DEFAULT_CHECK_INTERVAL_MINUTES
        except (ValueError, tk.TclError):
            return DEFAULT_CHECK_INTERVAL_MINUTES

    return get_interval_minutes


def build_exact_match_toggle(parent, enabled):
    """
    Blocked-apps matching mode: substring (default, matches "chrome" against
    "Google Chrome.exe") vs exact (only matches the literal process name).
    Returns get_exact_match() -> bool.
    """
    frame = tk.Frame(parent, bg=BG)
    frame.pack(fill='x', pady=(0, 8))

    exact_var = tk.BooleanVar(value=enabled if enabled is not None else DEFAULT_BLOCKED_APPS_EXACT_MATCH)
    tk.Checkbutton(
        frame, text="Match blocked app names exactly", variable=exact_var,
        font=FONT_BODY, fg=FG, bg=BG, selectcolor=BG,
        activebackground=BG, activeforeground=FG,
    ).pack(anchor='w')
    tk.Label(
        frame,
        text=("Off (default): \"steam\" also matches any process containing that "
              "text. On: only matches \"steam\"/\"steam.exe\" exactly. "
              "chromedriver.exe (used by this app) is never blocked either way."),
        font=FONT_SMALL, fg=FG_MUTED, bg=BG, wraplength=380, justify='left'
    ).pack(anchor='w')

    return lambda: exact_var.get()


def _diagnose_login_failure(captured: list) -> str:
    """
    Turn the warning/error log lines captured during a failed check into a
    specific, actionable reason instead of one generic "login failed" message
    for every possible failure. setup_logging() always lets WARNING/ERROR
    through regardless of --test mode, and every failure path in
    get_review_count()/login_to_migaku()/setup_webdriver() logs at one of
    those two levels, so this has real signal to work with even in production
    mode (where INFO-level success traces are suppressed, but that's fine —
    only the failure messages matter here).
    """
    text = " ".join(captured).lower()

    if 'chrome' in text and ('binary' in text or 'cannot find' in text):
        return 'chrome_missing'

    if any(code in text for code in (
        'err_internet_disconnected', 'err_name_not_resolved',
        'err_connection_refused', 'err_connection_timed_out',
        'err_connection_reset', 'net::err_'
    )):
        return ("Couldn't reach study.migaku.com — check your internet connection "
                "and try again.")

    if 'webdriver setup failed' in text:
        return ("Couldn't start the browser Migaku Enforcer uses to check your "
                "reviews (this is a technical/driver problem, not your email or "
                "password). Try again, or make sure Chrome is up to date.")

    if 'all attempts failed' in text or 'could not find review count' in text:
        return ("Couldn't verify your login. This usually means the email or "
                "password is incorrect — double-check them and try again. (If "
                "you're sure they're right, Migaku's site may be temporarily "
                "unavailable, or its page layout changed.)")

    # Fall back to whatever the most specific captured line was, rather than a
    # single generic message that could be true or completely wrong for any
    # given failure.
    for message in reversed(captured):
        if message.strip():
            return f"Something went wrong while checking your reviews. Details: {message}"

    return "Something went wrong while checking your reviews (no further details were logged)."


def run_test_login(parent, email, password, on_result):
    """
    Test Migaku credentials in a background thread without blocking the UI or
    touching the saved config file. Builds a throwaway MigakuEnforcer, overwrites
    its in-memory credentials only, reuses get_review_count()/cleanup() unmodified.

    on_result(count, error_kind) is called back on the Tk main thread once done:
      count        -- the review count, or -1 on failure
      error_kind   -- None on success; 'chrome_missing' if Chrome wasn't found
                       (caller shows a download link for that one); otherwise a
                       specific human-readable reason from _diagnose_login_failure
    """
    def worker():
        from migaku_enforcer import MigakuEnforcer

        captured = []

        class _Capture(logging.Handler):
            def emit(self, record):
                captured.append(record.getMessage())

        enforcer = None
        target_logger = logging.getLogger('migaku_enforcer')
        handler = _Capture()
        target_logger.addHandler(handler)
        try:
            enforcer = MigakuEnforcer()
            enforcer.test_mode = True
            enforcer.headless = True
            enforcer.config['migaku_credentials'] = {
                'email': email, 'password': password, 'auto_login': True
            }
            count = enforcer.get_review_count()
        except Exception as e:
            # Defensive: get_review_count() itself always catches its own
            # errors and returns -1, but if something truly unexpected slips
            # through, still resolve on_result instead of leaving the button
            # stuck on "Testing…" forever with no explanation.
            count = -1
            captured.append(f"Unexpected error: {type(e).__name__}: {e}")
        finally:
            target_logger.removeHandler(handler)
            if enforcer is not None:
                enforcer.cleanup()

        error_kind = _diagnose_login_failure(captured) if count == -1 else None
        parent.after(0, lambda: on_result(count, error_kind))

    threading.Thread(target=worker, daemon=True).start()
