#!/usr/bin/env python3
"""
Debug script to examine responses from redirect court websites.
This helps us understand why searches return no results.
"""

import requests
from bs4 import BeautifulSoup
import time

def debug_court_response(name, url):
    """Debug a specific court's response."""
    print(f"\n{'='*60}")
    print(f"DEBUGGING {name}")
    print(f"URL: {url}")
    print(f"{'='*60}")
    
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
    })
    
    try:
        # Get the initial page
        print("1. Getting initial page...")
        response = session.get(url)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find the form
        form = soup.find('form')
        if not form:
            print("❌ No form found!")
            return
        
        print("✅ Form found")
        
        # Extract form details
        action = form.get('action', '')
        method = form.get('method', 'GET')
        print(f"Form action: {action}")
        print(f"Form method: {method}")
        
        # Get all inputs
        inputs = form.find_all(['input', 'select', 'textarea'])
        print(f"Form inputs: {len(inputs)}")
        
        form_data = {}
        for inp in inputs:
            name = inp.get('name')
            input_type = inp.get('type', inp.name)
            value = inp.get('value', '')
            print(f"  - {input_type}: {name} = '{value}'")
            
            if name:
                if input_type == 'hidden':
                    form_data[name] = value
                elif input_type == 'text':
                    if 'date' in name.lower() or 'मिति' in name:
                        # Try different date formats
                        form_data[name] = '2081-01-01'  # More recent date
                    else:
                        form_data[name] = ''
        
        print(f"\nForm data to submit: {form_data}")
        
        # Submit the form
        print("\n2. Submitting form...")
        time.sleep(1)
        
        if method.upper() == 'POST':
            if action:
                submit_url = requests.compat.urljoin(url, action)
            else:
                submit_url = url
            response = session.post(submit_url, data=form_data)
        else:
            if action:
                submit_url = requests.compat.urljoin(url, action)
            else:
                submit_url = url
            response = session.get(submit_url, params=form_data)
        
        print(f"Response status: {response.status_code}")
        print(f"Response URL: {response.url}")
        
        # Parse response
        result_soup = BeautifulSoup(response.content, 'html.parser')
        
        # Look for tables
        tables = result_soup.find_all('table')
        print(f"Tables in response: {len(tables)}")
        
        # Look for specific text patterns
        text_content = result_soup.get_text()
        
        # Check for "no records found" messages
        no_records_patterns = [
            'तपाईले खोज्नु भएको रेकर्ड भेटिएन',
            'No records found',
            'रेकर्ड भेटिएन',
            'कुनै रेकर्ड फेला परेन'
        ]
        
        found_patterns = []
        for pattern in no_records_patterns:
            if pattern in text_content:
                found_patterns.append(pattern)
        
        if found_patterns:
            print(f"❌ Found 'no records' messages: {found_patterns}")
        else:
            print("✅ No 'no records' messages found")
        
        # Look for any data tables or content
        if tables:
            print("\n3. Analyzing tables...")
            for i, table in enumerate(tables[:3]):
                rows = table.find_all('tr')
                print(f"Table {i+1}: {len(rows)} rows")
                
                if rows:
                    # Show first few rows
                    for j, row in enumerate(rows[:3]):
                        cells = row.find_all(['td', 'th'])
                        cell_texts = [cell.get_text(strip=True)[:30] for cell in cells]
                        print(f"  Row {j+1}: {cell_texts}")
        
        # Save response for manual inspection
        filename = f"debug_response_{name.lower().replace(' ', '_')}.html"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(response.text)
        print(f"\n📁 Response saved to: {filename}")
        
        # Show a sample of the response content
        print(f"\n📄 Response content preview (first 500 chars):")
        print("-" * 50)
        print(text_content[:500])
        print("-" * 50)
        
        return response
        
    except Exception as e:
        print(f"❌ Error debugging {name}: {e}")
        return None

def main():
    """Main debug function."""
    print("NEPAL REDIRECT COURTS DEBUG SCRIPT")
    print("Analyzing responses from all three redirect court websites...")
    
    courts = [
        ("Foreign Employment Tribunal", "http://fet.gov.np/causelist/cpfile.php"),
        ("Revenue Tribunal", "https://revenuetribunal.gov.np/rajaswoFaisalaPdf"),
        ("Administrative Court", "https://admincourt.gov.np/adminCourtFaisalaPdf")
    ]
    
    for name, url in courts:
        debug_court_response(name, url)
        time.sleep(2)  # Delay between requests
    
    print(f"\n{'='*60}")
    print("DEBUG COMPLETE")
    print("Check the saved HTML files for detailed response analysis.")
    print(f"{'='*60}")

if __name__ == "__main__":
    main() 