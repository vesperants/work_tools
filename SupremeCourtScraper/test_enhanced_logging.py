#!/usr/bin/env python3
"""
Test script to verify enhanced logging shows all courts being processed.
"""

import time
from redirect_courts_scraper import MegaRedirectCourtsScraper

def test_court_processing():
    """Test that all courts are being processed with enhanced logging."""
    print("🔍 TESTING ENHANCED COURT PROCESSING")
    print("=" * 50)
    
    # Initialize scraper with fewer tasks for testing
    scraper = MegaRedirectCourtsScraper(max_workers=3, delay=0.1)
    
    # Override task list with just a few test dates for each court
    test_dates = ['2069-01-01', '2069-01-15', '2069-06-01', '2069-06-15']
    test_tasks = []
    
    for date_str in test_dates:
        for court_key, court_config in scraper.court_configs.items():
            task = {
                'court_key': court_key,
                'court_config': court_config,
                'date': date_str,
                'task_id': f"{court_key}_{date_str}"
            }
            test_tasks.append(task)
    
    scraper.task_list = test_tasks
    
    print(f"Testing with {len(test_tasks)} tasks ({len(test_dates)} dates × 3 courts)")
    print("This should show processing for all three courts...")
    print()
    
    try:
        # Run the test
        decisions = scraper.run_mega_scraping()
        
        print(f"\n✅ Test completed!")
        print(f"📊 Total decisions found: {len(decisions)}")
        
        with scraper.stats_lock:
            print(f"\n📈 FINAL TASK COUNTS BY COURT:")
            for court_code, count in scraper.stats['tasks_processed_by_court'].items():
                court_name = next((config['name'] for config in scraper.court_configs.values() 
                                 if config['type_code'] == court_code), court_code)
                decisions_found = scraper.stats['by_court'][court_code]
                print(f"   {court_name} ({court_code}): {count} tasks processed, {decisions_found} decisions found")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

if __name__ == "__main__":
    test_court_processing() 