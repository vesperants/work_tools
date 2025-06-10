#!/usr/bin/env python3
"""
Test script for the Redirect Courts Scraper.
Tests connectivity and basic functionality for all three redirect court websites.
"""

import sys
import time
from redirect_courts_scraper import RedirectCourtsScraper

def test_court_connectivity(scraper, court_code, court_config):
    """
    Test basic connectivity to a court website.
    
    Args:
        scraper: RedirectCourtsScraper instance
        court_code (str): Court code (fet, revenue, admin)
        court_config (dict): Court configuration
        
    Returns:
        bool: True if connection successful, False otherwise
    """
    print(f"\n--- Testing {court_config['name']} ---")
    print(f"URL: {court_config['decisions_url']}")
    
    try:
        # Test basic connectivity
        response = scraper.make_request(court_config['decisions_url'])
        if not response:
            print("❌ Failed to connect")
            return False
        
        print(f"✅ Connection successful (Status: {response.status_code})")
        
        # Parse and analyze page structure
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Get page title
        title = soup.title.string if soup.title else "No title"
        print(f"📄 Page title: {title}")
        
        # Count forms
        forms = soup.find_all('form')
        print(f"📝 Forms found: {len(forms)}")
        
        # Analyze forms
        for i, form in enumerate(forms[:3]):  # Limit to first 3 forms
            action = form.get('action', 'No action')
            method = form.get('method', 'GET')
            inputs = form.find_all(['input', 'select', 'textarea'])
            print(f"   Form {i+1}: {method} -> {action} ({len(inputs)} inputs)")
            
            # Show input details
            for input_elem in inputs[:5]:  # Show first 5 inputs
                input_type = input_elem.get('type', input_elem.name)
                input_name = input_elem.get('name', 'unnamed')
                print(f"     - {input_type}: {input_name}")
        
        # Count tables
        tables = soup.find_all('table')
        print(f"📊 Tables found: {len(tables)}")
        
        # Analyze tables
        for i, table in enumerate(tables[:3]):  # Limit to first 3 tables
            rows = table.find_all('tr')
            print(f"   Table {i+1}: {len(rows)} rows")
            
            if rows:
                # Show header row
                header_cells = rows[0].find_all(['th', 'td'])
                if header_cells:
                    headers = [cell.get_text(strip=True)[:20] for cell in header_cells[:5]]
                    print(f"     Headers: {headers}")
        
        # Look for decision-related links
        links = soup.find_all('a', href=True)
        decision_links = []
        
        for link in links:
            text = link.get_text(strip=True).lower()
            if any(keyword in text for keyword in ['फैसला', 'decision', 'judgment', 'order', 'pdf']):
                decision_links.append(link.get_text(strip=True)[:50])
        
        print(f"🔗 Decision-related links: {len(decision_links)}")
        if decision_links:
            for link_text in decision_links[:3]:  # Show first 3
                print(f"   - {link_text}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing {court_config['name']}: {e}")
        return False

def test_scraping_functionality(scraper):
    """
    Test the actual scraping functionality.
    
    Args:
        scraper: RedirectCourtsScraper instance
    """
    print(f"\n{'='*60}")
    print("TESTING SCRAPING FUNCTIONALITY")
    print(f"{'='*60}")
    
    try:
        # Test each court's scraping method
        court_methods = [
            ('fet', scraper.scrape_foreign_employment_tribunal),
            ('revenue', scraper.scrape_revenue_tribunal),
            ('admin', scraper.scrape_administrative_court)
        ]
        
        total_decisions = 0
        
        for court_code, scrape_method in court_methods:
            court_config = scraper.court_configs[court_code]
            print(f"\n--- Testing {court_config['name']} Scraping ---")
            
            try:
                start_time = time.time()
                decisions = scrape_method()
                end_time = time.time()
                
                print(f"✅ Scraping completed in {end_time - start_time:.2f} seconds")
                print(f"📊 Decisions found: {len(decisions)}")
                
                if decisions:
                    # Show sample decision data
                    sample = decisions[0]
                    print(f"📝 Sample decision fields: {list(sample.keys())}")
                    
                    # Show some sample values
                    for key, value in list(sample.items())[:5]:
                        if isinstance(value, str) and len(value) > 50:
                            value = value[:50] + "..."
                        print(f"   {key}: {value}")
                
                total_decisions += len(decisions)
                
            except Exception as e:
                print(f"❌ Error scraping {court_config['name']}: {e}")
        
        print(f"\n📊 TOTAL DECISIONS FOUND: {total_decisions}")
        
        return total_decisions > 0
        
    except Exception as e:
        print(f"❌ Error in scraping functionality test: {e}")
        return False

def main():
    """
    Main test function.
    """
    print("="*60)
    print("NEPAL REDIRECT COURTS SCRAPER TEST")
    print("="*60)
    print("Testing connectivity and functionality for:")
    print("1. Foreign Employment Tribunal (fet.gov.np)")
    print("2. Revenue Tribunal (revenuetribunal.gov.np)")
    print("3. Administrative Court (admincourt.gov.np)")
    print("="*60)
    
    # Initialize scraper with longer delay for testing
    scraper = RedirectCourtsScraper(delay=2.0)
    
    connectivity_results = {}
    
    # Test connectivity for each court
    for court_code, court_config in scraper.court_configs.items():
        success = test_court_connectivity(scraper, court_code, court_config)
        connectivity_results[court_code] = success
    
    # Print connectivity summary
    print(f"\n{'='*60}")
    print("CONNECTIVITY TEST SUMMARY")
    print(f"{'='*60}")
    
    for court_code, success in connectivity_results.items():
        court_name = scraper.court_configs[court_code]['name']
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{court_name}: {status}")
    
    # Test scraping functionality if at least one site is accessible
    if any(connectivity_results.values()):
        scraping_success = test_scraping_functionality(scraper)
        
        print(f"\n{'='*60}")
        print("FINAL TEST RESULTS")
        print(f"{'='*60}")
        print(f"Connectivity: {sum(connectivity_results.values())}/3 sites accessible")
        print(f"Scraping: {'✅ WORKING' if scraping_success else '❌ NOT WORKING'}")
        
        if scraping_success:
            print("\n🎉 The redirect courts scraper is working!")
            print("You can now run the full scraper with: python redirect_courts_scraper.py")
        else:
            print("\n⚠️  The scraper needs further investigation.")
            print("Check the log file 'redirect_courts_scraper.log' for details.")
    else:
        print(f"\n❌ No court websites were accessible.")
        print("Please check your internet connection and try again.")

if __name__ == "__main__":
    main() 