#!/usr/bin/env python3
"""
MEGA Multi-threaded Scraper for ALL Nepal Redirect Courts
Comprehensive daily scraping from 2069-01-01 for all three sites:
1. Foreign Employment Tribunal (fet.gov.np)
2. Revenue Tribunal (revenuetribunal.gov.np)  
3. Administrative Court (admincourt.gov.np)

Uses 12 cores and tests EVERY SINGLE DAY to ensure no data is missed.
"""

import requests
import pandas as pd
from bs4 import BeautifulSoup
import time
import logging
from datetime import datetime, timedelta
import re
import json
import csv
from urllib.parse import urljoin, urlparse
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import queue
from itertools import product

class MegaRedirectCourtsScraper:
    """
    Comprehensive multi-threaded scraper for all three redirect court websites.
    Tests every single day from 2069-01-01 for maximum data coverage.
    """
    
    def __init__(self, max_workers=12, delay=0.3):
        """
        Initialize the mega scraper.
        
        Args:
            max_workers (int): Number of parallel threads (default 12)
            delay (float): Delay between requests in seconds (default 0.3)
        """
        self.max_workers = max_workers
        self.delay = delay
        
        # Set up logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('mega_redirect_courts_scraper.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        # Thread-safe results storage
        self.all_results = []
        self.results_lock = threading.Lock()
        self.stats_lock = threading.Lock()
        
        # Statistics tracking
        self.stats = {
            'total_processed': 0,
            'total_found': 0,
            'by_court': {'B': 0, 'R': 0, 'AD': 0},
            'by_date': {},
            'errors': 0,
            'tasks_processed_by_court': {'B': 0, 'R': 0, 'AD': 0}
        }
        
        # All three court configurations
        self.court_configs = {
            'fet': {
                'name': 'Foreign Employment Tribunal',
                'base_url': 'http://fet.gov.np',
                'decisions_url': 'http://fet.gov.np/causelist/cpfile.php',
                'type_code': 'B'
            },
            'revenue': {
                'name': 'Revenue Tribunal',
                'base_url': 'https://revenuetribunal.gov.np',
                'decisions_url': 'https://revenuetribunal.gov.np/rajaswoFaisalaPdf',
                'type_code': 'R'
            },
            'admin': {
                'name': 'Administrative Court',
                'base_url': 'https://admincourt.gov.np',
                'decisions_url': 'https://admincourt.gov.np/adminCourtFaisalaPdf',
                'type_code': 'AD'
            }
        }
        
        # Generate comprehensive task list: every day for every court
        self.task_list = self._generate_all_tasks()
        
        self.logger.info(f"Initialized MegaRedirectCourtsScraper with {max_workers} workers")
        self.logger.info(f"Will process {len(self.task_list)} total tasks")
        self.logger.info(f"Expected runtime: ~{len(self.task_list) * delay / max_workers / 60:.1f} minutes")

    def _generate_all_tasks(self):
        """Generate every single day from 2069-01-01 for all three courts."""
        tasks = []
        
        # Nepali calendar considerations
        # Generate every day from 2069-01-01 to 2081-12-30
        start_year = 2069
        end_year = 2081
        
        for year in range(start_year, end_year + 1):
            for month in range(1, 13):  # 12 months
                # Nepali months have varying days, but we'll be safe and try up to 32
                max_day = 32 if month <= 11 else 30  # Most months have 30-32 days
                
                for day in range(1, max_day + 1):
                    date_str = f"{year:04d}-{month:02d}-{day:02d}"
                    
                    # Add task for each court
                    for court_key, court_config in self.court_configs.items():
                        task = {
                            'court_key': court_key,
                            'court_config': court_config,
                            'date': date_str,
                            'task_id': f"{court_key}_{date_str}"
                        }
                        tasks.append(task)
        
        self.logger.info(f"Generated {len(tasks)} total tasks:")
        for court_key, court_config in self.court_configs.items():
            court_tasks = [t for t in tasks if t['court_key'] == court_key]
            self.logger.info(f"  {court_config['name']}: {len(court_tasks)} dates")
        
        return tasks

    def create_session(self):
        """Create a new session for thread-safe requests."""
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        })
        return session

    def scrape_single_task(self, task):
        """
        Scrape a single court for a single date.
        Thread-safe function for parallel execution.
        
        Args:
            task (dict): Task containing court and date information
            
        Returns:
            dict: Results with decisions and metadata
        """
        session = self.create_session()
        court_config = task['court_config']
        date_str = task['date']
        
        # Add debug logging to show all courts being processed
        self.logger.debug(f"🔍 Processing {court_config['name']} ({court_config['type_code']}) - {date_str}")
        
        try:
            time.sleep(self.delay)
            
            # Prepare form data for search
            form_data = {
                'regno': '',
                'darta_date': date_str,
                'faisala_date': '',
                'mode': 'show'
            }
            
            # Submit search request
            response = session.get(court_config['decisions_url'], params=form_data, timeout=30)
            response.raise_for_status()
            
            # Parse results
            soup = BeautifulSoup(response.content, 'html.parser')
            text_content = soup.get_text()
            
            # Check for record count
            record_count = 0
            record_count_pattern = r'(\d+)\s*वटा\s*रेकर्ड\s*भेटियो'
            match = re.search(record_count_pattern, text_content)
            
            if match:
                record_count = int(match.group(1))
            
            # Update statistics
            with self.stats_lock:
                self.stats['total_processed'] += 1
                self.stats['tasks_processed_by_court'][court_config['type_code']] += 1
                if record_count > 0:
                    self.stats['total_found'] += record_count
                    self.stats['by_court'][court_config['type_code']] += record_count
                    if date_str not in self.stats['by_date']:
                        self.stats['by_date'][date_str] = 0
                    self.stats['by_date'][date_str] += record_count
            
            decisions = []
            
            if record_count > 0:
                self.logger.info(f"🎉 {court_config['name']} ({court_config['type_code']}) - {date_str}: Found {record_count} records!")
                
                # Parse the results table
                tables = soup.find_all('table')
                for table in tables:
                    rows = table.find_all('tr')
                    
                    if len(rows) < 2:
                        continue
                        
                    # Check if this is a results table
                    header_row = rows[0]
                    headers = [th.get_text(strip=True) for th in header_row.find_all(['th', 'td'])]
                    
                    if any(header in ' '.join(headers) for header in ['दर्ता नं', 'मुद्दा', 'फैसला']):
                        # Parse data rows
                        for i, row in enumerate(rows[1:], 1):
                            cells = row.find_all(['td', 'th'])
                            
                            if len(cells) < 3:
                                continue
                            
                            # Extract cell data
                            cell_data = [cell.get_text(strip=True) for cell in cells]
                            
                            # Look for download links
                            download_link = None
                            for cell in cells:
                                links = cell.find_all('a', href=True)
                                for link in links:
                                    href = link.get('href')
                                    if href and ('.pdf' in href.lower() or 'download' in href.lower()):
                                        download_link = urljoin(court_config['base_url'], href)
                                        break
                            
                            # Create decision record
                            decision = {
                                'court_type': court_config['type_code'],
                                'court_name': court_config['name'],
                                'search_date': date_str,
                                'scraped_at': datetime.now().isoformat(),
                                'source_url': response.url,
                                'row_number': i,
                                'download_url': download_link or 'N/A'
                            }
                            
                            # Map data to fields
                            if len(cell_data) >= 10:
                                decision.update({
                                    'serial_number': cell_data[0] if cell_data[0] else f"Row-{i}",
                                    'registration_number': cell_data[1],
                                    'case_number': cell_data[2],
                                    'registration_date': cell_data[3],
                                    'case_type': cell_data[4],
                                    'case_name': cell_data[5],
                                    'plaintiff': cell_data[6],
                                    'defendant': cell_data[7],
                                    'decision_date': cell_data[8],
                                    'full_text_available': 'Yes' if cell_data[9] else 'No'
                                })
                            else:
                                decision['raw_data'] = ' | '.join(cell_data)
                            
                            decisions.append(decision)
            
            # Log zero results more frequently to show all courts are being processed
            if record_count == 0 and (date_str.endswith('-01-01') or date_str.endswith('-06-01') or date_str.endswith('-01-15') or date_str.endswith('-06-15')):  # Log 4 times per year
                self.logger.info(f"⭕ {court_config['name']} ({court_config['type_code']}) - {date_str}: 0 records found")
            
            return {
                'task_id': task['task_id'],
                'court': court_config['type_code'],
                'court_name': court_config['name'],
                'date': date_str,
                'record_count': record_count,
                'decisions': decisions,
                'success': True
            }
            
        except Exception as e:
            with self.stats_lock:
                self.stats['errors'] += 1
                self.stats['total_processed'] += 1
                self.stats['tasks_processed_by_court'][court_config['type_code']] += 1
            
            self.logger.error(f"❌ {court_config['name']} ({court_config['type_code']}) - {date_str}: Error - {e}")
            return {
                'task_id': task['task_id'],
                'court': court_config['type_code'],
                'court_name': court_config['name'],
                'date': date_str,
                'record_count': 0,
                'decisions': [],
                'success': False,
                'error': str(e)
            }
        finally:
            session.close()

    def run_mega_scraping(self):
        """
        Run mega parallel scraping using ThreadPoolExecutor.
        
        Returns:
            list: All collected decisions
        """
        self.logger.info(f"🚀 Starting MEGA scraping with {self.max_workers} workers...")
        self.logger.info(f"📊 Processing {len(self.task_list)} total tasks")
        self.logger.info(f"🎯 Target: Every day from 2069-01-01 for all 3 courts")
        
        # Log all courts being scraped
        self.logger.info(f"🏛️  Courts configured:")
        for court_key, court_config in self.court_configs.items():
            court_tasks = [t for t in self.task_list if t['court_key'] == court_key]
            self.logger.info(f"   {court_config['name']} ({court_config['type_code']}): {len(court_tasks)} tasks | {court_config['decisions_url']}")
        
        all_decisions = []
        completed_count = 0
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_task = {
                executor.submit(self.scrape_single_task, task): task 
                for task in self.task_list
            }
            
            # Process completed tasks
            for future in as_completed(future_to_task):
                task = future_to_task[future]
                completed_count += 1
                
                try:
                    result = future.result()
                    
                    if result['success'] and result['decisions']:
                        with self.results_lock:
                            all_decisions.extend(result['decisions'])
                    
                    # Progress update every 100 tasks
                    if completed_count % 100 == 0:
                        elapsed = time.time() - start_time
                        rate = completed_count / elapsed
                        eta = (len(self.task_list) - completed_count) / rate / 60
                        
                        with self.stats_lock:
                            stats_copy = self.stats.copy()
                        
                        self.logger.info(f"📈 Progress: {completed_count}/{len(self.task_list)} | Found: {len(all_decisions)} decisions | ETA: {eta:.1f}min")
                        self.logger.info(f"   Decisions Found: FET={stats_copy['by_court']['B']}, RT={stats_copy['by_court']['R']}, AC={stats_copy['by_court']['AD']}")
                        self.logger.info(f"   Tasks Processed: FET={stats_copy['tasks_processed_by_court']['B']}, RT={stats_copy['tasks_processed_by_court']['R']}, AC={stats_copy['tasks_processed_by_court']['AD']} | Errors: {stats_copy['errors']}")
                    
                    # Show exciting finds immediately
                    if result['record_count'] > 0:
                        self.logger.info(f"🔥 JACKPOT! {result['court_name']} ({result['court']}) - {result['date']}: {result['record_count']} decisions!")
                        
                except Exception as e:
                    self.logger.error(f"❌ Task failed: {e}")
        
        self.all_results = all_decisions
        elapsed = time.time() - start_time
        
        self.logger.info(f"🎉 MEGA SCRAPING COMPLETE!")
        self.logger.info(f"⏱️  Total time: {elapsed/60:.1f} minutes")
        self.logger.info(f"📊 Total decisions found: {len(all_decisions)}")
        
        return all_decisions

    def save_results(self, filename=None):
        """Save results to CSV files - one combined and separate files for each court."""
        if not self.all_results:
            self.logger.warning("No results to save")
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        try:
            df = pd.DataFrame(self.all_results)
            
            # Save combined file
            if not filename:
                filename = f"mega_all_courts_decisions_{timestamp}.csv"
            df.to_csv(filename, index=False, encoding='utf-8')
            self.logger.info(f"Combined results saved to {filename}")
            
            # Save separate files for each court
            court_files = {}
            for court_code, court_config in [('B', 'Foreign Employment Tribunal'), ('R', 'Revenue Tribunal'), ('AD', 'Administrative Court')]:
                court_data = df[df['court_type'] == court_code]
                if not court_data.empty:
                    court_filename = f"mega_{court_config.lower().replace(' ', '_')}_decisions_{timestamp}.csv"
                    court_data.to_csv(court_filename, index=False, encoding='utf-8')
                    court_files[court_config] = {'filename': court_filename, 'count': len(court_data)}
                    self.logger.info(f"{court_config} results saved to {court_filename} ({len(court_data)} decisions)")
                else:
                    self.logger.info(f"{court_config}: No decisions found (no separate file created)")
            
            # Print comprehensive summary
            print(f"\n{'='*60}")
            print(f"🎉 MEGA SCRAPING SUMMARY")
            print(f"{'='*60}")
            print(f"📊 Total decisions found: {len(self.all_results)}")
            print(f"📅 Date range: 2069-01-01 to 2081-12-30")
            print(f"🏛️  Courts scraped: All 3 redirect courts")
            print(f"🔧 Threads used: {self.max_workers}")
            
            with self.stats_lock:
                print(f"\n📈 BREAKDOWN BY COURT:")
                for court_code, count in self.stats['by_court'].items():
                    court_name = next((config['name'] for config in self.court_configs.values() 
                                     if config['type_code'] == court_code), court_code)
                    tasks_processed = self.stats['tasks_processed_by_court'][court_code]
                    print(f"   {court_name} ({court_code}): {count} decisions from {tasks_processed} tasks processed")
                
                if self.stats['by_date']:
                    print(f"\n🗓️  TOP 10 MOST PRODUCTIVE DATES:")
                    sorted_dates = sorted(self.stats['by_date'].items(), key=lambda x: x[1], reverse=True)
                    for date, count in sorted_dates[:10]:
                        print(f"   {date}: {count} decisions")
                
                print(f"\n📋 PROCESSING STATS:")
                print(f"   Total tasks processed: {self.stats['total_processed']}")
                print(f"   Tasks with data: {len([d for d in self.stats['by_date'].values() if d > 0])}")
                print(f"   Error rate: {self.stats['errors']}/{self.stats['total_processed']} ({self.stats['errors']/max(1,self.stats['total_processed'])*100:.1f}%)")
            
            print(f"\n💾 FILES CREATED:")
            print(f"   📁 Combined: {filename}")
            for court_name, file_info in court_files.items():
                print(f"   📁 {court_name}: {file_info['filename']} ({file_info['count']} decisions)")
            
            print(f"\n{'='*60}")
            
        except Exception as e:
            self.logger.error(f"Error saving results: {e}")

