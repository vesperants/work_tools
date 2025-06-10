#!/usr/bin/env python3
"""
Date-Based Supreme Court Scraper
Uses registration dates that are proven to work from our comprehensive testing
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import logging
import time
from datetime import datetime
import json

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('date_based_scraper.log'),
        logging.StreamHandler()
    ]
)

class DateBasedSupremeCourtScraper:
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
        
        self.court_types = {
            'S': 'सर्वोच्च अदालत',
            'A': 'उच्च अदालत', 
            'D': 'जिल्ला अदालत',
            'T': 'विशेष अदालत',
            'B': 'वैदेशिक रोजगार न्यायाधिकरण',
            'R': 'राजस्व न्यायाधिकरण कार्मण्डौ',
            'AD': 'प्रशासकीय अदालत'
        }
        
        self.all_decisions = []
        
        # Working dates from our comprehensive testing
        # These are the dates that returned results, organized by year for easy selection
        self.working_dates = {
            2069: [
                ("2069-01-15", 16), ("2069-03-01", 14), ("2069-03-15", 31), ("2069-06-01", 21),
                ("2069-06-15", 29), ("2069-06-29", 58), ("2069-09-01", 23), ("2069-09-29", 46),
                ("2069-12-01", 19), ("2069-12-15", 17), ("2069-12-30", 20)
            ],
            2070: [
                ("2070-01-15", 21), ("2070-01-30", 17), ("2070-03-30", 26), ("2070-06-01", 65),
                ("2070-06-15", 54), ("2070-09-01", 7), ("2070-09-29", 41), ("2070-12-30", 44)
            ],
            2075: [
                ("2075-03-01", 25), ("2075-03-15", 24), ("2075-06-01", 107), ("2075-06-15", 52),
                ("2075-09-01", 39), ("2075-09-15", 42), ("2075-09-29", 15), ("2075-12-01", 20),
                ("2075-12-15", 43)
            ],
            2076: [
                ("2076-01-15", 45), ("2076-01-30", 72), ("2076-03-01", 26), ("2076-03-15", 49),
                ("2076-03-30", 33), ("2076-06-01", 59), ("2076-06-29", 68), ("2076-09-01", 22),
                ("2076-09-15", 13), ("2076-09-29", 27), ("2076-12-30", 2)
            ],
            2077: [
                ("2077-01-30", 1), ("2077-03-01", 20), ("2077-03-15", 17), ("2077-03-30", 16),
                ("2077-06-15", 15), ("2077-06-29", 26), ("2077-09-01", 12), ("2077-09-15", 5),
                ("2077-09-29", 20), ("2077-12-01", 9), ("2077-12-30", 10)
            ],
            2078: [
                ("2078-01-15", 11), ("2078-03-01", 3), ("2078-03-15", 8), ("2078-06-01", 9),
                ("2078-06-15", 12), ("2078-09-01", 6), ("2078-09-29", 9), ("2078-12-01", 16),
                ("2078-12-15", 12), ("2078-12-30", 11)
            ],
            2079: [
                ("2079-01-15", 5), ("2079-03-01", 13), ("2079-03-15", 5), ("2079-03-30", 7),
                ("2079-04-01", 1), ("2079-09-01", 8), ("2079-09-29", 8), ("2079-12-01", 5),
                ("2079-12-15", 7), ("2079-12-30", 12)
            ],
            2080: [
                ("2080-01-15", 2), ("2080-03-15", 4), ("2080-04-01", 8), ("2080-06-01", 5),
                ("2080-06-15", 7), ("2080-06-29", 4), ("2080-09-01", 3), ("2080-09-29", 7),
                ("2080-12-01", 2), ("2080-12-15", 6), ("2080-12-30", 4)
            ],
            2081: [
                ("2081-03-30", 3), ("2081-06-15", 10), ("2081-09-01", 3), ("2081-09-29", 2),
                ("2081-12-01", 2), ("2081-12-15", 4)
            ]
        }
        
    def get_supreme_court_id(self):
        """Get the Supreme Court ID"""
        try:
            data = {'court_type': 'S', 'selected': 0}
            response = self.session.post(f"{self.base_url}welcome/get_courts", data=data)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            options = soup.find_all('option')
            
            for option in options:
                value = option.get('value', '')
                if value and value != '':
                    return value  # Should be '264' for Supreme Court
            
            return None
        except Exception as e:
            logging.error(f"Error getting Supreme Court ID: {e}")
            return None
    
    def search_by_date(self, court_id, date_string):
        """Search for decisions using registration date"""
        try:
            form_data = {
                'court_type': 'S',
                'court_id': court_id,
                'regno': '',
                'darta_date': date_string,  # Using registration date field
                'faisala_date': '',
                'submit': 'खोज्नु होस्'
            }
            
            response = self.session.post(self.base_url, data=form_data)
            response.raise_for_status()
            
            return self.parse_search_results(response.text, date_string)
            
        except Exception as e:
            logging.error(f"Error searching for date {date_string}: {e}")
            return []
    
    def parse_search_results(self, html_content, search_date):
        """Parse search results and extract decision data"""
        soup = BeautifulSoup(html_content, 'html.parser')
        decisions = []
        
        # Look for the main results table
        table = soup.find('table', class_='table table-bordered sc-table table-responsive')
        
        if not table:
            # Check for no results message
            if 'भेटिएन' in html_content:
                logging.info(f"No results found for date {search_date}")
            else:
                logging.warning(f"Could not find results table for date {search_date}")
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
                
                decision_data = {
                    'search_date': search_date,
                    'court_type': 'सर्वोच्च अदालत',
                    'court_id': '264',
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
        
        logging.info(f"Parsed {len(decisions)} decisions from search results for date {search_date}")
        return decisions
    
    def scrape_by_year_selection(self, years_to_scrape=None, max_results_per_date=None):
        """
        Main scraping function using proven working dates
        
        Args:
            years_to_scrape: List of years to scrape (e.g., [2075, 2076]). If None, scrapes all.
            max_results_per_date: Maximum results to expect per date (for validation)
        """
        
        # Get Supreme Court ID
        court_id = self.get_supreme_court_id()
        if not court_id:
            logging.error("Could not get Supreme Court ID")
            return []
        
        logging.info(f"Using Supreme Court ID: {court_id}")
        
        # Determine which years to scrape
        if years_to_scrape is None:
            years_to_scrape = sorted(self.working_dates.keys())
        
        logging.info(f"Starting systematic scraping for years: {years_to_scrape}")
        
        total_found = 0
        expected_total = 0
        
        for year in years_to_scrape:
            if year not in self.working_dates:
                logging.warning(f"No working dates available for year {year}")
                continue
                
            year_dates = self.working_dates[year]
            expected_year_total = sum(count for _, count in year_dates)
            expected_total += expected_year_total
            
            logging.info(f"Processing year {year}: {len(year_dates)} dates, expecting ~{expected_year_total} results")
            
            for date_string, expected_count in year_dates:
                try:
                    logging.info(f"Searching date {date_string} (expecting ~{expected_count} results)")
                    
                    decisions = self.search_by_date(court_id, date_string)
                    
                    if decisions:
                        actual_count = len(decisions)
                        logging.info(f"  ✓ Found {actual_count} decisions for {date_string}")
                        
                        # Validate result count (allow some variance)
                        if abs(actual_count - expected_count) > 5:
                            logging.warning(f"  ⚠ Result count differs from expected: got {actual_count}, expected {expected_count}")
                        
                        self.all_decisions.extend(decisions)
                        total_found += actual_count
                    else:
                        logging.warning(f"  ✗ No results found for {date_string} (expected {expected_count})")
                    
                    # Rate limiting - be respectful to the server
                    time.sleep(2)
                    
                except Exception as e:
                    logging.error(f"Error processing date {date_string}: {e}")
                    continue
        
        logging.info(f"Scraping completed. Found {total_found} decisions (expected ~{expected_total})")
        return self.all_decisions
    
    def scrape_high_value_dates(self, min_results=20):
        """
        Scrape only dates that have a high number of results
        
        Args:
            min_results: Minimum number of results per date to include
        """
        high_value_dates = []
        
        for year, year_dates in self.working_dates.items():
            for date_string, expected_count in year_dates:
                if expected_count >= min_results:
                    high_value_dates.append((date_string, expected_count))
        
        # Sort by expected count (highest first)
        high_value_dates.sort(key=lambda x: x[1], reverse=True)
        
        logging.info(f"Scraping {len(high_value_dates)} high-value dates (min {min_results} results each)")
        
        # Get Supreme Court ID
        court_id = self.get_supreme_court_id()
        if not court_id:
            logging.error("Could not get Supreme Court ID")
            return []
        
        total_found = 0
        
        for date_string, expected_count in high_value_dates:
            try:
                logging.info(f"Searching high-value date {date_string} (expecting {expected_count} results)")
                
                decisions = self.search_by_date(court_id, date_string)
                
                if decisions:
                    actual_count = len(decisions)
                    logging.info(f"  ✓ Found {actual_count} decisions for {date_string}")
                    self.all_decisions.extend(decisions)
                    total_found += actual_count
                else:
                    logging.warning(f"  ✗ No results found for {date_string}")
                
                # Rate limiting
                time.sleep(2)
                
            except Exception as e:
                logging.error(f"Error processing date {date_string}: {e}")
                continue
        
        logging.info(f"High-value scraping completed. Found {total_found} decisions")
        return self.all_decisions
    
    def save_results(self, filename="supreme_court_decisions_date_based.csv"):
        """Save results to CSV and generate summary"""
        if not self.all_decisions:
            logging.warning("No data to save")
            return
        
        try:
            # Create DataFrame
            df = pd.DataFrame(self.all_decisions)
            
            # Save to CSV
            df.to_csv(filename, index=False, encoding='utf-8')
            logging.info(f"Saved {len(self.all_decisions)} decisions to {filename}")
            
            # Generate summary
            summary = {
                'total_decisions': len(self.all_decisions),
                'scraping_date': datetime.now().isoformat(),
                'unique_dates_scraped': len(df['search_date'].unique()),
                'date_range': {
                    'earliest': df['search_date'].min(),
                    'latest': df['search_date'].max()
                },
                'decisions_by_search_date': df['search_date'].value_counts().to_dict(),
                'decisions_with_downloads': len(df[df['download_url'].str.contains('http', na=False)]),
                'decisions_upload_pending': len(df[df['download_url'] == 'Upload Pending']),
                'decisions_no_download': len(df[df['download_url'] == 'N/A']),
                'case_types': df['case_type'].value_counts().head(10).to_dict()
            }
            
            # Save summary as JSON
            summary_filename = filename.replace('.csv', '_summary.json')
            with open(summary_filename, 'w', encoding='utf-8') as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)
            
            # Print summary
            logging.info("=== SCRAPING SUMMARY ===")
            logging.info(f"Total decisions found: {summary['total_decisions']}")
            logging.info(f"Unique dates scraped: {summary['unique_dates_scraped']}")
            logging.info(f"Date range: {summary['date_range']['earliest']} to {summary['date_range']['latest']}")
            logging.info(f"With download links: {summary['decisions_with_downloads']}")
            logging.info(f"Upload pending: {summary['decisions_upload_pending']}")
            logging.info(f"No download available: {summary['decisions_no_download']}")
            
            # Show top case types
            logging.info("Top case types:")
            for case_type, count in list(summary['case_types'].items())[:5]:
                logging.info(f"  {case_type}: {count}")
                
        except Exception as e:
            logging.error(f"Error saving results: {e}")

def main():
    """Main execution function"""
    scraper = DateBasedSupremeCourtScraper()
    
    # Configuration options:
    
    # Option 1: Scrape specific years (recommended for testing)
    years_to_scrape = [2075, 2076]  # High-value years with most results
    
    # Option 2: Scrape all available years
    # years_to_scrape = None
    
    # Option 3: Scrape only high-value dates (quick option)
    # scraper.scrape_high_value_dates(min_results=30)
    
    logging.info("Starting date-based scraping of Supreme Court decisions...")
    
    # Perform scraping
    decisions = scraper.scrape_by_year_selection(years_to_scrape=years_to_scrape)
    
    # Save results
    if decisions:
        scraper.save_results()
        logging.info("Date-based scraping completed successfully!")
    else:
        logging.warning("No decisions found. Check search parameters or network connectivity.")

if __name__ == "__main__":
    main() 