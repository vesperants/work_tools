# Supreme Court of Nepal Decision Scraper

A Python scraper for extracting court decisions (faisalas) from the Supreme Court of Nepal website at https://supremecourt.gov.np/cp/#listTable

## Features

- Scrapes court decisions from multiple court types (Supreme, High, District, Special courts)
- Extracts comprehensive case information including:
  - Case registration details
  - Plaintiff and defendant information  
  - Decision dates
  - Download URLs for full decision texts
- Handles dynamic court list loading
- Systematic date range searching
- CSV output with detailed metadata
- Comprehensive logging
- Rate limiting to be respectful to the server

## Installation

1. Install required Python packages:
```bash
pip install -r requirements.txt
```

## Usage

### Quick Test

First, run the test script to verify functionality:
```bash
python test_scraper.py
```

### Basic Usage

Run the main scraper with default settings (Supreme Court, recent years):
```bash
python supreme_court_scraper.py
```

### Advanced Configuration

You can modify the scraper parameters in the `main()` function:

```python
# Court types to scrape
court_types_to_scrape = ['S', 'A', 'D', 'T']  # All courts
# court_types_to_scrape = ['S']  # Supreme Court only

# Date range (Nepali calendar years)
start_year = 2069  # Start from 2069 (all available data)
# start_year = 2079  # Recent years only (2022-2023)

scraper.scrape_all_courts(
    court_types=court_types_to_scrape,
    date_range_start=start_year
)
```

## Court Types

- **S**: सर्वोच्च अदालत (Supreme Court)
- **A**: उच्च अदालत (High Court)  
- **D**: जिल्ला अदालत (District Court)
- **T**: बिषेश अदालत (Special Court)

Note: The following court types redirect to different websites:
- **B**: वैदेशिक रोजगार न्यायाधिकरण (Foreign Employment Tribunal)
- **R**: राजश्व न्यायाधिकरण (Revenue Tribunal)
- **AD**: प्रशासकीय अदालत (Administrative Court)

## Output Files

The scraper generates several output files:

1. **supreme_court_decisions.csv** - Main CSV file with all scraped decisions
2. **supreme_court_decisions_summary.txt** - Summary statistics
3. **scraper.log** - Detailed scraping logs

## CSV Output Columns

- `court_type` - Type of court (Nepali name)
- `court_name` - Specific court name
- `court_id` - Internal court ID
- `serial_no` - Serial number from results
- `registration_no` - Case registration number
- `case_no` - Case number
- `registration_date` - Case registration date (Nepali calendar)
- `case_type` - Type of case
- `case_name` - Case name/title
- `plaintiff` - Plaintiff information
- `defendant` - Defendant information
- `decision_date` - Decision date (Nepali calendar)
- `download_url` - URL for full decision text (or 'N/A' if not available)
- `scraped_date` - When this record was scraped

## Date Format

The scraper uses Nepali calendar dates in YYYY-MM-DD format:
- 2069 = approximately 2012 (when digital records begin)
- 2081 = approximately 2024 (current year)

## Customization

### Search Strategy

The scraper systematically searches by:
1. Iterating through all court types
2. Getting the list of courts for each type
3. Searching each court with date ranges
4. Currently uses registration date (`darta_date`) for searching

You can modify the search strategy in the `scrape_all_courts()` method to:
- Search by decision date (`faisala_date`) instead
- Use specific case registration numbers
- Implement different date range strategies

### Rate Limiting

The scraper includes a 1-second delay between requests. You can adjust this in the `scrape_all_courts()` method:

```python
time.sleep(1)  # Increase for slower scraping
```

## Troubleshooting

### Common Issues

1. **Connection Errors**: Check internet connection and website availability
2. **No Results**: The website may be down or search parameters may need adjustment
3. **Parsing Errors**: Website structure may have changed - check logs for details

### Debugging

Check the `scraper.log` file for detailed information about:
- Which searches are being performed
- How many results are found
- Any errors encountered

## Legal and Ethical Considerations

- This scraper is for educational and research purposes
- Be respectful to the server with appropriate rate limiting
- The scraped data is public information from the official court website
- Always verify important legal information from official sources

## Contributing

Feel free to improve the scraper by:
- Adding support for additional search parameters
- Improving the parsing logic for different result formats
- Adding support for other court websites (B, R, AD types)
- Enhancing error handling and recovery

## Limitations

- Depends on the current website structure and may break if the site changes
- Date range searching may miss some cases if not all dates are tried
- Large-scale scraping may take considerable time due to rate limiting
- Some older records may not be available digitally 