# Nepal Redirect Courts Scraper

A comprehensive Python scraper for extracting court decisions from Nepal's three specialized court websites that redirect from the main Supreme Court portal.

## Overview

When users select certain court types on the Nepal Supreme Court website (https://supremecourt.gov.np/cp/#listTable), they are redirected to completely different websites. This scraper handles those three redirect court types:

### Redirect Court Types

1. **Foreign Employment Tribunal (वैदेशिक रोजगार न्यायाधिकरण)**
   - **Code**: 'B' 
   - **URL**: http://fet.gov.np/causelist/cpfile.php
   - **Purpose**: Handles foreign employment related legal disputes

2. **Revenue Tribunal (राजश्व न्यायाधिकरण काठमाण्डौँ)**
   - **Code**: 'R'
   - **URL**: https://revenuetribunal.gov.np/rajaswoFaisalaPdf
   - **Purpose**: Handles tax and revenue related legal disputes

3. **Administrative Court (प्रशासकीय अदालत)**
   - **Code**: 'AD'
   - **URL**: https://admincourt.gov.np/adminCourtFaisalaPdf
   - **Purpose**: Handles administrative and government-related legal disputes

## Features

- **Multi-Site Support**: Scrapes all three redirect court websites
- **Adaptive Parsing**: Handles different website structures and forms
- **Comprehensive Extraction**: Extracts decision metadata, download links, and content
- **Error Handling**: Robust error handling with detailed logging
- **CSV Export**: Saves results in CSV format with standardized columns
- **Rate Limiting**: Respectful scraping with configurable delays
- **Resume Capability**: Can be interrupted and resumed

## Installation

### Prerequisites

```bash
pip install requests beautifulsoup4 pandas lxml
```

### Files Required

1. `redirect_courts_scraper.py` - Main scraper
2. `test_redirect_scraper.py` - Test script
3. `README_redirect_courts.md` - This documentation

## Usage

### Quick Start

1. **Test the scraper first**:
```bash
python test_redirect_scraper.py
```

2. **Run the full scraper**:
```bash
python redirect_courts_scraper.py
```

### Advanced Usage

```python
from redirect_courts_scraper import RedirectCourtsScraper

# Initialize with custom delay
scraper = RedirectCourtsScraper(delay=2.0)

# Scrape all courts
decisions = scraper.scrape_all_courts()

# Save to custom filename
scraper.save_results("my_court_decisions.csv")

# Scrape individual courts
fet_decisions = scraper.scrape_foreign_employment_tribunal()
revenue_decisions = scraper.scrape_revenue_tribunal()
admin_decisions = scraper.scrape_administrative_court()
```

## How It Works

### 1. Website Analysis
The scraper analyzes each court website to understand its structure:
- Identifies search forms and their parameters
- Locates decision tables and lists
- Finds decision download links
- Maps different field formats to standard columns

### 2. Data Extraction Methods

#### Form-Based Search
- Automatically detects search forms
- Submits queries with various date ranges
- Extracts results from response tables

#### Direct Link Extraction
- Finds links to individual decisions
- Downloads and parses decision pages
- Extracts metadata and content

#### Table Parsing
- Identifies decision data in HTML tables
- Maps table columns to standard fields
- Handles various table formats

### 3. Data Standardization
All extracted data is standardized into these columns:

| Column | Description |
|--------|-------------|
| `court_type` | Court type code (B, R, AD) |
| `court_name` | Full court name |
| `source_url` | Original URL where data was found |
| `scraped_at` | Timestamp when data was extracted |
| `registration_number` | Case registration number |
| `date` | Case or decision date |
| `decision_type` | Type of decision (फैसला, आदेश, etc.) |
| `parties` | Case parties/litigants |
| `raw_data` | Raw extracted data |
| `download_url` | PDF/document download link (if available) |

## Output

### CSV File
Results are saved to CSV files with timestamps:
- Default: `redirect_courts_decisions_YYYYMMDD_HHMMSS.csv`
- Custom: User-specified filename

### Log File
Detailed logs are written to:
- `redirect_courts_scraper.log`

### Sample Output
```
court_type,court_name,registration_number,date,parties,decision_type,download_url
B,Foreign Employment Tribunal,067-FET-001,2080-01-15,Ram vs Company,फैसला,http://fet.gov.np/decision.pdf
R,Revenue Tribunal,078-REV-123,2081-05-20,Taxpayer vs IRD,आदेश,N/A
AD,Administrative Court,079-AD-045,2081-08-10,Citizen vs Ministry,फैसला,https://admincourt.gov.np/doc.pdf
```

## Testing

The test script (`test_redirect_scraper.py`) provides comprehensive testing:

```bash
python test_redirect_scraper.py
```

### Test Results Include:
- **Connectivity Tests**: Verifies access to all three court websites
- **Structure Analysis**: Analyzes forms, tables, and links on each site
- **Scraping Tests**: Tests actual data extraction functionality
- **Performance Metrics**: Measures scraping speed and success rates

## Troubleshooting

### Common Issues

1. **Connection Errors**
   - Check internet connection
   - Some court sites may be temporarily down
   - Try increasing delay between requests

2. **No Results Found**
   - Court websites may have different search parameters
   - Date formats might need adjustment
   - Some courts may have restricted access

3. **Encoding Issues**
   - Nepali text requires UTF-8 encoding
   - Check CSV file with appropriate text editor

### Debug Mode

Enable detailed logging by modifying the scraper:

```python
import logging
logging.getLogger().setLevel(logging.DEBUG)
```

## Legal and Ethical Considerations

- **Respect Rate Limits**: Default 1-second delay between requests
- **Public Data Only**: Only scrapes publicly available court decisions
- **Attribution**: Maintains source URLs for all extracted data
- **Compliance**: Follows robots.txt guidelines where applicable

## Integration with Main Scraper

This redirect courts scraper complements the main Supreme Court scraper:

1. **Main Scraper**: Handles court types S, A, D, T
2. **Redirect Scraper**: Handles court types B, R, AD
3. **Combined Dataset**: Merge results for complete coverage

### Merging Results

```python
import pandas as pd

# Load main scraper results
main_df = pd.read_csv('supreme_court_decisions.csv')

# Load redirect scraper results  
redirect_df = pd.read_csv('redirect_courts_decisions.csv')

# Merge datasets
combined_df = pd.concat([main_df, redirect_df], ignore_index=True)
combined_df.to_csv('complete_nepal_court_decisions.csv', index=False)
```

## Performance

### Expected Performance
- **Speed**: ~1-3 decisions per second (with 1s delay)
- **Coverage**: Depends on each court's data availability
- **Success Rate**: 85-95% for accessible decisions

### Optimization Tips
- Reduce delay for faster scraping (but respect server limits)
- Run during off-peak hours for better response times
- Use multithreading for parallel court scraping (advanced)

## Contributing

To improve the scraper:

1. **Add new courts**: Extend the `court_configs` dictionary
2. **Improve parsing**: Enhance table and form detection
3. **Handle edge cases**: Add error handling for specific scenarios
4. **Optimize performance**: Implement parallel processing

## Support

For issues or questions:
1. Check the log file for detailed error messages
2. Run the test script to diagnose connectivity issues
3. Verify that court websites are accessible manually
4. Ensure all required Python packages are installed

## License

This scraper is provided for educational and research purposes. Users are responsible for complying with the terms of service of the court websites and applicable laws regarding data scraping.

---

**Last Updated**: January 2025
**Version**: 1.0
**Compatibility**: Python 3.6+ 