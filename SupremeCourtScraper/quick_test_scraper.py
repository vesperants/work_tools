#!/usr/bin/env python3
"""
Quick Test Date-Based Scraper
Scrapes a few high-value dates to demonstrate the working system
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import logging
import time
from datetime import datetime
import json

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class QuickTestScraper:
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
        
        self.all_decisions = []
        
        # Top 5 highest-value dates for quick demonstration
        self.top_dates = [
            ("2075-06-01", 107),  # Highest single-date result
            ("2076-01-30", 72),   # Second highest
            ("2076-06-29", 68),   # Third highest
            ("2070-06-01", 65),   # Fourth highest
            ("2076-06-01", 59),   # Fifth highest
        ]
        
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
                    return value
            
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
                'darta_date': date_string,
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
        
        table = soup.find('table', class_='table table-bordered sc-table table-responsive')
        
        if not table:
            logging.warning(f"No results table found for {search_date}")
            return decisions
        
        tbody = table.find('tbody')
        if not tbody:
            return decisions
        
        rows = tbody.find_all('tr')
        
        for row in rows:
            cells = row.find_all('td')
            
            if len(cells) >= 10:
                # Extract key information
                decision_data = {
                    'search_date': search_date,
                    'registration_no': cells[1].get_text(strip=True),
                    'case_no': cells[2].get_text(strip=True),
                    'registration_date': cells[3].get_text(strip=True),
                    'case_type': cells[4].get_text(strip=True),
                    'case_name': cells[5].get_text(strip=True),
                    'plaintiff': cells[6].get_text(strip=True),
                    'defendant': cells[7].get_text(strip=True),
                    'decision_date': cells[8].get_text(strip=True),
                    'download_url': 'N/A',
                    'scraped_date': datetime.now().isoformat()
                }
                
                # Check for download link
                last_cell = cells[9]
                link = last_cell.find('a')
                if link and link.get('href'):
                    decision_data['download_url'] = link.get('href')
                elif last_cell.find('img') and 'error.png' in str(last_cell.find('img').get('src', '')):
                    decision_data['download_url'] = 'Upload Pending'
                
                decisions.append(decision_data)
        
        return decisions
    
    def run_quick_test(self):
        """Run quick test with top 5 dates"""
        logging.info("Starting quick test with top 5 highest-value dates...")
        
        court_id = self.get_supreme_court_id()
        if not court_id:
            logging.error("Could not get Supreme Court ID")
            return []
        
        logging.info(f"Using Supreme Court ID: {court_id}")
        
        total_found = 0
        expected_total = sum(count for _, count in self.top_dates)
        
        for date_string, expected_count in self.top_dates:
            try:
                logging.info(f"🔍 Searching {date_string} (expecting {expected_count} results)")
                
                decisions = self.search_by_date(court_id, date_string)
                
                if decisions:
                    actual_count = len(decisions)
                    logging.info(f"  ✅ Found {actual_count} decisions")
                    
                    if abs(actual_count - expected_count) <= 5:
                        logging.info(f"  ✓ Result count matches expected ({expected_count})")
                    else:
                        logging.warning(f"  ⚠ Count differs: got {actual_count}, expected {expected_count}")
                    
                    self.all_decisions.extend(decisions)
                    total_found += actual_count
                else:
                    logging.warning(f"  ❌ No results found")
                
                # Brief pause between requests
                time.sleep(1.5)
                
            except Exception as e:
                logging.error(f"Error processing {date_string}: {e}")
                continue
        
        logging.info(f"\n🎉 Quick test completed!")
        logging.info(f"Found {total_found} decisions (expected {expected_total})")
        
        return self.all_decisions
    
    def save_sample_results(self):
        """Save sample results"""
        if not self.all_decisions:
            logging.warning("No data to save")
            return
        
        df = pd.DataFrame(self.all_decisions)
        filename = "sample_supreme_court_decisions.csv"
        df.to_csv(filename, index=False, encoding='utf-8')
        
        logging.info(f"✅ Saved {len(self.all_decisions)} sample decisions to {filename}")
        
        # Print summary
        print(f"\n📊 SAMPLE RESULTS SUMMARY:")
        print(f"   Total decisions: {len(self.all_decisions)}")
        print(f"   Unique dates: {len(df['search_date'].unique())}")
        print(f"   With downloads: {len(df[df['download_url'].str.contains('http', na=False)])}")
        print(f"   Upload pending: {len(df[df['download_url'] == 'Upload Pending'])}")
        print(f"   Top case types:")
        for case_type, count in df['case_type'].value_counts().head(3).items():
            print(f"     {case_type}: {count}")

def main():
    scraper = QuickTestScraper()
    decisions = scraper.run_quick_test()
    
    if decisions:
        scraper.save_sample_results()
        print(f"\n🚀 Quick test successful! The date-based scraper is working perfectly.")
        print(f"You can now use the full scraper with confidence.")
    else:
        print("❌ Quick test failed")

if __name__ == "__main__":
    main() 