#!/usr/bin/env python3
"""
Quick test for Administrative Court only - we know it has data.
"""

from redirect_courts_scraper import RedirectCourtsScraper
import time

def test_admin_court():
    """Test Administrative Court scraping only."""
    print("=== Testing Administrative Court Only ===")
    print("We know this court has data for 2081-01-01...")
    
    # Initialize scraper
    scraper = RedirectCourtsScraper(delay=1.0)
    
    try:
        # Scrape just the Administrative Court
        print("\nScraping Administrative Court...")
        start_time = time.time()
        
        decisions = scraper.scrape_administrative_court()
        
        end_time = time.time()
        
        print(f"\n=== RESULTS ===")
        print(f"Time taken: {end_time - start_time:.2f} seconds")
        print(f"Decisions found: {len(decisions)}")
        
        if decisions:
            print(f"\n=== SAMPLE DECISION ===")
            sample = decisions[0]
            print("Fields found:")
            for key, value in sample.items():
                if isinstance(value, str) and len(value) > 50:
                    value = value[:50] + "..."
                print(f"  {key}: {value}")
            
            # Save the results
            scraper.all_results = decisions
            scraper.save_results("admin_court_test.csv")
            
            print(f"\nSuccess! Found {len(decisions)} decisions from Administrative Court")
            print("Results saved to admin_court_test.csv")
            
        else:
            print("No decisions found. Check log for details.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_admin_court() 