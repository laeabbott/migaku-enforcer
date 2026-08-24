"""
First-run setup wizard for Migaku Enforcer.

Replaces the old console-based setup_credentials.py. Walks a new user through
Migaku credentials, a live test login, and blocking preferences. Nothing is
written to config.json until the Finish step — closing the wizard early leaves
no partial state.
"""

import tkinter as tk
import webbrowser
from tkinter import messagebox

from gui_theme import (
    BG, FG, FG_MUTED, FG_GOOD, FG_BAD, ACCENT, SEPARATOR,
    FONT_TITLE, FONT_HEADING, FONT_BODY, FONT_SMALL, FONT_SMALL_ITALIC,
    make_dark_button, make_separator,
)
from config_forms import (
    build_credentials_form, build_string_list_editor, build_goal_control,
    build_reset_hour_control, build_emergency_passes_toggle,
    build_check_interval_control, build_exact_match_toggle, run_test_login,
)
from migaku_enforcer import (
    DEFAULT_BLOCKED_DOMAINS, DEFAULT_BLOCKED_APPS, DEFAULT_DAILY_REVIEW_GOAL,
    DEFAULT_RESET_HOUR, DEFAULT_EMERGENCY_PASSES_ENABLED,
    DEFAULT_EMERGENCY_PASSES_PER_MONTH, DEFAULT_CHECK_INTERVAL_MINUTES,
    DEFAULT_BLOCKED_APPS_EXACT_MATCH,
    check_admin_privileges, install_startup,
)

WINDOW_WIDTH = 480