def main():
    """Main function for mega parallel scraping."""
    print("🚀 MEGA NEPAL REDIRECT COURTS SCRAPER")
    print("=====================================")
    print("Comprehensive scraping of ALL THREE redirect court sites:")
    print("1. Foreign Employment Tribunal (fet.gov.np)")
    print("2. Revenue Tribunal (revenuetribunal.gov.np)")  
    print("3. Administrative Court (admincourt.gov.np)")
    print()
    print("📅 Every single day from 2069-01-01")
    print("🔧 Using 12 parallel cores")
    print("🎯 Maximum data coverage strategy")
    print()
    
    # Ask for confirmation
    confirm = input("This will test ~15,000 date/court combinations. Continue? (y/N): ").strip().lower()
    if confirm != 'y':
        print("Scraping cancelled.")
        return
    
    # Initialize and run scraper
    scraper = MegaRedirectCourtsScraper(max_workers=12, delay=0.3)
    
    try:
        decisions = scraper.run_mega_scraping()
        
        if decisions:
            scraper.save_results()
            print(f"\n🎉 SUCCESS! Found {len(decisions)} total decisions across all courts!")
        else:
            print("\n😞 No decisions found across any courts.")
            print("Check the log file for detailed information.")
            
    except KeyboardInterrupt:
        print("\n⛔ Scraping interrupted by user")
        if scraper.all_results:
            print(f"💾 Saving {len(scraper.all_results)} partial results...")
            scraper.save_results("partial_mega_results.csv")
    except Exception as e:
        print(f"\n❌ Error during mega scraping: {e}")
        if scraper.all_results:
            print(f"💾 Saving {len(scraper.all_results)} partial results...")
            scraper.save_results("error_recovery_results.csv")

if __name__ == "__main__":
    main() 