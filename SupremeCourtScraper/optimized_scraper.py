#!/usr/bin/env python3
"""
Optimized Supreme Court scraper based on successful search parameter discovery
Key finding: Searching with partial years (like "2080") in registration number field works
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import logging
import time
from datetime import datetime
import json
import os

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('optimized_scraper.log'),
        logging.StreamHandler()
    ]
)

class OptimizedSupremeCourtScraper:
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
        
    def get_court_list(self, court_type='S'):
        """Get the list of courts for a given type"""
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
                        'name': text
                    })
            
            return courts
        except Exception as e:
            logging.error(f"Error getting court list for {court_type}: {e}")
            return []
    
    def search_by_year(self, court_type, court_id, year):
        """Search for decisions using year in registration number field"""
        try:
            # Use the working search pattern: partial year in regno field
            form_data = {
                'court_type': court_type,
                'court_id': court_id,
                'regno': str(year),  # This is the key - search by year in regno field
                'darta_date': '',
                'faisala_date': '',
                'submit': 'खोज्नु होस्'
            }
            
            response = self.session.post(self.base_url, data=form_data)
            response.raise_for_status()
            
            return self.parse_search_results(response.text, court_type, court_id, year)
            
        except Exception as e:
            logging.error(f"Error searching for year {year}: {e}")
            return []
    
    def parse_search_results(self, html_content, court_type, court_id, search_year):
        """Parse search results and extract decision data"""
        soup = BeautifulSoup(html_content, 'html.parser')
        decisions = []
        
        # Look for the main results table
        table = soup.find('table', class_='table table-bordered sc-table table-responsive')
        
        if not table:
            # Check for no results message
            if 'भेटिएन' in html_content:
                logging.info(f"No results found for year {search_year}")
            else:
                logging.warning(f"Could not find results table for year {search_year}")
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
                    'search_year': search_year,
                    'court_type': self.court_types.get(court_type, court_type),
                    'court_id': court_id,
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
        
        logging.info(f"Parsed {len(decisions)} decisions from search results for year {search_year}")
        return decisions
    
    def scrape_systematic(self, court_types=['S'], start_year=2075, end_year=2081):
        """
        Main scraping function - systematically search by years
        Uses the working search pattern: partial year in registration number field
        """
        logging.info(f"Starting systematic scraping from year {start_year} to {end_year}")
        
        total_found = 0
        
        for court_type in court_types:
            logging.info(f"Processing court type: {self.court_types.get(court_type, court_type)}")
            
            # Get courts for this type
            courts = self.get_court_list(court_type)
            
            if not courts:
                logging.warning(f"No courts found for type {court_type}")
                continue
            
            for court in courts:
                logging.info(f"Processing court: {court['name']} (ID: {court['id']})")
                
                # Search by years - this is the pattern that works
                for year in range(start_year, end_year + 1):
                    try:
                        logging.info(f"Searching for year {year} in {court['name']}")
                        
                        decisions = self.search_by_year(court_type, court['id'], year)
                        
                        if decisions:
                            logging.info(f"Found {len(decisions)} decisions for year {year}")
                            self.all_decisions.extend(decisions)
                            total_found += len(decisions)
                        
                        # Rate limiting - be respectful
                        time.sleep(2)
                        
                    except Exception as e:
                        logging.error(f"Error processing year {year} for {court['name']}: {e}")
                        continue
        
        logging.info(f"Scraping completed. Total decisions found: {total_found}")
        return self.all_decisions
    
    def save_results(self, filename="supreme_court_decisions_optimized.csv"):
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
                'court_types_processed': list(df['court_type'].unique()),
                'years_found': sorted(list(df['search_year'].unique())),
                'decisions_by_year': df['search_year'].value_counts().to_dict(),
                'decisions_with_downloads': len(df[df['download_url'].str.contains('http', na=False)]),
                'decisions_upload_pending': len(df[df['download_url'] == 'Upload Pending']),
                'decisions_no_download': len(df[df['download_url'] == 'N/A'])
            }
            
            # Save summary as JSON
            summary_filename = filename.replace('.csv', '_summary.json')
            with open(summary_filename, 'w', encoding='utf-8') as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)
            
            # Print summary
            logging.info("=== SCRAPING SUMMARY ===")
            logging.info(f"Total decisions found: {summary['total_decisions']}")
            logging.info(f"Years with data: {summary['years_found']}")
            logging.info(f"Decisions by year: {summary['decisions_by_year']}")
            logging.info(f"With download links: {summary['decisions_with_downloads']}")
            logging.info(f"Upload pending: {summary['decisions_upload_pending']}")
            logging.info(f"No download available: {summary['decisions_no_download']}")
            
        except Exception as e:
            logging.error(f"Error saving results: {e}")

def main():
    """Main execution function"""
    scraper = OptimizedSupremeCourtScraper()
    
    # Configuration - you can modify these parameters
    court_types_to_scrape = ['S']  # Start with Supreme Court
    start_year = 2078  # Starting from recent years first
    end_year = 2081    # Current year (approximate)
    
    logging.info(f"Starting optimized scraping for years {start_year}-{end_year}")
    
    # Perform scraping
    decisions = scraper.scrape_systematic(
        court_types=court_types_to_scrape,
        start_year=start_year,
        end_year=end_year
    )
    
    # Save results
    if decisions:
        scraper.save_results()
        logging.info("Scraping completed successfully!")
    else:
        logging.warning("No decisions found. Check search parameters or network connectivity.")

if __name__ == "__main__":
    main() 