class WizardWindow(tk.Tk):
    def __init__(self, enforcer):
        super().__init__()
        self.enforcer = enforcer

        self.title("Migaku Enforcer — Setup")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self._email_var = None
        self._password_var = None
        self._get_domains = None
        self._get_apps = None
        self._get_goal = None
        self._get_reset_hour = None
        self._get_emergency_enabled = None
        self._get_passes_per_month = None
        self._get_check_interval = None
        self._get_exact_match = None
        self._startup_var = tk.BooleanVar(value=False)

        self.steps = [
            {'title': 'Welcome', 'build': self._step_welcome},
            {'title': 'Migaku Account', 'build': self._step_credentials,
             'validate': self._validate_credentials},
            {'title': 'Test Login', 'build': self._step_test_login},
            {'title': 'Blocked Websites', 'build': self._step_blocked_sites},
            {'title': 'Blocked Apps', 'build': self._step_blocked_apps},
            {'title': 'Review Settings', 'build': self._step_goal},
            {'title': 'Start at Login', 'build': self._step_startup},
            {'title': 'Finish', 'build': self._step_finish},
        ]
        self.frames = [None] * len(self.steps)
        self.index = 0

        self._build_shell()
        self._show_step(0)

        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")

    def run(self):
        self.mainloop()

    # ------------------------------------------------------------------ #
    #  Shell / navigation                                                  #
    # ------------------------------------------------------------------ #

    def _build_shell(self):
        header = tk.Frame(self, bg=BG, padx=20, pady=14)
        header.pack(fill='x')
        tk.Label(header, text="MIGAKU ENFORCER SETUP", font=FONT_TITLE,
                 fg=ACCENT, bg=BG).pack()
        self.progress_label = tk.Label(header, text="", font=FONT_SMALL_ITALIC,
                                        fg=FG_MUTED, bg=BG)
        self.progress_label.pack(pady=(2, 0))
        make_separator(header)

        self.content = tk.Frame(self, bg=BG, padx=20, pady=6, width=WINDOW_WIDTH)
        self.content.pack(fill='both', expand=True)
        self.content.pack_propagate(True)

        footer = tk.Frame(self, bg=BG, padx=20, pady=14)
        footer.pack(fill='x')
        make_separator(footer, pady=(0, 10))

        nav = tk.Frame(footer, bg=BG)
        nav.pack(fill='x')

        tk.Button(nav, text="Cancel Setup", command=self._cancel,
                  bg=BG, fg=FG_MUTED, font=FONT_SMALL, relief='flat',
                  cursor='hand2', bd=0).pack(side='left')

        self.next_btn = make_dark_button(nav, "Next →", self._go_next,
                                          bg=ACCENT, hover='#ff6b81')
        self.next_btn.pack(side='right', padx=(6, 0))
        self.back_btn = make_dark_button(nav, "← Back", self._go_back)
        self.back_btn.pack(side='right')

    def _show_step(self, index):
        for frame in self.frames:
            if frame is not None:
                frame.pack_forget()

        if self.frames[index] is None:
            frame = tk.Frame(self.content, bg=BG)
            self.steps[index]['build'](frame)
            self.frames[index] = frame

        self.frames[index].pack(fill='both', expand=True)
        self.index = index

        step = self.steps[index]
        self.progress_label.config(
            text=f"Step {index + 1} of {len(self.steps)} — {step['title']}")
        self.back_btn.config(state='normal' if index > 0 else 'disabled')
        self.next_btn.config(text="Finish" if index == len(self.steps) - 1 else "Next →")

    def _go_next(self):
        if self.index == len(self.steps) - 1:
            self._on_finish()
            return

        validate = self.steps[self.index].get('validate')
        if validate:
            ok, message = validate()
            if not ok:
                messagebox.showwarning("Migaku Enforcer Setup", message)
                return

        self._show_step(self.index + 1)

    def _go_back(self):
        if self.index > 0:
            self._show_step(self.index - 1)

    def _cancel(self):
        if messagebox.askyesno(
            "Cancel Setup",
            "Setup isn't finished. Migaku Enforcer won't run until setup is completed.\n\n"
            "Cancel setup for now?"
        ):
            self.destroy()

    # ------------------------------------------------------------------ #
    #  Steps                                                               #
    # ------------------------------------------------------------------ #

    def _step_welcome(self, frame):
        tk.Label(frame, text="Welcome!", font=FONT_HEADING, fg=FG, bg=BG).pack(
            anchor='w', pady=(10, 6))
        tk.Label(
            frame, wraplength=WINDOW_WIDTH - 40, justify='left', font=FONT_BODY,
            fg=FG_MUTED, bg=BG,
            text=(
                "Migaku Enforcer blocks distracting websites and apps until you've "
                "finished your Migaku flashcard reviews for the day.\n\n"
                "This will take about a minute to set up: your Migaku login, which "
                "sites/apps to block, and your daily review goal."
            )
        ).pack(anchor='w')

    def _step_credentials(self, frame):
        tk.Label(frame, text="Your Migaku account", font=FONT_HEADING, fg=FG, bg=BG).pack(
            anchor='w', pady=(10, 6))
        tk.Label(
            frame, wraplength=WINDOW_WIDTH - 40, justify='left', font=FONT_SMALL,
            fg=FG_MUTED, bg=BG,
            text="Used to check your review count on study.migaku.com. Stored locally "
                 "on this computer only."
        ).pack(anchor='w', pady=(0, 10))

        creds = self.enforcer.config.get('migaku_credentials', {})
        self._email_var, self._password_var = build_credentials_form(
            frame, creds.get('email', ''), creds.get('password', ''))

    def _validate_credentials(self):
        if not self._email_var.get().strip():
            return False, "Please enter your Migaku email address."
        if not self._password_var.get():
            return False, "Please enter your Migaku password."
        return True, ""

    def _step_test_login(self, frame):
        tk.Label(frame, text="Test your login", font=FONT_HEADING, fg=FG, bg=BG).pack(
            anchor='w', pady=(10, 6))
        tk.Label(
            frame, wraplength=WINDOW_WIDTH - 40, justify='left', font=FONT_SMALL,
            fg=FG_MUTED, bg=BG,
            text="Optional, but recommended — makes sure Migaku Enforcer can actually "
                 "read your review count before you finish setup.\n\n"
                 "Each check opens a hidden browser and loads study.migaku.com, so it "
                 "takes roughly 30-40 seconds — that's normal, just wait for it."
        ).pack(anchor='w', pady=(0, 10))

        result_label = tk.Label(frame, text="", font=FONT_BODY, bg=BG,
                                 wraplength=WINDOW_WIDTH - 40, justify='left')
        result_label.pack(anchor='w', pady=(8, 4))

        chrome_link = tk.Label(frame, text="Open Chrome download page →",
                                font=FONT_SMALL, fg=ACCENT, bg=BG, cursor='hand2')

        def open_chrome_page(_event=None):
            webbrowser.open("https://www.google.com/chrome/")

        chrome_link.bind('<Button-1>', open_chrome_page)

        def on_result(count, error_kind):
            test_btn.config(state='normal', text="Test Login")
            chrome_link.pack_forget()
            if error_kind is None:
                result_label.config(
                    text=f"✓ Login successful! You have {count} review(s) pending.",
                    fg=FG_GOOD)
            elif error_kind == 'chrome_missing':
                result_label.config(
                    text="✗ Google Chrome wasn't found. Migaku Enforcer needs Chrome "
                         "installed to check your reviews.", fg=FG_BAD)
                chrome_link.pack(anchor='w', pady=(2, 0))
            else:
                result_label.config(text=f"✗ {error_kind}", fg=FG_BAD)

        def start_test():
            test_btn.config(state='disabled', text="Testing…")
            result_label.config(text="Checking your Migaku login…", fg=FG_MUTED)
            chrome_link.pack_forget()
            run_test_login(self, self._email_var.get().strip(),
                            self._password_var.get(), on_result)

        test_btn = make_dark_button(frame, "Test Login", start_test)
        test_btn.pack(anchor='w')

    def _step_blocked_sites(self, frame):
        tk.Label(frame, text="Blocked websites", font=FONT_HEADING, fg=FG, bg=BG).pack(
            anchor='w', pady=(10, 6))
        tk.Label(
            frame, wraplength=WINDOW_WIDTH - 40, justify='left', font=FONT_SMALL,
            fg=FG_MUTED, bg=BG,
            text="These sites are blocked (via your hosts file) whenever reviews are "
                 "pending. Edit the list to fit you — add or remove any site."
        ).pack(anchor='w', pady=(0, 10))

        domains = self.enforcer.config.get('blocked_domains') or list(DEFAULT_BLOCKED_DOMAINS)
        self._get_domains = build_string_list_editor(frame, domains, "Blocked domains:")

    def _step_blocked_apps(self, frame):
        tk.Label(frame, text="Blocked apps", font=FONT_HEADING, fg=FG, bg=BG).pack(
            anchor='w', pady=(10, 6))
        tk.Label(
            frame, wraplength=WINDOW_WIDTH - 40, justify='left', font=FONT_SMALL,
            fg=FG_MUTED, bg=BG,
            text="These apps are closed automatically whenever reviews are pending. "
                 "Match on part of the process name (e.g. \"steam\" matches steam.exe)."
        ).pack(anchor='w', pady=(0, 10))

        apps = self.enforcer.config.get('blocked_apps') or list(DEFAULT_BLOCKED_APPS)
        self._get_apps = build_string_list_editor(frame, apps, "Blocked apps/processes:")

        exact_match = self.enforcer.config.get(
            'blocked_apps_exact_match', DEFAULT_BLOCKED_APPS_EXACT_MATCH)
        self._get_exact_match = build_exact_match_toggle(frame, exact_match)

    def _step_goal(self, frame):
        tk.Label(frame, text="Review settings", font=FONT_HEADING, fg=FG, bg=BG).pack(
            anchor='w', pady=(10, 6))
        goal = self.enforcer.config.get('daily_review_goal', DEFAULT_DAILY_REVIEW_GOAL)
        self._get_goal = build_goal_control(frame, goal)

        reset_hour = self.enforcer.config.get('reset_hour', DEFAULT_RESET_HOUR)
        self._get_reset_hour = build_reset_hour_control(frame, reset_hour)

        interval = self.enforcer.config.get(
            'check_interval_minutes', DEFAULT_CHECK_INTERVAL_MINUTES)
        self._get_check_interval = build_check_interval_control(frame, interval)

        emergency_enabled = self.enforcer.config.get(
            'emergency_passes_enabled', DEFAULT_EMERGENCY_PASSES_ENABLED)
        passes_per_month = self.enforcer.config.get(
            'emergency_passes_per_month', DEFAULT_EMERGENCY_PASSES_PER_MONTH)
        self._get_emergency_enabled, self._get_passes_per_month = build_emergency_passes_toggle(
            frame, emergency_enabled, passes_per_month)

    def _step_startup(self, frame):
        tk.Label(frame, text="Start automatically", font=FONT_HEADING, fg=FG, bg=BG).pack(
            anchor='w', pady=(10, 6))
        tk.Label(
            frame, wraplength=WINDOW_WIDTH - 40, justify='left', font=FONT_SMALL,
            fg=FG_MUTED, bg=BG,
            text="Recommended — starts Migaku Enforcer automatically when you log in, "
                 "so it can't be skipped by just not opening it. Requires administrator "
                 "privileges (you may see a permissions prompt)."
        ).pack(anchor='w', pady=(0, 10))

        tk.Checkbutton(
            frame, text="Start Migaku Enforcer automatically when I log in",
            variable=self._startup_var, font=FONT_BODY, fg=FG, bg=BG,
            selectcolor=BG, activebackground=BG, activeforeground=FG,
        ).pack(anchor='w')

    def _step_finish(self, frame):
        tk.Label(frame, text="All set!", font=FONT_HEADING, fg=FG_GOOD, bg=BG).pack(
            anchor='w', pady=(10, 6))
        tk.Label(
            frame, wraplength=WINDOW_WIDTH - 40, justify='left', font=FONT_BODY,
            fg=FG_MUTED, bg=BG,
            text="Click Finish to save your settings and start Migaku Enforcer.\n\n"
                 "Your Migaku password is stored in a local config file on this "
                 "computer, protected by your Windows account's file permissions — "
                 "don't use this on a shared computer.\n\n"
                 "You can change any of these settings later from the Settings button."
        ).pack(anchor='w')

    # ------------------------------------------------------------------ #
    #  Finish                                                              #
    # ------------------------------------------------------------------ #

    def _on_finish(self):
        ok, message = self._validate_credentials()
        if not ok:
            messagebox.showwarning("Migaku Enforcer Setup", message)
            self._show_step(1)
            return

        self.enforcer.config['migaku_credentials'] = {
            'email': self._email_var.get().strip(),
            'password': self._password_var.get(),
            'auto_login': True,
        }
        self.enforcer.config['blocked_domains'] = self._get_domains()
        self.enforcer.config['blocked_apps'] = self._get_apps()
        self.enforcer.config['daily_review_goal'] = self._get_goal()
        self.enforcer.config['reset_hour'] = self._get_reset_hour()
        self.enforcer.config['check_interval_minutes'] = self._get_check_interval()
        self.enforcer.config['emergency_passes_enabled'] = self._get_emergency_enabled()
        self.enforcer.config['emergency_passes_per_month'] = self._get_passes_per_month()
        self.enforcer.config['blocked_apps_exact_match'] = self._get_exact_match()
        self.enforcer.config['onboarding_completed'] = True
        self.enforcer.save_config()

        if self._startup_var.get():
            if check_admin_privileges():
                install_startup(self.enforcer.config['reset_hour'])
                self.enforcer.config['install_to_startup'] = True
                self.enforcer.save_config()
            else:
                messagebox.showwarning(
                    "Migaku Enforcer Setup",
                    "Administrator privileges are required to start automatically at "
                    "login. You can turn this on later from Settings (right-click and "
                    "\"Run as administrator\" if needed)."
                )

        self.destroy()
