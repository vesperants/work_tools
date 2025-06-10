#!/usr/bin/env python3
"""
Date Range Tester for Supreme Court Scraper
Tests different registration dates to find which ones return actual results
"""

import requests
from bs4 import BeautifulSoup
import logging
import time
import json
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class DateRangeTester:
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
    
    def test_date(self, court_id, date_string):
        """Test a specific date to see if it returns results"""
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
            
            # Parse response
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for results table
            table = soup.find('table', class_='table table-bordered sc-table table-responsive')
            
            if table:
                tbody = table.find('tbody')
                if tbody:
                    rows = tbody.find_all('tr')
                    return len(rows)  # Return number of results
            
            # Check for no results message
            if 'भेटिएन' in response.text:
                return 0
            
            # If no table and no "not found" message, something else might be wrong
            return -1
            
        except Exception as e:
            logging.error(f"Error testing date {date_string}: {e}")
            return -1
    
    def generate_test_dates(self):
        """Generate a comprehensive list of test dates to try"""
        test_dates = []
        
        # Test different years
        years_to_test = [2069, 2070, 2075, 2076, 2077, 2078, 2079, 2080, 2081]
        
        # For each year, test several months
        months_to_test = [1, 3, 6, 9, 12]  # Test different seasons
        
        # For each month, test beginning, middle, and end
        days_to_test = [1, 15, 30]
        
        for year in years_to_test:
            for month in months_to_test:
                for day in days_to_test:
                    # Adjust day for months that don't have 30 days
                    if month in [2] and day == 30:
                        day = 28
                    elif month in [4, 6, 9, 11] and day == 30:
                        day = 29
                    
                    date_string = f"{year:04d}-{month:02d}-{day:02d}"
                    test_dates.append(date_string)
        
        # Also test some specific dates that might be more likely to have data
        # (like start of fiscal years, etc.)
        additional_dates = [
            "2078-04-01",  # Start of Nepali fiscal year
            "2079-04-01",
            "2080-04-01",
            "2081-04-01",
            "2078-01-01",  # Start of calendar year
            "2079-01-01",
            "2080-01-01",
            "2081-01-01",
        ]
        
        test_dates.extend(additional_dates)
        
        # Remove duplicates and sort
        test_dates = sorted(list(set(test_dates)))
        
        return test_dates
    
    def run_comprehensive_test(self):
        """Run comprehensive date testing"""
        logging.info("Starting comprehensive date range testing...")
        
        # Get Supreme Court ID
        court_id = self.get_supreme_court_id()
        if not court_id:
            logging.error("Could not get Supreme Court ID")
            return
        
        logging.info(f"Using Supreme Court ID: {court_id}")
        
        # Generate test dates
        test_dates = self.generate_test_dates()
        logging.info(f"Testing {len(test_dates)} different dates...")
        
        results = {}
        successful_dates = []
        
        for i, date_string in enumerate(test_dates):
            logging.info(f"Testing date {i+1}/{len(test_dates)}: {date_string}")
            
            result_count = self.test_date(court_id, date_string)
            results[date_string] = result_count
            
            if result_count > 0:
                successful_dates.append((date_string, result_count))
                logging.info(f"  ✓ SUCCESS: Found {result_count} results for {date_string}")
            elif result_count == 0:
                logging.info(f"  - No results for {date_string}")
            else:
                logging.info(f"  ? Error testing {date_string}")
            
            # Rate limiting
            time.sleep(1.5)
        
        # Save detailed results
        with open('date_test_results.json', 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        # Print summary
        logging.info("\n=== DATE TESTING SUMMARY ===")
        logging.info(f"Total dates tested: {len(test_dates)}")
        logging.info(f"Dates with results: {len(successful_dates)}")
        
        if successful_dates:
            logging.info("\nSuccessful dates (with result counts):")
            for date_str, count in sorted(successful_dates, key=lambda x: x[1], reverse=True):
                logging.info(f"  {date_str}: {count} results")
            
            # Find date ranges that work
            successful_years = {}
            for date_str, count in successful_dates:
                year = date_str.split('-')[0]
                if year not in successful_years:
                    successful_years[year] = []
                successful_years[year].append((date_str, count))
            
            logging.info("\nResults by year:")
            for year in sorted(successful_years.keys()):
                total_results = sum(count for _, count in successful_years[year])
                logging.info(f"  {year}: {len(successful_years[year])} successful dates, {total_results} total results")
        else:
            logging.warning("No dates returned results!")
        
        return successful_dates

def main():
    tester = DateRangeTester()
    successful_dates = tester.run_comprehensive_test()
    
    if successful_dates:
        print(f"\n🎉 Found {len(successful_dates)} dates with results!")
        print("You can now use these dates for systematic scraping.")
    else:
        print("\n😞 No dates returned results. May need to try different search strategies.")

if __name__ == "__main__":
    main() 