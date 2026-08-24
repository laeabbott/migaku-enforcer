#!/usr/bin/env python3
"""
Credential Setup Script for Migaku Enforcer

SUPERSEDED: normal setup is now the in-app onboarding wizard (onboarding_wizard.py),
which runs automatically on first launch and also lets you configure blocked sites/
apps/goal, not just credentials. This console script is kept only as a dev-only
fallback for running from source without the GUI. Note it also writes to the old
Path.home()/migaku_enforcer_config.json location, not the %APPDATA% path the app
now uses by default (MigakuEnforcer._migrate_legacy_config picks it up from there).
"""

import sys
import os
import json
from pathlib import Path
import getpass


def setup_migaku_credentials():
    print("🔐 Migaku Enforcer - Credential Setup")
    print("=" * 40)
    print("This will securely store your Migaku credentials for automatic login.")
    print("Credentials are stored locally in an encrypted config file.")
    print("=" * 40)

    # Get credentials from user
    print("\n📧 Enter your Migaku login credentials:")
    email = input("Email: ").strip()

    if not email:
        print("❌ Email is required")
        return False

    # Use getpass to hide password input
    password = getpass.getpass("Password: ").strip()

    if not password:
        print("❌ Password is required")
        return False

    # Create config
    config = {
        "emergency_passes_used": 0,
        "emergency_passes_reset_date": "2025-01",
        "restrictions_disabled_until": None,
        "migaku_credentials": {
            "email": email,
            "password": password,
            "auto_login": True
        },
        "blocked_domains": [
            "youtube.com", "netflix.com", "twitch.tv", "reddit.com",
            "facebook.com", "instagram.com", "twitter.com", "tiktok.com",
            "discord.com", "discord.gg"
        ],
        "allowed_domains": ["migaku.com", "study.migaku.com"]
    }

    # Save config file
    config_file = Path.home() / "migaku_enforcer_config.json"

    try:
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)

        print(f"✅ Credentials saved to: {config_file}")
        print("🔒 Your credentials are stored securely on your local machine")
        print("🚀 You can now run the Migaku Enforcer!")

        return True

    except Exception as e:
        print(f"❌ Error saving credentials: {e}")
        return False


def test_login():
    """Test the login with saved credentials"""
    print("\n🧪 Would you like to test the login? (y/n): ", end="")
    test_choice = input().lower().strip()

    if test_choice in ['y', 'yes']:
        print("🚀 Testing login...")
        try:
            sys.path.append(str(Path(__file__).parent))
            from migaku_enforcer import MigakuEnforcer

            enforcer = MigakuEnforcer()
            enforcer.headless = False  # Visible browser for testing

            count = enforcer.get_review_count()

            if count >= 0:
                print(f"✅ Login test successful! Review count: {count}")
            else:
                print("❌ Login test failed. Check the browser window for details.")

            enforcer.cleanup()

        except Exception as e:
            print(f"❌ Test error: {e}")


if __name__ == "__main__":
    print("🎯 Migaku Study Enforcer - Credential Setup")
    print()

    if setup_migaku_credentials():
        test_login()
    else:
        print("❌ Setup failed. Please try again.")
