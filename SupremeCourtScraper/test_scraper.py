#!/usr/bin/env python3
"""
Test script for Supreme Court scraper
Tests basic functionality before running full scraper
"""

from supreme_court_scraper import SupremeCourtScraper
import logging

# Set up logging for test
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def test_court_list():
    """Test getting court list for Supreme Court"""
    scraper = SupremeCourtScraper()
    
    logging.info("Testing court list retrieval...")
    courts = scraper.get_court_list('S')  # Supreme Court
    
    logging.info(f"Found courts: {courts}")
    return len(courts) > 0

def test_search_with_sample_data():
    """Test search with known sample data"""
    scraper = SupremeCourtScraper()
    
    # Test with Supreme Court and a recent date
    logging.info("Testing search functionality...")
    results = scraper.search_decisions(
        court_type='S',
        court_id='264',  # Supreme Court ID from HTML
        darta_date='2080-01-01'  # Sample date
    )
    
    logging.info(f"Search returned {len(results)} results")
    if results:
        logging.info(f"Sample result: {results[0]}")
    
    return True

def test_basic_functionality():
    """Run basic functionality tests"""
    logging.info("Starting basic functionality tests...")
    
    try:
        # Test 1: Court list retrieval
        if test_court_list():
            logging.info("✓ Court list retrieval test passed")
        else:
            logging.error("✗ Court list retrieval test failed")
            return False
        
        # Test 2: Search functionality
        if test_search_with_sample_data():
            logging.info("✓ Search functionality test completed")
        else:
            logging.error("✗ Search functionality test failed")
            return False
        
        logging.info("All basic tests completed successfully!")
        return True
        
    except Exception as e:
        logging.error(f"Test failed with error: {e}")
        return False

if __name__ == "__main__":
    test_basic_functionality() 