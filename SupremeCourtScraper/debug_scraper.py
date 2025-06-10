#!/usr/bin/env python3
"""
Debug script to examine the actual response from the Supreme Court website
"""

import requests
from bs4 import BeautifulSoup
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)

def debug_search_response():
    """Debug the search response to understand the table structure"""
    
    base_url = "https://supremecourt.gov.np/cp/"
    
    # Create session with headers
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    })
    
    # Test search parameters - let's try a broader search
    form_data = {
        'court_type': 'S',
        'court_id': '264',
        'regno': '',
        'darta_date': '2080-01-01',  # Try recent date
        'faisala_date': '',
        'submit': 'खोज्नु होस्'
    }
    
    try:
        # Submit search
        response = session.post(base_url, data=form_data)
        response.raise_for_status()
        
        # Save response to file for examination
        with open('debug_response.html', 'w', encoding='utf-8') as f:
            f.write(response.text)
        
        print(f"Response saved to debug_response.html")
        print(f"Response length: {len(response.text)} characters")
        
        # Parse and analyze structure
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Look for any tables
        tables = soup.find_all('table')
        print(f"Found {len(tables)} tables")
        
        for i, table in enumerate(tables):
            print(f"\nTable {i+1}:")
            rows = table.find_all('tr')
            print(f"  Rows: {len(rows)}")
            
            if rows:
                # Show first few rows
                for j, row in enumerate(rows[:3]):
                    cells = row.find_all(['td', 'th'])
                    print(f"  Row {j+1}: {len(cells)} cells")
                    if cells:
                        cell_texts = [cell.get_text(strip=True)[:50] for cell in cells[:5]]
                        print(f"    Content: {cell_texts}")
        
        # Look for any text indicating results or no results
        result_text = soup.get_text()
        if 'भेटिएन' in result_text:
            print("\nFound 'भेटिएन' (not found) text in response")
        if 'रेकर्ड' in result_text:
            print("Found 'रेकर्ड' (record) text in response")
        
        # Look for specific elements that might contain results
        result_containers = soup.find_all(['div', 'section'], class_=lambda x: x and 'result' in x.lower())
        print(f"Found {len(result_containers)} potential result containers")
        
        # Look for elements with Nepali text patterns
        nepali_elements = soup.find_all(text=lambda text: text and any(ord(char) >= 0x0900 and ord(char) <= 0x097F for char in text))
        print(f"Found {len(nepali_elements)} elements with Nepali text")
        
        if nepali_elements:
            print("Sample Nepali text elements:")
            for elem in nepali_elements[:5]:
                clean_text = elem.strip()
                if clean_text and len(clean_text) > 5:
                    print(f"  '{clean_text[:100]}'")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_search_response() 