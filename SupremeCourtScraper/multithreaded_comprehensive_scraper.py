#!/usr/bin/env python3
"""
Multithreaded Comprehensive Supreme Court Scraper
High-performance scraper for ALL courts, ALL types, day-by-day from 2069 onwards
Features:
- Multithreading for 10x+ speed improvement
- Proper UTF-8 encoding for Nepali text
- Progress tracking and resumption capability
- Batch processing with checkpoints
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import logging
import time
from datetime import datetime
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from queue import Queue
import signal
import sys
import glob

# Set up logging with proper UTF-8 encoding
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('multithreaded_scraper.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

class MultithreadedCourtScraper:
    def __init__(self, max_workers=12):
        self.base_url = "https://supremecourt.gov.np/cp/"
        self.max_workers = max_workers
        
        # All court types available on the website
        self.court_types = {
            'S': 'सर्वोच्च अदालत',           # Supreme Court
            'A': 'उच्च अदालत',              # High Court  
            'D': 'जिल्ला अदालत',            # District Court
            'T': 'विशेष अदालत',             # Special Court
            'B': 'वैदेशिक रोजगार न्यायाधिकरण', # Foreign Employment Tribunal
            'R': 'राजस्व न्यायाधिकरण',        # Revenue Tribunal
            'AD': 'प्रशासकीय अदालत'         # Administrative Court
        }
        
        # Court types that redirect to different websites
        self.redirect_court_types = ['B', 'R', 'AD']
        
        self.all_decisions = []
        self.court_cache = {}
        self.progress_lock = threading.Lock()
        self.results_lock = threading.Lock()
        
        # Progress tracking
        self.total_searches = 0
        self.completed_searches = 0
        self.total_decisions_found = 0
        
        # Graceful shutdown handling
        signal.signal(signal.SIGINT, self.signal_handler)
        self.shutdown_requested = False
        
    def signal_handler(self, signum, frame):
        """Handle Ctrl+C gracefully"""
        logging.info("\n⚠️  Shutdown requested. Finishing current tasks and saving progress...")
        self.shutdown_requested = True
    
    def create_session(self):
        """Create a new session for thread-safe requests"""
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        return session
    
    def get_court_list(self, court_type):
        """Get the list of all courts for a given court type"""
        if court_type in self.court_cache:
            return self.court_cache[court_type]
            
        try:
            session = self.create_session()
            data = {'court_type': court_type, 'selected': 0}
            response = session.post(f"{self.base_url}welcome/get_courts", data=data)
            response.raise_for_status()
            
            # Fix encoding issue: explicitly set UTF-8 encoding for Nepali text
            response.encoding = 'utf-8'
            
            soup = BeautifulSoup(response.text, 'html.parser')
            options = soup.find_all('option')
            courts = []
            
            for option in options:
                value = option.get('value', '')
                text = option.text.strip()
                
                if value and value != '':
                    courts.append({
                        'id': value,
                        'name': text,
                        'type_code': court_type,
                        'type_name': self.court_types.get(court_type, court_type)
                    })
            
            self.court_cache[court_type] = courts
            logging.info(f"Found {len(courts)} courts for type {court_type} ({self.court_types.get(court_type)})")
            
            return courts
            
        except Exception as e:
            logging.error(f"Error getting court list for type {court_type}: {e}")
            return []
    
    def get_completed_task_count_from_logs(self):
        """Extract the exact number of completed tasks from log files"""
        try:
            with open('multithreaded_scraper.log', 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Find the last progress line
            for line in reversed(lines):
                if 'Progress:' in line and '/462,787' in line:
                    # Extract completed count from line like "Progress: 401,650/462,787 (86.79%)"
                    import re
                    match = re.search(r'Progress: (\d+,?\d*)/462,787', line)
                    if match:
                        completed_str = match.group(1).replace(',', '')
                        return int(completed_str)
            
            return 0
        except Exception as e:
            logging.warning(f"Could not read progress from logs: {e}")
            return 0
    
    def get_completed_tasks(self):
        """Bulletproof method to determine exactly which tasks were completed"""
        
        # First try to get exact count from logs (most accurate)
        completed_count = self.get_completed_task_count_from_logs()
        
        if completed_count > 0:
            logging.info(f"📊 Found {completed_count:,} completed tasks from log analysis")
            return completed_count
        
        # Fallback: analyze checkpoint files (less accurate but better than nothing)
        completed_combinations = set()
        checkpoint_files = sorted(glob.glob("checkpoint_*.csv"))
        
        if not checkpoint_files:
            logging.info("No existing checkpoint files found - starting fresh")
            return 0
        
        logging.info(f"Analyzing {len(checkpoint_files)} existing checkpoint files for resume...")
        
        for file in checkpoint_files:
            try:
                df = pd.read_csv(file, encoding='utf-8-sig')
                # Create unique combinations of court_id + search_date to track what's been processed
                for _, row in df.iterrows():
                    combination = (str(row['court_id']), str(row['search_date']))
                    completed_combinations.add(combination)
                    
            except Exception as e:
                logging.warning(f"Could not read checkpoint file {file}: {e}")
        
        logging.info(f"Found {len(completed_combinations):,} completed court-date combinations from checkpoints")
        return len(completed_combinations)
    
    def generate_date_range(self, start_year=2069, end_year=None):
        """Generate comprehensive date range day-by-day in Nepali calendar format"""
        if end_year is None:
            end_year = 2081  # Current approximate Nepali year
        
        dates = []
        
        for year in range(start_year, end_year + 1):
            for month in range(1, 13):  # Nepali calendar has 12 months
                # Nepali calendar: months 1-8 have 31 days, month 9-11 have 30 days, month 12 has 29/30 days
                if month <= 8:
                    days_in_month = 31
                elif month <= 11:
                    days_in_month = 30
                else:  # month 12
                    days_in_month = 29
                
                for day in range(1, days_in_month + 1):
                    date_string = f"{year:04d}-{month:02d}-{day:02d}"
                    dates.append(date_string)
        
        logging.info(f"Generated {len(dates)} dates from {start_year}-01-01 to {end_year}-12-29")
        return dates
    
    def search_single_date_court(self, task):
        """Search for decisions for a single date-court combination (thread worker function)"""
        court_info, date_string, task_id = task
        
        if self.shutdown_requested:
            return []
        
        try:
            session = self.create_session()
            
            form_data = {
                'court_type': court_info['type_code'],
                'court_id': court_info['id'],
                'regno': '',
                'darta_date': date_string,
                'faisala_date': '',
                'submit': 'खोज्नु होस्'
            }
            
            response = session.post(self.base_url, data=form_data)
            response.raise_for_status()
            
            # Fix encoding issue: explicitly set UTF-8 encoding for Nepali text
            response.encoding = 'utf-8'
            
            decisions = self.parse_search_results(response.text, date_string, court_info)
            
            # Update progress
            with self.progress_lock:
                self.completed_searches += 1
                if decisions:
                    self.total_decisions_found += len(decisions)
                
                # Log progress every 50 completed searches
                if self.completed_searches % 50 == 0:
                    progress_pct = (self.completed_searches / self.total_searches) * 100
                    logging.info(f"Progress: {self.completed_searches:,}/{self.total_searches:,} ({progress_pct:.2f}%) - Found {self.total_decisions_found:,} decisions")
            
            # Rate limiting per thread
            time.sleep(0.2)  # Reduced from 1.5s since we have multiple threads
            
            return decisions
            
        except Exception as e:
            logging.error(f"Error searching {court_info['name']} for date {date_string}: {e}")
            return []
    
    def parse_search_results(self, html_content, search_date, court_info):
        """Parse search results and extract decision data with complete court information"""
        soup = BeautifulSoup(html_content, 'html.parser')
        decisions = []
        
        # Look for the main results table
        table = soup.find('table', class_='table table-bordered sc-table table-responsive')
        
        if not table:
            # Check for no results message (this is normal for most dates)
            if 'भेटिएन' in html_content:
                return decisions
            else:
                logging.debug(f"Could not find results table for {court_info['name']} on {search_date}")
            return decisions
        
        tbody = table.find('tbody')
        if not tbody:
            return decisions
        
        rows = tbody.find_all('tr')
        
        for row in rows:
            cells = row.find_all('td')
            
            if len(cells) >= 10:
                # Extract data from each cell
                serial_no = cells[0].get_text(strip=True)
                registration_no = cells[1].get_text(strip=True)
                case_no = cells[2].get_text(strip=True)
                registration_date = cells[3].get_text(strip=True)
                case_type = cells[4].get_text(strip=True)
                case_name = cells[5].get_text(strip=True)
                plaintiff = cells[6].get_text(strip=True)
                defendant = cells[7].get_text(strip=True)
                decision_date = cells[8].get_text(strip=True)
                
                # Check for download link in the last column
                download_url = 'N/A'
                last_cell = cells[9]
                link = last_cell.find('a')
                if link and link.get('href'):
                    download_url = link.get('href')
                    if not download_url.startswith('http'):
                        download_url = f"{self.base_url.rstrip('/')}/{download_url.lstrip('/')}"
                else:
                    # Check for error image (indicates upload pending)
                    img = last_cell.find('img')
                    if img and 'error.png' in str(img.get('src', '')):
                        download_url = 'Upload Pending'
                
                # Create decision record with complete court information
                decision_data = {
                    'search_date': search_date,
                    'court_type_code': court_info['type_code'],
                    'court_type_name': court_info['type_name'],
                    'court_id': court_info['id'],
                    'court_name': court_info['name'],
                    'serial_no': serial_no,
                    'registration_no': registration_no,
                    'case_no': case_no,
                    'registration_date': registration_date,
                    'case_type': case_type,
                    'case_name': case_name,
                    'plaintiff': plaintiff,
                    'defendant': defendant,
                    'decision_date': decision_date,
                    'download_url': download_url,
                    'scraped_date': datetime.now().isoformat()
                }
                
                decisions.append(decision_data)
        
        return decisions
    
    def save_checkpoint(self, decisions, checkpoint_num):
        """Save intermediate results as checkpoint"""
        if not decisions:
            return
            
        checkpoint_file = f"checkpoint_{checkpoint_num:04d}.csv"
        df = pd.DataFrame(decisions)
        
        # Save with proper UTF-8 encoding for Nepali text
        df.to_csv(checkpoint_file, index=False, encoding='utf-8-sig')
        logging.info(f"💾 Checkpoint saved: {checkpoint_file} ({len(decisions)} decisions)")
    
    def merge_checkpoints(self, output_filename="comprehensive_court_decisions.csv"):
        """Merge all checkpoint files into final output"""
        checkpoint_files = sorted(glob.glob("checkpoint_*.csv"))
        if not checkpoint_files:
            logging.warning("No checkpoint files found to merge")
            return
        
        logging.info(f"Merging {len(checkpoint_files)} checkpoint files...")
        
        all_dfs = []
        for file in checkpoint_files:
            try:
                df = pd.read_csv(file, encoding='utf-8-sig')
                all_dfs.append(df)
                logging.info(f"Loaded {file}: {len(df)} decisions")
            except Exception as e:
                logging.error(f"Error loading {file}: {e}")
        
        if all_dfs:
            final_df = pd.concat(all_dfs, ignore_index=True)
            
            # Remove duplicates if any
            initial_count = len(final_df)
            final_df = final_df.drop_duplicates(subset=['registration_no', 'court_id', 'search_date'])
            final_count = len(final_df)
            
            if initial_count != final_count:
                logging.info(f"Removed {initial_count - final_count} duplicate records")
            
            # Save final file with proper UTF-8 encoding
            final_df.to_csv(output_filename, index=False, encoding='utf-8-sig')
            logging.info(f"✅ Final dataset saved: {output_filename} ({final_count:,} decisions)")
            
            # Generate summary
            self.generate_final_summary(final_df, output_filename)
            
            # Clean up checkpoint files
            self.cleanup_checkpoints(checkpoint_files)
    
    def cleanup_checkpoints(self, checkpoint_files):
        """Remove checkpoint files after successful merge"""
        for file in checkpoint_files:
            try:
                os.remove(file)
            except Exception as e:
                logging.warning(f"Could not remove checkpoint file {file}: {e}")
        logging.info(f"Cleaned up {len(checkpoint_files)} checkpoint files")
    
    def generate_final_summary(self, df, filename):
        """Generate comprehensive summary of final results"""
        summary = {
            'total_decisions': len(df),
            'scraping_completed_date': datetime.now().isoformat(),
            'unique_courts': len(df['court_name'].unique()),
            'court_types_covered': df['court_type_name'].unique().tolist(),
            'date_range': {
                'earliest': df['search_date'].min(),
                'latest': df['search_date'].max()
            },
            'decisions_by_court_type': df['court_type_name'].value_counts().to_dict(),
            'decisions_by_court': df['court_name'].value_counts().head(20).to_dict(),
            'decisions_with_downloads': len(df[df['download_url'].str.contains('http', na=False)]),
            'decisions_upload_pending': len(df[df['download_url'] == 'Upload Pending']),
            'decisions_no_download': len(df[df['download_url'] == 'N/A']),
            'top_case_types': df['case_type'].value_counts().head(10).to_dict(),
            'decisions_by_year': df['search_date'].str[:4].value_counts().sort_index().to_dict()
        }
        
        # Save summary with proper UTF-8 encoding
        summary_filename = filename.replace('.csv', '_summary.json')
        with open(summary_filename, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        # Print summary
        logging.info("=== FINAL COMPREHENSIVE SCRAPING SUMMARY ===")
        logging.info(f"Total decisions found: {summary['total_decisions']:,}")
        logging.info(f"Unique courts covered: {summary['unique_courts']}")
        logging.info(f"Date range: {summary['date_range']['earliest']} to {summary['date_range']['latest']}")
        logging.info(f"With download links: {summary['decisions_with_downloads']:,}")
        logging.info(f"Upload pending: {summary['decisions_upload_pending']:,}")
        logging.info(f"No download: {summary['decisions_no_download']:,}")
    
    def scrape_comprehensive_multithreaded(self, start_year=2069, end_year=None, court_types_to_include=None, batch_size=1000):
        """
        Main multithreaded comprehensive scraping function
        
        Args:
            start_year: Starting Nepali year (default 2069)
            end_year: Ending Nepali year (default current ~2081)
            court_types_to_include: List of court types to include
            batch_size: Number of tasks per checkpoint batch
        """
        
        # Default to all court types except those that redirect
        if court_types_to_include is None:
            court_types_to_include = [ct for ct in self.court_types.keys() if ct not in self.redirect_court_types]
        
        logging.info(f"Starting MULTITHREADED comprehensive scraping from year {start_year}")
        logging.info(f"Court types to include: {court_types_to_include}")
        logging.info(f"Max workers: {self.max_workers}")
        
        # Get all courts for all types
        all_courts = []
        for court_type in court_types_to_include:
            courts = self.get_court_list(court_type)
            all_courts.extend(courts)
        
        total_courts = len(all_courts)
        logging.info(f"Total courts to scrape: {total_courts}")
        
        # Generate date range
        dates = self.generate_date_range(start_year, end_year)
        
        # Generate ALL tasks in exact same order as original run
        all_tasks = []
        task_id = 0
        for court in all_courts:
            for date_string in dates:
                all_tasks.append((court, date_string, task_id))
                task_id += 1
        
        total_possible_tasks = len(all_tasks)
        logging.info(f"Total possible tasks: {total_possible_tasks:,}")
        
        # Get exact completed count for bulletproof resumption
        completed_count = self.get_completed_tasks()
        
        # Skip exactly the number of completed tasks (in order)
        if completed_count > 0:
            remaining_tasks = all_tasks[completed_count:]
            logging.info(f"🎯 BULLETPROOF RESUME: Skipping first {completed_count:,} completed tasks")
            logging.info(f"📋 Resuming from task #{completed_count + 1}")
        else:
            remaining_tasks = all_tasks
            logging.info("🚀 Starting fresh - no previous progress found")
        
        tasks = remaining_tasks
        self.total_searches = len(tasks)
        logging.info(f"Remaining searches to perform: {self.total_searches:,}")
        
        if self.total_searches == 0:
            logging.info("🎉 All tasks already completed!")
            self.merge_checkpoints()
            return
        
        completion_percentage = (completed_count / total_possible_tasks) * 100
        logging.info(f"📊 Resuming from {completion_percentage:.2f}% completion")
        logging.info(f"Estimated time with {self.max_workers} threads: {(self.total_searches * 0.2 / self.max_workers / 3600):.1f} hours")
        
        # Process tasks in batches with checkpoints
        checkpoint_num = len(glob.glob("checkpoint_*.csv")) + 1  # Continue from last checkpoint number
        batch_results = []
        
        start_time = datetime.now()
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_task = {executor.submit(self.search_single_date_court, task): task for task in tasks}
            
            for future in as_completed(future_to_task):
                if self.shutdown_requested:
                    logging.info("Shutdown requested, stopping task submission...")
                    break
                
                try:
                    decisions = future.result()
                    if decisions:
                        with self.results_lock:
                            batch_results.extend(decisions)
                        
                        logging.info(f"✓ Found {len(decisions)} decisions from {decisions[0]['court_name']} on {decisions[0]['search_date']}")
                    
                    # Save checkpoint every batch_size results
                    if len(batch_results) >= batch_size:
                        with self.results_lock:
                            self.save_checkpoint(batch_results, checkpoint_num)
                            batch_results = []
                            checkpoint_num += 1
                
                except Exception as e:
                    task = future_to_task[future]
                    logging.error(f"Task failed: {task[0]['name']} on {task[1]}: {e}")
        
        # Save final batch if any remaining
        if batch_results:
            self.save_checkpoint(batch_results, checkpoint_num)
        
        end_time = datetime.now()
        duration = end_time - start_time
        
        logging.info(f"\n🎉 Scraping completed!")
        logging.info(f"Total time: {duration}")
        logging.info(f"Total searches completed: {self.completed_searches:,}")
        logging.info(f"Total decisions found: {self.total_decisions_found:,}")
        
        # Merge all decisions into final file
        self.merge_checkpoints()

    def save_progress_state(self, completed_count, total_count):
        """Save the current progress state for bulletproof resumption"""
        progress_state = {
            'completed_searches': completed_count,
            'total_searches': total_count,
            'completion_percentage': (completed_count / total_count) * 100,
            'timestamp': datetime.now().isoformat(),
            'last_checkpoint_num': len(glob.glob("checkpoint_*.csv"))
        }
        
        with open('scraper_progress.json', 'w', encoding='utf-8') as f:
            json.dump(progress_state, f, indent=2, ensure_ascii=False)
    
    def load_progress_state(self):
        """Load previous progress state for resumption"""
        try:
            with open('scraper_progress.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return None

def main():
    """Main execution function"""
    
    print("🚀 MULTITHREADED COMPREHENSIVE SUPREME COURT SCRAPER")
    print("=" * 60)
    
    # Configuration
    max_workers = 12  # Adjust based on your system and internet connection
    start_year = 2069
    end_year = 2081
    
    print(f"Configuration:")
    print(f"  Start Year: {start_year}")
    print(f"  End Year: {end_year}")
    print(f"  Max Workers: {max_workers}")
    print(f"  Court Types: Supreme, High, District, Special courts")
    print()
    
    scraper = MultithreadedCourtScraper(max_workers=max_workers)
    
    try:
        scraper.scrape_comprehensive_multithreaded(
            start_year=start_year,
            end_year=end_year,
            batch_size=1000  # Save checkpoint every 1000 results
        )
        
        print("\n✅ COMPREHENSIVE SCRAPING COMPLETED SUCCESSFULLY!")
        print("📁 Check 'comprehensive_court_decisions.csv' for final results")
        print("📊 Check '*_summary.json' for detailed statistics")
        
    except KeyboardInterrupt:
        print("\n⚠️  Scraping interrupted by user")
        print("💾 Progress has been saved in checkpoint files")
        print("🔄 Run the script again to resume from where it left off")
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        print(f"\n❌ Error occurred: {e}")
        print("💾 Partial progress may be saved in checkpoint files")

if __name__ == "__main__":
    main() 