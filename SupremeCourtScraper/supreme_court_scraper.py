#!/usr/bin/env python3
"""
Supreme Court of Nepal Decision Scraper
Scrapes court decisions (faisalas) from https://supremecourt.gov.np/cp/#listTable
"""

import requests
import csv
import time
import logging
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import pandas as pd
from urllib.parse import urljoin, urlparse
import re

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper.log'),
        logging.StreamHandler()
    ]
)

class SupremeCourtScraper:
    """
    Scraper for Nepal Supreme Court decisions website
    """
    
    def __init__(self, base_url="https://supremecourt.gov.np/cp/"):
        self.base_url = base_url
        self.session = requests.Session()
        # Add headers to mimic browser behavior
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        
        # Court type mappings
        self.court_types = {
            'S': 'सर्वोच्च अदालत',  # Supreme Court
            'A': 'उच्च अदालत',      # High Court  
            'D': 'जिल्ला अदालत',    # District Court
            'T': 'बिषेश अदालत'      # Special Court
        }
        
        # Data storage
        self.all_decisions = []
        
    def get_court_list(self, court_type, selected=0):
        """
        Get list of courts for a given court type
        This mimics the AJAX call that loads court names dynamically
        """
        try:
            url = urljoin(self.base_url, "welcome/get_courts")
            data = {
                'court_type': court_type,
                'selected': selected
            }
            
            response = self.session.post(url, data=data)
            response.raise_for_status()
            
            # Parse the HTML response to extract court options
            soup = BeautifulSoup(response.text, 'html.parser')
            courts = []
            
            # The response should contain <option> tags
            for option in soup.find_all('option'):
                if option.get('value') and option.get('value') != '':
                    courts.append({
                        'id': option.get('value'),
                        'name': option.text.strip()
                    })
            
            logging.info(f"Found {len(courts)} courts for type {court_type}")
            return courts
            
        except Exception as e:
            logging.error(f"Error getting court list for type {court_type}: {e}")
            return []
    
    def search_decisions(self, court_type, court_id, regno="", darta_date="", faisala_date=""):
        """
        Search for decisions using the form parameters
        """
        try:
            url = self.base_url  # Main search form URL
            
            # Prepare form data
            form_data = {
                'court_type': court_type,
                'court_id': court_id,
                'regno': regno,
                'darta_date': darta_date,
                'faisala_date': faisala_date,
                'submit': 'खोज्नु होस्'  # Submit button text
            }
            
            # Remove empty parameters
            form_data = {k: v for k, v in form_data.items() if v}
            
            logging.info(f"Searching with params: {form_data}")
            
            response = self.session.post(url, data=form_data)
            response.raise_for_status()
            
            return self.parse_search_results(response.text)
            
        except Exception as e:
            logging.error(f"Error searching decisions: {e}")
            return []
    
    def parse_search_results(self, html_content):
        """
        Parse the search results table and extract decision data
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        decisions = []
        
        # Look for results table
        # The table might have class 'sc-table' or similar
        tables = soup.find_all('table')
        
        for table in tables:
            rows = table.find_all('tr')
            
            # Skip header row
            for row in rows[1:] if len(rows) > 1 else []:
                cells = row.find_all(['td', 'th'])
                
                if len(cells) >= 8:  # Minimum expected columns
                    decision_data = {
                        'serial_no': cells[0].text.strip() if len(cells) > 0 else '',
                        'registration_no': cells[1].text.strip() if len(cells) > 1 else '',
                        'case_no': cells[2].text.strip() if len(cells) > 2 else '',
                        'registration_date': cells[3].text.strip() if len(cells) > 3 else '',
                        'case_type': cells[4].text.strip() if len(cells) > 4 else '',
                        'case_name': cells[5].text.strip() if len(cells) > 5 else '',
                        'plaintiff': cells[6].text.strip() if len(cells) > 6 else '',
                        'defendant': cells[7].text.strip() if len(cells) > 7 else '',
                        'decision_date': cells[8].text.strip() if len(cells) > 8 else '',
                        'download_url': 'N/A'
                    }
                    
                    # Look for download link in the last column (पुर्ण पाठ)
                    if len(cells) > 9:
                        last_cell = cells[9]
                        link = last_cell.find('a')
                        if link and link.get('href'):
                            download_url = urljoin(self.base_url, link.get('href'))
                            decision_data['download_url'] = download_url
                    
                    decisions.append(decision_data)
        
        # Check if no results found
        if not decisions:
            no_result_text = soup.find(text=re.compile(r'भेटिएन|नभेटिएको'))
            if no_result_text:
                logging.info("No results found for this search")
            else:
                logging.warning("Could not parse results table")
        
        return decisions
    
    def generate_date_ranges(self, start_year=2069, end_year=None):
        """
        Generate Nepali date ranges for systematic searching
        Nepali calendar format: YYYY-MM-DD
        """
        if end_year is None:
            end_year = 2081  # Current Nepali year (approximate)
        
        date_ranges = []
        
        for year in range(start_year, end_year + 1):
            for month in range(1, 13):  # 12 months
                # Generate month ranges
                date_str = f"{year:04d}-{month:02d}-01"
                date_ranges.append(date_str)
        
        return date_ranges
    
    def scrape_all_courts(self, court_types=['S'], date_range_start=2069):
        """
        Main scraping function - iterates through all courts and date ranges
        """
        logging.info("Starting comprehensive scraping...")
        
        for court_type in court_types:
            logging.info(f"Processing court type: {self.court_types.get(court_type, court_type)}")
            
            # Get list of courts for this type
            courts = self.get_court_list(court_type)
            
            if not courts:
                logging.warning(f"No courts found for type {court_type}")
                continue
            
            for court in courts:
                logging.info(f"Processing court: {court['name']} (ID: {court['id']})")
                
                # Generate date ranges for searching
                date_ranges = self.generate_date_ranges(start_year=date_range_start)
                
                for date_str in date_ranges:
                    try:
                        # Search using registration date
                        results = self.search_decisions(
                            court_type=court_type,
                            court_id=court['id'],
                            darta_date=date_str
                        )
                        
                        # Add metadata to results
                        for result in results:
                            result['court_type'] = self.court_types.get(court_type, court_type)
                            result['court_name'] = court['name']
                            result['court_id'] = court['id']
                            result['scraped_date'] = datetime.now().isoformat()
                        
                        self.all_decisions.extend(results)
                        
                        if results:
                            logging.info(f"Found {len(results)} decisions for {court['name']} on {date_str}")
                        
                        # Rate limiting - be respectful to the server
                        time.sleep(1)
                        
                    except Exception as e:
                        logging.error(f"Error processing {court['name']} for date {date_str}: {e}")
                        continue
    
    def save_to_csv(self, filename="supreme_court_decisions.csv"):
        """
        Save scraped data to CSV file
        """
        if not self.all_decisions:
            logging.warning("No data to save")
            return
        
        # Define CSV columns
        columns = [
            'court_type', 'court_name', 'court_id', 'serial_no', 
            'registration_no', 'case_no', 'registration_date', 
            'case_type', 'case_name', 'plaintiff', 'defendant', 
            'decision_date', 'download_url', 'scraped_date'
        ]
        
        try:
            df = pd.DataFrame(self.all_decisions)
            
            # Ensure all columns exist
            for col in columns:
                if col not in df.columns:
                    df[col] = ''
            
            # Reorder columns
            df = df[columns]
            
            # Save to CSV
            df.to_csv(filename, index=False, encoding='utf-8')
            logging.info(f"Saved {len(self.all_decisions)} decisions to {filename}")
            
            # Also save summary statistics
            summary_filename = filename.replace('.csv', '_summary.txt')
            with open(summary_filename, 'w', encoding='utf-8') as f:
                f.write(f"Supreme Court Scraping Summary\n")
                f.write(f"==============================\n\n")
                f.write(f"Total decisions scraped: {len(self.all_decisions)}\n")
                f.write(f"Scraping completed: {datetime.now()}\n\n")
                
                # Count by court type
                court_counts = df['court_type'].value_counts()
                f.write("Decisions by Court Type:\n")
                for court, count in court_counts.items():
                    f.write(f"  {court}: {count}\n")
                
                # Count decisions with download URLs
                with_urls = len(df[df['download_url'] != 'N/A'])
                f.write(f"\nDecisions with download URLs: {with_urls}\n")
                f.write(f"Decisions without download URLs: {len(df) - with_urls}\n")
            
            logging.info(f"Summary saved to {summary_filename}")
            
        except Exception as e:
            logging.error(f"Error saving to CSV: {e}")

def main():
    """
    Main execution function
    """
    scraper = SupremeCourtScraper()
    
    # Test with Supreme Court only first
    logging.info("Starting Supreme Court decision scraping...")
    
    # You can modify these parameters:
    court_types_to_scrape = ['S']  # Start with Supreme Court only
    start_year = 2079  # Recent years first (2022-2023)
    
    scraper.scrape_all_courts(
        court_types=court_types_to_scrape,
        date_range_start=start_year
    )
    
    # Save results
    scraper.save_to_csv("supreme_court_decisions.csv")

if __name__ == "__main__":
    main() 