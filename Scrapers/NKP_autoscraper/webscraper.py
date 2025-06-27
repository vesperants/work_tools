#!/usr/bin/env python3
"""
Auto-WebScraper for NKP Government Portal
Checks redirected links for new content and sends email notifications
"""

import csv
import requests
import smtplib
import logging
import os
import time
import schedule
import argparse
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from urllib.parse import urlparse, urljoin
from typing import List, Set, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import threading


class WebScraperConfig:
    """Configuration class for the web scraper"""
    
    def __init__(self):
        self.csv_file = "sorted_links.csv"
        self.potential_file = "Potential.txt"
        self.config_file = "config.json"
        self.home_redirect_url = "https://nkp.gov.np/home"
        self.request_timeout = 10
        self.request_delay = 0.2  # seconds between requests (reduced for threading)
        self.max_retries = 3
        self.max_workers = 10  # number of concurrent threads
        self.batch_size = 50  # process links in batches for progress reporting
        
        # Email configuration (will be loaded from config file)
        self.email_config = {}
        
        # Load configuration
        self.load_config()
    
    def load_config(self):
        """Load configuration from config.json"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    self.email_config = config.get('email', {})
        except Exception as e:
            print(f"Warning: Could not load config file: {e}")
    
    def create_default_config(self):
        """Create a default configuration file"""
        default_config = {
            "email": {
                "smtp_server": "smtp.gmail.com",
                "smtp_port": 587,
                "sender_email": "your_email@gmail.com",
                "sender_password": "your_app_password",
                "recipient_email": "recipient@gmail.com"
            }
        }
        
        with open(self.config_file, 'w') as f:
            json.dump(default_config, f, indent=4)
        
        print(f"Created default config file '{self.config_file}'. Please update with your email settings.")


class WebScraper:
    """Main web scraper class"""
    
    def __init__(self, config: WebScraperConfig, test_mode: bool = False):
        self.config = config
        self.test_mode = test_mode
        
        # This session is not used directly in threads, but can be used for non-threaded requests
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        # Setup logging
        self.setup_logging()
        
        # Load existing potential links to avoid duplicates
        self.existing_potential_links = self.load_existing_potential_links()
        
        # Thread-local session for thread safety
        self.thread_local_session = threading.local()
    
    def get_session(self) -> requests.Session:
        """Create a new session if one doesn't exist for the current thread"""
        if not hasattr(self.thread_local_session, "session"):
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            })
            self.thread_local_session.session = session
        return self.thread_local_session.session
    
    def setup_logging(self):
        """Setup logging with date-indexed log files"""
        current_date = datetime.now().strftime("%Y-%m-%d")
        log_filename = f"log_{current_date}.txt"
        
        # Create logs directory if it doesn't exist
        if not os.path.exists('logs'):
            os.makedirs('logs')
        
        log_filepath = os.path.join('logs', log_filename)
        
        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_filepath),
                logging.StreamHandler() if self.test_mode else logging.NullHandler()
            ]
        )
        
        self.logger = logging.getLogger(__name__)
        self.logger.info("=" * 60)
        self.logger.info(f"WebScraper started - {'TEST MODE' if self.test_mode else 'PRODUCTION MODE'}")
        self.logger.info("=" * 60)
    
    def load_existing_potential_links(self) -> Set[str]:
        """Load existing potential links to avoid duplicates"""
        existing_links = set()
        if os.path.exists(self.config.potential_file):
            try:
                with open(self.config.potential_file, 'r') as f:
                    existing_links = {line.strip() for line in f if line.strip()}
                self.logger.info(f"Loaded {len(existing_links)} existing potential links")
            except Exception as e:
                self.logger.error(f"Error loading existing potential links: {e}")
        return existing_links
    
    def read_csv_links(self) -> List[str]:
        """Read redirected links from CSV file"""
        redirected_links = []
        
        try:
            with open(self.config.csv_file, 'r', newline='', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                
                for row_num, row in enumerate(reader, start=2):  # start=2 because of header
                    redirected_link = row.get('Redirected', '').strip()
                    if redirected_link:
                        redirected_links.append(redirected_link)
                
                self.logger.info(f"Read {len(redirected_links)} redirected links from CSV")
                
        except Exception as e:
            self.logger.error(f"Error reading CSV file: {e}")
            raise
        
        return redirected_links
    
    def check_redirect(self, url: str) -> Tuple[str, bool]:
        """
        Check if URL redirects to home page
        Returns (url, is_home_redirect) where is_home_redirect is True if redirects to home
        """
        session = self.get_session()
        
        for attempt in range(self.config.max_retries):
            try:
                self.logger.debug(f"Checking URL (attempt {attempt + 1}): {url}")
                
                response = session.get(
                    url, 
                    timeout=self.config.request_timeout,
                    allow_redirects=True
                )
                
                final_url = response.url.lower().strip('/')
                home_url = self.config.home_redirect_url.lower().strip('/')
                
                # Check if the final URL is the home page.
                # This is more robust against variations in URL (e.g. http vs https, trailing slashes)
                is_home_redirect = urlparse(final_url).path == urlparse(home_url).path

                self.logger.debug(f"URL: {url} -> Final URL: {response.url} -> Is home redirect: {is_home_redirect}")
                
                time.sleep(self.config.request_delay)
                
                return (url, is_home_redirect)
                
            except requests.exceptions.Timeout:
                self.logger.warning(f"Timeout for URL {url} (attempt {attempt + 1})")
            except requests.exceptions.RequestException as e:
                self.logger.warning(f"Request error for URL {url} (attempt {attempt + 1}): {e}")
            except Exception as e:
                self.logger.warning(f"Unexpected error for URL {url} (attempt {attempt + 1}): {e}")
            
            if attempt < self.config.max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
        
        # If all attempts failed, assume it's not a home redirect (potential new content)
        self.logger.warning(f"All attempts failed for URL {url}, assuming it has new content")
        return (url, False)
    
    def process_links(self, links: List[str]) -> List[str]:
        """Process all links using multithreading and return those with new content"""
        if self.test_mode:
            links = links[:10]
            self.logger.info("Test mode: Limited to 10 links")

        links_to_process = [link for link in links if link not in self.existing_potential_links]
        skipped_count = len(links) - len(links_to_process)
        if skipped_count > 0:
            self.logger.info(f"Skipping {skipped_count} already processed links")

        if not links_to_process:
            return []

        self.logger.info(f"Processing {len(links_to_process)} redirected links using {self.config.max_workers} threads...")
        
        new_content_links = []
        processed_count = 0
        
        with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
            future_to_url = {executor.submit(self.check_redirect, url): url for url in links_to_process}

            for future in as_completed(future_to_url):
                processed_count += 1
                url = future_to_url[future]
                try:
                    _, is_home_redirect = future.result()
                    
                    if not is_home_redirect:
                        new_content_links.append(url)
                        self.logger.info(f"✓ New content found ({processed_count}/{len(links_to_process)}): {url}")
                    else:
                        self.logger.info(f"✗ Redirects to home ({processed_count}/{len(links_to_process)}): {url}")
                        
                except Exception as e:
                    self.logger.error(f"Error processing {url}: {e}")
                    # Decide if you want to treat errors as new content
                    # For now, we are not adding them to new_content_links on error
        
        return new_content_links
    
    def save_potential_links(self, new_links: List[str]):
        """Append new links to the potential file"""
        if not new_links:
            self.logger.info("No new links to save")
            return
        
        try:
            with open(self.config.potential_file, 'a') as f:
                for link in new_links:
                    f.write(f"{link}\n")
            
            self.logger.info(f"Saved {len(new_links)} new potential links to {self.config.potential_file}")
            # Terminal notification
            print("UPDATE FOUND")
            
        except Exception as e:
            self.logger.error(f"Error saving potential links: {e}")
            raise
    
    def send_email_notification(self, new_links_count: int, new_links: List[str]):
        """Send email notification about new links found"""
        if not self.config.email_config or not new_links_count:
            self.logger.info("Email not configured or no new links to report")
            return
        
        try:
            # Create message
            msg = MIMEMultipart()
            msg['From'] = self.config.email_config['sender_email']
            
            # Determine recipient list (supports comma-separated string or list)
            recipient_field = self.config.email_config.get('recipient_email', '')
            if isinstance(recipient_field, str):
                recipients = [r.strip() for r in recipient_field.split(',') if r.strip()]
            else:
                # Assume it is already a list or tuple
                recipients = list(recipient_field)
            
            msg['To'] = ', '.join(recipients)
            
            msg['Subject'] = f"WebScraper Alert: {new_links_count} New Links Found"
            
            # Create email body
            body = f"""
WebScraper Run Complete - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Found {new_links_count} new links with potential content:

"""
            
            for i, link in enumerate(new_links[:20], 1):  # Show first 20 links
                body += f"{i}. {link}\n"
            
            if len(new_links) > 20:
                body += f"\n... and {len(new_links) - 20} more links.\n"
            
            body += f"\nAll links have been saved to '{self.config.potential_file}'.\n"
            body += f"\nRun completed in {'TEST MODE' if self.test_mode else 'PRODUCTION MODE'}."
            
            msg.attach(MIMEText(body, 'plain'))
            
            # Send email
            server = smtplib.SMTP(
                self.config.email_config['smtp_server'], 
                self.config.email_config['smtp_port']
            )
            server.starttls()
            server.login(
                self.config.email_config['sender_email'], 
                self.config.email_config['sender_password']
            )
            
            text = msg.as_string()
            server.sendmail(
                self.config.email_config['sender_email'],
                recipients,
                text
            )
            server.quit()
            
            self.logger.info(f"Email notification sent successfully to {', '.join(recipients)}")
            
        except Exception as e:
            self.logger.error(f"Error sending email notification: {e}")
    
    def run_scraper(self):
        """Main scraper execution"""
        start_time = datetime.now()
        self.logger.info(f"Starting scraper run at {start_time}")
        
        try:
            # Read links from CSV
            redirected_links = self.read_csv_links()
            
            if not redirected_links:
                self.logger.warning("No redirected links found in CSV file")
                return
            
            # Process links
            new_content_links = self.process_links(redirected_links)
            
            # Save new links
            if new_content_links:
                self.save_potential_links(new_content_links)
                
                # Send email notification
                self.send_email_notification(len(new_content_links), new_content_links)
            
            # Log completion
            end_time = datetime.now()
            duration = end_time - start_time
            
            self.logger.info("=" * 60)
            self.logger.info(f"Scraper run completed successfully")
            self.logger.info(f"Duration: {duration}")
            self.logger.info(f"Links processed: {len(redirected_links)}")
            self.logger.info(f"New content links found: {len(new_content_links)}")
            self.logger.info("=" * 60)
            
            if self.test_mode:
                print(f"\nTest run completed!")
                print(f"Duration: {duration}")
                print(f"Links processed: {min(10, len(redirected_links))}")
                print(f"New content links found: {len(new_content_links)}")
                if new_content_links:
                    print("\nNew links found:")
                    for i, link in enumerate(new_content_links, 1):
                        print(f"{i}. {link}")
            
            # Add a final summary at the end
            self.logger.info("=" * 60)
            self.logger.info(f"Scraper run finished. Found {len(new_content_links)} new potential links.")
            self.logger.info("=" * 60)
            
        except Exception as e:
            self.logger.error(f"Error during scraper execution: {e}")
            raise


def setup_config():
    """Create a default config file."""
    config = WebScraperConfig()
    config.create_default_config()

def run_scheduled_scraper():
    """Run the scraper on a schedule."""
    config = WebScraperConfig()
    scraper = WebScraper(config)
    
    # Schedule the job
    schedule.every(48).hours.do(scraper.run_scraper)
    
    logging.info("Scheduler started. The scraper will run every 48 hours.")
    
    while True:
        schedule.run_pending()
        time.sleep(1)

def main():
    """Main function to run the scraper."""
    parser = argparse.ArgumentParser(
        description="Auto-WebScraper for NKP Government Portal.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    parser.add_argument(
        '--setup',
        action='store_true',
        help="Create a default 'config.json' file.\n"
             "You must edit this file with your email settings before running the scraper."
    )
    
    parser.add_argument(
        '--run',
        action='store_true',
        help="Run the scraper once."
    )
    
    parser.add_argument(
        '--schedule',
        action='store_true',
        help="Run the scraper on a schedule (every 48 hours)."
    )
    
    parser.add_argument(
        '--test',
        action='store_true',
        help="Run the scraper in test mode with a limited number of links."
    )
    
    args = parser.parse_args()
    
    if args.setup:
        setup_config()
    elif args.run:
        config = WebScraperConfig()
        scraper = WebScraper(config, test_mode=args.test)
        scraper.run_scraper()
    elif args.schedule:
        run_scheduled_scraper()
    elif args.test:
        # Also allow --test to be run on its own
        config = WebScraperConfig()
        scraper = WebScraper(config, test_mode=True)
        scraper.run_scraper()
    else:
        parser.print_help()


if __name__ == "__main__":
    main() 