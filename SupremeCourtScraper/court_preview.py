#!/usr/bin/env python3
"""
Court Preview Script
Shows all available courts across all types before running comprehensive scraper
"""

import requests
from bs4 import BeautifulSoup
import logging
import json

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class CourtPreview:
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
            'S': 'सर्वोच्च अदालत',           # Supreme Court
            'A': 'उच्च अदालत',              # High Court  
            'D': 'जिल्ला अदालत',            # District Court
            'T': 'विशेष अदालत',             # Special Court
            'B': 'वैदेशिक रोजगार न्यायाधिकरण', # Foreign Employment Tribunal
            'R': 'राजस्व न्यायाधिकरण',        # Revenue Tribunal
            'AD': 'प्रशासकीय अदालत'         # Administrative Court
        }
        
        self.redirect_court_types = ['B', 'R', 'AD']
        
    def get_court_list(self, court_type):
        """Get the list of all courts for a given court type"""
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
            
            return courts
            
        except Exception as e:
            logging.error(f"Error getting court list for type {court_type}: {e}")
            return []
    
    def preview_all_courts(self):
        """Preview all available courts across all types"""
        logging.info("🔍 Discovering all available courts...")
        
        all_courts = {}
        total_courts = 0
        
        for court_type, type_name in self.court_types.items():
            logging.info(f"\n📋 Getting courts for type: {court_type} ({type_name})")
            
            if court_type in self.redirect_court_types:
                logging.info(f"   ⚠️  Note: {court_type} redirects to different website")
            
            courts = self.get_court_list(court_type)
            
            if courts:
                all_courts[court_type] = {
                    'type_name': type_name,
                    'count': len(courts),
                    'courts': courts,
                    'redirects': court_type in self.redirect_court_types
                }
                total_courts += len(courts)
                
                logging.info(f"   ✅ Found {len(courts)} courts")
                
                # Show first few courts as preview
                for i, court in enumerate(courts[:3]):
                    logging.info(f"      {i+1}. {court['name']} (ID: {court['id']})")
                
                if len(courts) > 3:
                    logging.info(f"      ... and {len(courts) - 3} more courts")
            else:
                logging.info(f"   ❌ No courts found for type {court_type}")
        
        # Print summary
        logging.info(f"\n📊 COURT DISCOVERY SUMMARY")
        logging.info(f"Total court types: {len(all_courts)}")
        logging.info(f"Total individual courts: {total_courts}")
        
        logging.info(f"\nBreakdown by Court Type:")
        for court_type, info in all_courts.items():
            redirect_note = " (redirects)" if info['redirects'] else ""
            logging.info(f"  {court_type} - {info['type_name']}: {info['count']} courts{redirect_note}")
        
        # Calculate scraping scope
        main_courts = [ct for ct in all_courts.keys() if ct not in self.redirect_court_types]
        main_court_count = sum(all_courts[ct]['count'] for ct in main_courts)
        
        # Date calculation (2069 to 2081 = 13 years)
        # Approximate days per year in Nepali calendar: 365
        total_days = 13 * 365
        total_searches = main_court_count * total_days
        
        logging.info(f"\n🎯 SCRAPING SCOPE CALCULATION:")
        logging.info(f"Main courts to scrape (excl. redirects): {main_court_count}")
        logging.info(f"Date range (2069-2081): ~{total_days:,} days")
        logging.info(f"Total searches required: {total_searches:,}")
        logging.info(f"Estimated time (1.5s per search): {total_searches * 1.5 / 3600:.1f} hours")
        
        # Save results
        with open('court_discovery.json', 'w', encoding='utf-8') as f:
            json.dump(all_courts, f, indent=2, ensure_ascii=False)
        
        logging.info(f"\n💾 Detailed court list saved to 'court_discovery.json'")
        
        return all_courts

def main():
    preview = CourtPreview()
    courts = preview.preview_all_courts()
    
    print(f"\n🎉 Court discovery completed!")
    print(f"Review the results above and in 'court_discovery.json'")
    print(f"\nTo proceed with comprehensive scraping:")
    print(f"1. Run sample mode first: python comprehensive_court_scraper.py")
    print(f"2. If satisfied, change sample_mode=False for full scraping")

if __name__ == "__main__":
    main() 