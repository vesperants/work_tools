#!/usr/bin/env python3
"""
Comprehensive Supreme Court Scraper
Scrapes ALL courts, ALL types, day-by-day from 2069 onwards using registration dates
Addresses user requirements:
1. Day-by-day date progression starting from 2069
2. All court types (S, A, D, T, etc.)
3. All individual courts within each type
4. Complete court metadata in each row
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import logging
import time
from datetime import datetime, timedelta
import json
import os
from calendar import monthrange

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('comprehensive_scraper.log'),
        logging.StreamHandler()
    ]
)

class ComprehensiveCourtScraper:
    def __init__(self):
        self.base_url = "https://supremecourt.gov.np/cp/"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        
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
        
        # Court types that redirect to different websites (we'll note but may skip)
        self.redirect_court_types = ['B', 'R', 'AD']
        
        self.all_decisions = []
        self.court_cache = {}  # Cache court lists to avoid repeated API calls
        
    def get_court_list(self, court_type):
        """Get the list of all courts for a given court type"""
        if court_type in self.court_cache:
            return self.court_cache[court_type]
            
        try:
            data = {'court_type': court_type, 'selected': 0}
            response = self.session.post(f"{self.base_url}welcome/get_courts", data=data)
            response.raise_for_status()
            
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
    
    def generate_date_range(self, start_year=2069, end_year=None, start_month=1, start_day=1):
        """
        Generate comprehensive date range day-by-day in Nepali calendar format
        
        Args:
            start_year: Starting Nepali year (default 2069)
            end_year: Ending Nepali year (default current year ~2081)
            start_month: Starting month (default 1)
            start_day: Starting day (default 1)
        """
        if end_year is None:
            end_year = 2081  # Current approximate Nepali year
        
        dates = []
        
        for year in range(start_year, end_year + 1):
            # Determine month range
            month_start = start_month if year == start_year else 1
            
            for month in range(month_start, 13):  # Nepali calendar has 12 months
                # Determine day range
                day_start = start_day if (year == start_year and month == start_month) else 1
                
                # Nepali calendar: months 1-8 have 31 days, month 9-11 have 30 days, month 12 has 29/30 days
                if month <= 8:
                    days_in_month = 31
                elif month <= 11:
                    days_in_month = 30
                else:  # month 12
                    # For simplicity, use 29 days for month 12 (Chaitra)
                    days_in_month = 29
                
                for day in range(day_start, days_in_month + 1):
                    date_string = f"{year:04d}-{month:02d}-{day:02d}"
                    dates.append(date_string)
        
        logging.info(f"Generated {len(dates)} dates from {start_year}-{start_month:02d}-{start_day:02d} to {end_year}-12-29")
        return dates
    
    def search_by_date_and_court(self, court_info, date_string):
        """Search for decisions using registration date for a specific court"""
        try:
            form_data = {
                'court_type': court_info['type_code'],
                'court_id': court_info['id'],
                'regno': '',
                'darta_date': date_string,  # Using registration date field as requested
                'faisala_date': '',
                'submit': 'खोज्नु होस्'
            }
            
            response = self.session.post(self.base_url, data=form_data)
            response.raise_for_status()
            
            return self.parse_search_results(response.text, date_string, court_info)
            
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
                # This is normal - most dates won't have results
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
            
            if len(cells) >= 10:  # We expect 10 columns based on the table structure
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
        
        if decisions:
            logging.info(f"Found {len(decisions)} decisions for {court_info['name']} on {search_date}")
        
        return decisions
    
    def scrape_comprehensive(self, start_year=2069, end_year=None, court_types_to_include=None, sample_mode=False):
        """
        Main comprehensive scraping function
        
        Args:
            start_year: Starting Nepali year (default 2069 as requested)
            end_year: Ending Nepali year (default current ~2081)
            court_types_to_include: List of court types to include (default: all except redirects)
            sample_mode: If True, only scrape a few dates for testing
        """
        
        # Default to all court types except those that redirect
        if court_types_to_include is None:
            court_types_to_include = [ct for ct in self.court_types.keys() if ct not in self.redirect_court_types]
        
        logging.info(f"Starting comprehensive scraping from year {start_year}")
        logging.info(f"Court types to include: {court_types_to_include}")
        
        # Get all courts for all types
        all_courts = []
        for court_type in court_types_to_include:
            courts = self.get_court_list(court_type)
            all_courts.extend(courts)
        
        total_courts = len(all_courts)
        logging.info(f"Total courts to scrape: {total_courts}")
        
        # Generate date range
        if sample_mode:
            # For testing: only a few days from start year
            dates = self.generate_date_range(start_year, start_year, 1, 1)[:10]  # First 10 days
            logging.info(f"SAMPLE MODE: Testing with {len(dates)} dates")
        else:
            dates = self.generate_date_range(start_year, end_year)
        
        total_searches = len(dates) * total_courts
        logging.info(f"Total searches to perform: {total_searches:,}")
        
        # Track progress
        search_count = 0
        results_found = 0
        
        # Main scraping loop: for each court, go through all dates
        for court_idx, court in enumerate(all_courts):
            logging.info(f"\nProcessing court {court_idx + 1}/{total_courts}: {court['name']} ({court['type_name']})")
            
            for date_idx, date_string in enumerate(dates):
                search_count += 1
                
                try:
                    # Log progress every 100 searches
                    if search_count % 100 == 0:
                        progress = (search_count / total_searches) * 100
                        logging.info(f"Progress: {search_count:,}/{total_searches:,} ({progress:.1f}%) - Found {results_found} decisions so far")
                    
                    decisions = self.search_by_date_and_court(court, date_string)
                    
                    if decisions:
                        self.all_decisions.extend(decisions)
                        results_found += len(decisions)
                        logging.info(f"  ✓ {date_string}: {len(decisions)} decisions from {court['name']}")
                    
                    # Rate limiting - be respectful to the server
                    time.sleep(1.5)
                    
                except Exception as e:
                    logging.error(f"Error processing {court['name']} for date {date_string}: {e}")
                    continue
        
        logging.info(f"\nScraping completed!")
        logging.info(f"Total searches performed: {search_count:,}")
        logging.info(f"Total decisions found: {results_found}")
        
        return self.all_decisions
    
    def save_results(self, filename="comprehensive_court_decisions.csv"):
        """Save results to CSV with comprehensive summary"""
        if not self.all_decisions:
            logging.warning("No data to save")
            return
        
        try:
            # Create DataFrame
            df = pd.DataFrame(self.all_decisions)
            
            # Save to CSV
            df.to_csv(filename, index=False, encoding='utf-8')
            logging.info(f"Saved {len(self.all_decisions)} decisions to {filename}")
            
            # Generate comprehensive summary
            summary = {
                'total_decisions': len(self.all_decisions),
                'scraping_date': datetime.now().isoformat(),
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
            
            # Save summary as JSON
            summary_filename = filename.replace('.csv', '_summary.json')
            with open(summary_filename, 'w', encoding='utf-8') as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)
            
            # Print summary
            self._print_summary(summary)
                
        except Exception as e:
            logging.error(f"Error saving results: {e}")
    
    def _print_summary(self, summary):
        """Print comprehensive summary"""
        logging.info("=== COMPREHENSIVE SCRAPING SUMMARY ===")
        logging.info(f"Total decisions found: {summary['total_decisions']:,}")
        logging.info(f"Unique courts covered: {summary['unique_courts']}")
        logging.info(f"Court types covered: {len(summary['court_types_covered'])}")
        logging.info(f"Date range: {summary['date_range']['earliest']} to {summary['date_range']['latest']}")
        
        logging.info("\nDecisions by Court Type:")
        for court_type, count in summary['decisions_by_court_type'].items():
            logging.info(f"  {court_type}: {count:,}")
        
        logging.info(f"\nTop 5 Courts by Decision Count:")
        for court, count in list(summary['decisions_by_court'].items())[:5]:
            logging.info(f"  {court}: {count}")
        
        logging.info(f"\nDownload Status:")
        logging.info(f"  With download links: {summary['decisions_with_downloads']:,}")
        logging.info(f"  Upload pending: {summary['decisions_upload_pending']:,}")
        logging.info(f"  No download: {summary['decisions_no_download']:,}")

def main():
    """Main execution function"""
    scraper = ComprehensiveCourtScraper()
    
    # Configuration options:
    
    # SAMPLE MODE for testing (recommended first)
    sample_mode = True
    start_year = 2069  # As requested by user
    
    # Court types to include (all except redirects by default)
    court_types_to_include = ['S', 'A', 'D', 'T']  # Start with main courts
    
    logging.info("Starting COMPREHENSIVE court scraping...")
    logging.info(f"Sample mode: {sample_mode}")
    logging.info(f"Starting from year: {start_year}")
    
    # Perform scraping
    decisions = scraper.scrape_comprehensive(
        start_year=start_year,
        court_types_to_include=court_types_to_include,
        sample_mode=sample_mode
    )
    
    # Save results
    if decisions:
        filename = "sample_comprehensive_decisions.csv" if sample_mode else "comprehensive_court_decisions.csv"
        scraper.save_results(filename)
        logging.info("Comprehensive scraping completed successfully!")
        
        if sample_mode:
            logging.info("\n🧪 SAMPLE MODE completed. Review results and then run with sample_mode=False for full scraping.")
    else:
        logging.warning("No decisions found. Check search parameters or network connectivity.")

if __name__ == "__main__":
    main() 