#!/usr/bin/env python3
"""
Advanced debugging script to find working search parameters for Supreme Court data
"""

import requests
from bs4 import BeautifulSoup
import logging
import time
import json

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class AdvancedDebugger:
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
        
    def get_court_list(self, court_type='S'):
        """Get the list of courts for debugging"""
        try:
            data = {'court_type': court_type, 'selected': 0}
            response = self.session.post(f"{self.base_url}welcome/get_courts", data=data)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            options = soup.find_all('option')
            courts = []
            
            logging.info(f"Raw response for court type {court_type}:")
            logging.info(f"Response length: {len(response.text)} characters")
            logging.info(f"Found {len(options)} option elements")
            
            for option in options:
                value = option.get('value', '')
                text = option.text.strip()
                logging.info(f"  Option: value='{value}', text='{text}'")
                
                if value and value != '':
                    courts.append({
                        'id': value,
                        'name': text
                    })
            
            return courts
        except Exception as e:
            logging.error(f"Error getting court list: {e}")
            return []
    
    def test_search_parameters(self):
        """Test various search parameter combinations to find what works"""
        
        courts = self.get_court_list('S')
        if not courts:
            logging.error("Could not get court list")
            return
        
        logging.info(f"Available courts for type 'S': {len(courts)}")
        for court in courts:
            logging.info(f"  {court['id']}: {court['name']}")
        
        # Use the first available court (likely the Supreme Court)
        supreme_court = courts[0] if courts else None
        
        if not supreme_court:
            logging.error("No courts available")
            return
        
        logging.info(f"Testing with: {supreme_court['name']} (ID: {supreme_court['id']})")
        
        # Test cases to try
        test_cases = [
            # Test 1: Empty search (might show recent cases)
            {
                'name': 'Empty search',
                'params': {
                    'court_type': 'S',
                    'court_id': supreme_court['id'],
                    'regno': '',
                    'darta_date': '',
                    'faisala_date': '',
                    'submit': 'खोज्नु होस्'
                }
            },
            
            # Test 2: Only court selection (minimal parameters)
            {
                'name': 'Court only',
                'params': {
                    'court_type': 'S',
                    'court_id': supreme_court['id'],
                    'submit': 'खोज्नु होस्'
                }
            },
            
            # Test 3: Recent Nepali year range
            {
                'name': 'Recent year 2081',
                'params': {
                    'court_type': 'S',
                    'court_id': supreme_court['id'],
                    'regno': '',
                    'darta_date': '2081-01-01',
                    'faisala_date': '',
                    'submit': 'खोज्नु होस्'
                }
            },
            
            # Test 4: Try older year
            {
                'name': 'Older year 2075',
                'params': {
                    'court_type': 'S',
                    'court_id': supreme_court['id'],
                    'regno': '',
                    'darta_date': '2075-01-01',
                    'faisala_date': '',
                    'submit': 'खोज्नु होस्'
                }
            },
            
            # Test 5: Try very recent year
            {
                'name': 'Very recent 2080',
                'params': {
                    'court_type': 'S',
                    'court_id': supreme_court['id'],
                    'regno': '',
                    'darta_date': '2080-01-01',
                    'faisala_date': '',
                    'submit': 'खोज्नु होस्'
                }
            },
            
            # Test 6: Try with registration number pattern
            {
                'name': 'Sample registration number',
                'params': {
                    'court_type': 'S',
                    'court_id': supreme_court['id'],
                    'regno': '2080-WO-001',
                    'darta_date': '',
                    'faisala_date': '',
                    'submit': 'खोज्नु होस्'
                }
            },
            
            # Test 7: Try partial registration number with year
            {
                'name': 'Partial registration with year',
                'params': {
                    'court_type': 'S',
                    'court_id': supreme_court['id'],
                    'regno': '2080',
                    'darta_date': '',
                    'faisala_date': '',
                    'submit': 'खोज्नु होस्'
                }
            },
            
            # Test 8: Try decision date instead of registration date
            {
                'name': 'Decision date only',
                'params': {
                    'court_type': 'S',
                    'court_id': supreme_court['id'],
                    'regno': '',
                    'darta_date': '',
                    'faisala_date': '2080-01-01',
                    'submit': 'खोज्नु होस्'
                }
            },
            
            # Test 9: Try different registration number format
            {
                'name': 'Different reg format',
                'params': {
                    'court_type': 'S',
                    'court_id': supreme_court['id'],
                    'regno': '077-WO-',
                    'darta_date': '',
                    'faisala_date': '',
                    'submit': 'खोज्नु होस्'
                }
            },
            
            # Test 10: Try broad date range
            {
                'name': 'Broad month search',
                'params': {
                    'court_type': 'S',
                    'court_id': supreme_court['id'],
                    'regno': '',
                    'darta_date': '2079-01',
                    'faisala_date': '',
                    'submit': 'खोज्नु होस्'
                }
            }
        ]
        
        results = {}
        
        for i, test_case in enumerate(test_cases):
            logging.info(f"Running test {i+1}: {test_case['name']}")
            
            try:
                response = self.session.post(self.base_url, data=test_case['params'])
                response.raise_for_status()
                
                # Analyze response
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Check for tables (results)
                tables = soup.find_all('table')
                
                # Check for "no results" message
                no_results = 'भेटिएन' in response.text
                
                # Check response length (different from form page)
                response_length = len(response.text)
                
                # Look for any data tables specifically
                data_tables = []
                for table in tables:
                    rows = table.find_all('tr')
                    if len(rows) > 1:  # More than header
                        first_row_cells = rows[1].find_all(['td', 'th']) if len(rows) > 1 else []
                        if len(first_row_cells) > 3:  # Likely a data table
                            data_tables.append(table)
                
                result = {
                    'success': response.status_code == 200,
                    'tables_found': len(tables),
                    'data_tables_found': len(data_tables),
                    'no_results_message': no_results,
                    'response_length': response_length,
                    'different_from_form': response_length != 15637  # The form page length we saw
                }
                
                # If we found data tables, examine them
                if data_tables:
                    for j, table in enumerate(data_tables):
                        rows = table.find_all('tr')
                        result[f'data_table_{j}_rows'] = len(rows)
                        
                        # Get sample data from first few rows
                        sample_data = []
                        for row in rows[:5]:  # First 5 rows including header
                            cells = row.find_all(['td', 'th'])
                            cell_texts = [cell.get_text(strip=True)[:50] for cell in cells[:8]]  # First 8 columns
                            if any(cell_texts):  # Not empty
                                sample_data.append(cell_texts)
                        result[f'data_table_{j}_sample'] = sample_data
                
                results[test_case['name']] = result
                
                logging.info(f"  Tables: {result['tables_found']}, Data Tables: {result['data_tables_found']}, No results: {result['no_results_message']}, Length: {result['response_length']}")
                
                # If this looks promising, save the response
                if result['data_tables_found'] > 0 or (result['tables_found'] > 0 and not result['no_results_message']):
                    filename = f"test_response_{i+1}_{test_case['name'].replace(' ', '_')}.html"
                    with open(filename, 'w', encoding='utf-8') as f:
                        f.write(response.text)
                    logging.info(f"  Saved promising response to {filename}")
                
                # Be respectful to the server
                time.sleep(1.5)
                
            except Exception as e:
                logging.error(f"  Error in test {test_case['name']}: {e}")
                results[test_case['name']] = {'error': str(e)}
        
        # Save results summary
        with open('debug_results.json', 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        # Print summary
        logging.info("\n=== TEST RESULTS SUMMARY ===")
        for test_name, result in results.items():
            if 'error' not in result:
                status = "PROMISING" if result.get('data_tables_found', 0) > 0 else ("SOME TABLES" if result.get('tables_found', 0) > 0 and not result.get('no_results_message', True) else "NO RESULTS")
                logging.info(f"{test_name}: {status} (Data Tables: {result.get('data_tables_found', 0)}, All Tables: {result.get('tables_found', 0)})")
            else:
                logging.info(f"{test_name}: ERROR - {result['error']}")
        
        return results

def main():
    debugger = AdvancedDebugger()
    debugger.test_search_parameters()

if __name__ == "__main__":
    main() 