"""
Settings dialog — reopenable version of the onboarding wizard's data, without the
step-by-step framing. Opened from MigakuStatusWindow's "Settings" button.

Edits the *live* MigakuEnforcer.config of the already-running enforcer (not a
throwaway instance like the wizard uses for Test Login), and applies domain-list
changes to the hosts file immediately if restrictions are currently active,
instead of waiting for the next hourly enforcement-loop tick.
"""

import tkinter as tk
from tkinter import messagebox

from gui_theme import (
    BG, FG, FG_MUTED, FG_GOOD, FG_BAD, ACCENT, BUTTON_BG,
    FONT_TITLE, FONT_HEADING, FONT_BODY, FONT_SMALL,
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
    check_admin_privileges, install_startup, uninstall_startup,
)

WINDOW_WIDTH = 460

TABS = ["Account", "Blocking", "Review", "Startup"]


class SettingsWindow(tk.Toplevel):
    def __init__(self, parent, enforcer, log_callback=None):
        super().__init__(parent)
        self.enforcer = enforcer
        self._log_callback = log_callback or (lambda msg: None)

        self.title("Migaku Enforcer — Settings")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.attributes('-topmost', True)
        self.transient(parent)
        self.grab_set()

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
        self._startup_var = tk.BooleanVar(
            value=bool(self.enforcer.config.get('install_to_startup', False)))

        self._build_shell()
        self._show_tab(0)

        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")
        self.focus_force()

    # ------------------------------------------------------------------ #
    #  Shell / tabs                                                        #
    # ------------------------------------------------------------------ #

    def _build_shell(self):
        header = tk.Frame(self, bg=BG, padx=18, pady=12)
        header.pack(fill='x')
        tk.Label(header, text="SETTINGS", font=FONT_TITLE, fg=ACCENT, bg=BG).pack()

        tab_bar = tk.Frame(header, bg=BG)
        tab_bar.pack(pady=(8, 0))
        self._tab_buttons = []
        for i, name in enumerate(TABS):
            btn = tk.Button(tab_bar, text=name, command=lambda i=i: self._show_tab(i),
                             bg=BUTTON_BG, fg=FG, font=FONT_SMALL, relief='flat',
                             padx=12, pady=5, cursor='hand2',
                             activebackground='#1e3a5f', activeforeground='white')
            btn.pack(side='left', padx=3)
            self._tab_buttons.append(btn)

        make_separator(header, pady=(10, 0))

        self.content = tk.Frame(self, bg=BG, padx=18, pady=10, width=WINDOW_WIDTH)
        self.content.pack(fill='both', expand=True)

        footer = tk.Frame(self, bg=BG, padx=18, pady=12)
        footer.pack(fill='x')
        make_separator(footer, pady=(0, 10))
        nav = tk.Frame(footer, bg=BG)
        nav.pack(fill='x')

        tk.Button(nav, text="Cancel", command=self.destroy,
                  bg=BG, fg=FG_MUTED, font=FONT_SMALL, relief='flat',
                  cursor='hand2', bd=0).pack(side='left')
        make_dark_button(nav, "Save", self._on_save,
                          bg=ACCENT, hover='#ff6b81').pack(side='right')

        self.tabs = [None] * len(TABS)

    def _show_tab(self, index):
        for frame in self.tabs:
            if frame is not None:
                frame.pack_forget()
        for i, btn in enumerate(self._tab_buttons):
            btn.config(bg=ACCENT if i == index else BUTTON_BG)

        if self.tabs[index] is None:
            frame = tk.Frame(self.content, bg=BG)
            [self._build_account_tab, self._build_blocking_tab,
             self._build_review_tab, self._build_startup_tab][index](frame)
            self.tabs[index] = frame

        self.tabs[index].pack(fill='both', expand=True)

    # ------------------------------------------------------------------ #
    #  Tabs                                                                #
    # ------------------------------------------------------------------ #

    def _build_account_tab(self, frame):
        creds = self.enforcer.config.get('migaku_credentials', {})
        self._email_var, self._password_var = build_credentials_form(
            frame, creds.get('email', ''), creds.get('password', ''))

        tk.Label(frame, text="Each check opens a hidden browser — expect roughly 30-40 seconds.",
                 font=FONT_SMALL, fg=FG_MUTED, bg=BG, wraplength=WINDOW_WIDTH - 40,
                 justify='left').pack(anchor='w', pady=(4, 8))

        result_label = tk.Label(frame, text="", font=FONT_SMALL, bg=BG,
                                 wraplength=WINDOW_WIDTH - 40, justify='left')

        def on_result(count, error_kind):
            test_btn.config(state='normal', text="Test Login")
            if error_kind is None:
                result_label.config(text=f"✓ Login successful! {count} review(s) pending.",
                                     fg=FG_GOOD)
            elif error_kind == 'chrome_missing':
                result_label.config(text="✗ Google Chrome wasn't found.", fg=FG_BAD)
            else:
                result_label.config(text=f"✗ {error_kind}", fg=FG_BAD)
            result_label.pack(anchor='w', pady=(6, 0))

        def start_test():
            test_btn.config(state='disabled', text="Testing…")
            result_label.config(text="Checking…", fg=FG_MUTED)
            result_label.pack(anchor='w', pady=(6, 0))
            run_test_login(self, self._email_var.get().strip(),
                            self._password_var.get(), on_result)

        test_btn = make_dark_button(frame, "Test Login", start_test)
        test_btn.pack(anchor='w', pady=(10, 0))

    def _build_blocking_tab(self, frame):
        domains = self.enforcer.config.get('blocked_domains') or list(DEFAULT_BLOCKED_DOMAINS)
        self._get_domains = build_string_list_editor(frame, domains, "Blocked websites:")

        apps = self.enforcer.config.get('blocked_apps') or list(DEFAULT_BLOCKED_APPS)
        self._get_apps = build_string_list_editor(frame, apps, "Blocked apps/processes:")

        exact_match = self.enforcer.config.get(
            'blocked_apps_exact_match', DEFAULT_BLOCKED_APPS_EXACT_MATCH)
        self._get_exact_match = build_exact_match_toggle(frame, exact_match)

    def _build_review_tab(self, frame):
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

    def _build_startup_tab(self, frame):
        tk.Label(
            frame, wraplength=WINDOW_WIDTH - 40, justify='left', font=FONT_BODY,
            fg=FG_MUTED, bg=BG,
            text="Start Migaku Enforcer automatically when you log in. Requires "
                 "administrator privileges."
        ).pack(anchor='w', pady=(0, 10))

        tk.Checkbutton(
            frame, text="Start automatically at login", variable=self._startup_var,
            font=FONT_BODY, fg=FG, bg=BG, selectcolor=BG,
            activebackground=BG, activeforeground=FG,
            command=self._on_toggle_startup,
        ).pack(anchor='w')

    def _on_toggle_startup(self):
        # Applies immediately (not deferred to Save) — this toggle reflects real
        # Task Scheduler state, not just a stored preference.
        wants_startup = self._startup_var.get()
        if not check_admin_privileges():
            self._startup_var.set(not wants_startup)  # revert
            messagebox.showwarning(
                "Migaku Enforcer",
                "Administrator privileges are required to change this. Restart "
                "Migaku Enforcer as administrator and try again."
            )
            return

        if wants_startup:
            reset_hour = self.enforcer.config.get('reset_hour', DEFAULT_RESET_HOUR)
            install_startup(reset_hour)
            self._log_callback("Startup enabled: will launch automatically at login.")
        else:
            uninstall_startup()
            self._log_callback("Startup disabled.")
        self.enforcer.config['install_to_startup'] = wants_startup
        self.enforcer.save_config()

    # ------------------------------------------------------------------ #
    #  Save                                                                #
    # ------------------------------------------------------------------ #

    def _on_save(self):
        email = self._email_var.get().strip()
        password = self._password_var.get()
        if not email or not password:
            messagebox.showwarning("Migaku Enforcer Settings",
                                    "Email and password can't be empty.")
            self._show_tab(0)
            return

        old_domains = set(self.enforcer.config.get('blocked_domains', []))
        old_reset_hour = self.enforcer.config.get('reset_hour', DEFAULT_RESET_HOUR)

        self.enforcer.config['migaku_credentials'] = {
            'email': email, 'password': password, 'auto_login': True,
        }
        self.enforcer.config['blocked_domains'] = self._get_domains()
        self.enforcer.config['blocked_apps'] = self._get_apps()
        self.enforcer.config['daily_review_goal'] = self._get_goal()
        self.enforcer.config['reset_hour'] = self._get_reset_hour()
        self.enforcer.config['check_interval_minutes'] = self._get_check_interval()
        self.enforcer.config['emergency_passes_enabled'] = self._get_emergency_enabled()
        self.enforcer.config['emergency_passes_per_month'] = self._get_passes_per_month()
        self.enforcer.config['blocked_apps_exact_match'] = self._get_exact_match()
        self.enforcer.save_config()

        new_domains = set(self.enforcer.config['blocked_domains'])
        self._log_callback(
            f"Settings saved: {len(new_domains)} blocked sites, "
            f"{len(self.enforcer.config['blocked_apps'])} blocked apps, "
            f"goal {self.enforcer.config['daily_review_goal']}/day, "
            f"reset at {self.enforcer._reset_time_label()}.")

        new_reset_hour = self.enforcer.config['reset_hour']
        if (new_reset_hour != old_reset_hour
                and self.enforcer.config.get('install_to_startup')
                and check_admin_privileges()):
            # The scheduled task's daily trigger time is baked in at
            # registration — re-register it so it actually matches the new
            # reset time instead of silently firing at the old one.
            install_startup(new_reset_hour)
            self._log_callback("Startup schedule updated to match the new reset time.")

        if old_domains != new_domains and getattr(self.enforcer, '_websites_blocked', False):
            # Restrictions are active right now and modify_hosts_file(block=True) is
            # normally skipped once _websites_blocked is already True — force a
            # refresh so the new list takes effect immediately instead of waiting
            # for the next hourly enforcement tick.
            if self.enforcer.modify_hosts_file(block=True):
                self._log_callback("Blocked sites updated immediately (restrictions are active).")

        self.destroy()
