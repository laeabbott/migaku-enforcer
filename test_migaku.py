#!/usr/bin/env python3
"""Simple Migaku Test - DOM scraping for review count detection"""

import sys
import time
import json
import re
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def simple_log(message):
    """Simple logging without emojis to avoid encoding issues"""
    print(f"[{time.strftime('%H:%M:%S')}] {message}")


class SimpleMigakuTester:
    def __init__(self):
        self.config_file = Path.home() / "migaku_enforcer_config.json"
        self.driver = None
        self.load_config()

    def load_config(self):
        """Load configuration"""
        if self.config_file.exists():
            with open(self.config_file, 'r') as f:
                self.config = json.load(f)
        else:
            simple_log(
                "ERROR: No config file found. Run setup_credentials.py first")
            sys.exit(1)

    def setup_webdriver(self):
        """Setup Chrome webdriver"""
        chrome_options = Options()
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")

        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.set_page_load_timeout(30)
            simple_log("WebDriver initialized")
            return True
        except Exception as e:
            simple_log(f"Failed to initialize webdriver: {e}")
            return False

    def login_to_migaku(self):
        """Login and handle language selection"""
        simple_log("Logging into Migaku...")
        self.driver.get("https://study.migaku.com/login")

        try:
            # Wait for and fill login form
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, 'input[type="email"]'))
            )

            email_field = self.driver.find_element(
                By.CSS_SELECTOR, 'input[type="email"]')
            password_field = self.driver.find_element(
                By.CSS_SELECTOR, 'input[type="password"]')
            login_button = self.driver.find_element(
                By.CSS_SELECTOR, 'button.UiButton.-gradient.-full-width')

            email_field.send_keys(self.config['migaku_credentials']['email'])
            password_field.send_keys(
                self.config['migaku_credentials']['password'])
            login_button.click()

            time.sleep(5)  # Wait for redirect

            # Always attempt language selection regardless of URL detection
            return self.select_japanese_language()

        except Exception as e:
            simple_log(f"Login failed: {e}")
            return False

    def select_japanese_language(self):
        """Select Japanese language"""
        simple_log("Selecting Japanese language...")

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
                    simple_log("Japanese selected successfully")
                    time.sleep(3)
                    return True
            except Exception:
                continue

        simple_log("Japanese language selection failed or not needed")
        return True  # Continue anyway

    def test_dom_scraping(self):
        """Extract review count from page elements"""
        simple_log("Extracting review count...")
        time.sleep(5)  # Wait for page load

        try:
            # Combined approach: look for any element containing "reviews"
            selectors = [
                '[class*="StudyBox_container"]',
                '//*[contains(text(), "reviews") or contains(text(), "Reviews")]',
                '[class*="container"], [class*="box"], [class*="card"]'
            ]

            for i, selector in enumerate(selectors):
                try:
                    if selector.startswith('//'):
                        elements = self.driver.find_elements(
                            By.XPATH, selector)
                    else:
                        elements = self.driver.find_elements(
                            By.CSS_SELECTOR, selector)

                    for element in elements:
                        text = element.get_attribute(
                            'textContent') or element.text or ''

                        # Skip if no reviews/reviewed mentioned
                        if 'review' not in text.lower():
                            continue

                        simple_log(f"Found text: '{text.strip()[:100]}...'")

                        # Check for "reviewed" (completed) - means 0 reviews remaining
                        if 'reviewed' in text.lower():
                            reviewed_match = re.search(
                                r'(\d+)\s*reviewed', text, re.IGNORECASE)
                            if reviewed_match:
                                simple_log(
                                    f"SUCCESS: Found {reviewed_match.group(1)} reviewed - 0 reviews remaining")
                                return 0

                        # Extract number before "reviews" (pending)
                        match = re.search(r'(\d+)\s*reviews?',
                                          text, re.IGNORECASE)
                        if match:
                            count = int(match.group(1))
                            simple_log(f"SUCCESS: Review count = {count}")
                            return count

                except Exception as e:
                    simple_log(f"Method {i+1} failed: {e}")
                    continue

            simple_log("Could not find review count")
            return None

        except Exception as e:
            simple_log(f"DOM scraping error: {e}")
            return None

    def run_test(self):
        """Run the complete test"""
        simple_log("=== MIGAKU TEST STARTED ===")

        if not self.setup_webdriver():
            return False

        try:
            # Login and get review count
            if not self.login_to_migaku():
                simple_log("Login failed")
                return False

            review_count = self.test_dom_scraping()

            # Results
            if review_count is not None:
                simple_log(f"SUCCESS: Found {review_count} reviews")
                simple_log("0 reviews = restrictions OFF" if review_count ==
                           0 else f"{review_count} reviews = restrictions ON")
                return True
            else:
                simple_log("FAILED: Could not extract review count")
                input("Check browser manually, then press Enter...")
                return False

        except Exception as e:
            simple_log(f"Test error: {e}")
            return False

        finally:
            if self.driver:
                self.driver.quit()


if __name__ == "__main__":
    tester = SimpleMigakuTester()
    success = tester.run_test()

    if success:
        simple_log("TEST COMPLETED SUCCESSFULLY")
    else:
        simple_log("TEST FAILED - Check the output above for details")
