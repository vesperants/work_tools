# Auto-WebScraper for NKP Government Portal

A Python-based automated web scraper that monitors redirected links from the NKP Government Portal to detect new content and send email notifications.

## Features

- **CSV Processing**: Reads links from `sorted_links.csv` and processes only the redirected links
- **Redirect Detection**: Checks if links redirect to the home page (indicating no new content)
- **Email Notifications**: Sends email alerts when new content is found
- **Date-Indexed Logging**: Creates detailed logs for each run with timestamps
- **Scheduled Execution**: Runs automatically every 48 hours
- **Test Mode**: Allows testing with limited links before production deployment
- **Manual Execution**: Option to run the scraper manually
- **Duplicate Prevention**: Avoids processing already discovered links

## Installation

1. **Clone or download** the project files to your directory
2. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

1. **Create configuration file**:
   ```bash
   python webscraper.py --setup
   ```

2. **Edit `config.json`** with your email settings:
   ```json
   {
       "email": {
           "smtp_server": "smtp.gmail.com",
           "smtp_port": 587,
           "sender_email": "your_email@gmail.com",
           "sender_password": "your_app_password",
           "recipient_email": "recipient@gmail.com"
       }
   }
   ```

   **Note**: For Gmail, use an App Password instead of your regular password:
   - Go to your Google Account settings
   - Security → 2-Step Verification → App passwords
   - Generate a new app password and use it in the config

## Usage

### Test Mode (Recommended First)
Test the scraper with only 10 links to verify everything works:
```bash
python webscraper.py --test
```

### Manual Run
Run the scraper once manually:
```bash
python webscraper.py --run
```

### Scheduled Mode
Start the automatic scheduler (runs every 48 hours):
```bash
python webscraper.py --schedule
```

### Help
View all available options:
```bash
python webscraper.py --help
```

## File Structure

```
Autoscraper/
├── webscraper.py          # Main scraper application
├── requirements.txt       # Python dependencies
├── config.json           # Email configuration (created by --setup)
├── sorted_links.csv      # Input CSV file with links
├── Potential.txt         # Output file with potential new content links
├── logs/                 # Directory for log files
│   ├── log_2024-01-15.txt
│   ├── log_2024-01-16.txt
│   └── ...
└── README.md             # This file
```

## How It Works

1. **Reads CSV**: Processes the `sorted_links.csv` file and extracts links from the "Redirected" column
2. **Skip Processing**: Ignores "Valid" and "Error" columns as specified
3. **Redirect Check**: For each redirected link:
   - Makes HTTP request to the URL
   - Follows redirects and checks final destination
   - If final URL is `https://nkp.gov.np/home` → No new content
   - If final URL is different → Potential new content
4. **Save Results**: Appends links with potential new content to `Potential.txt`
5. **Email Notification**: Sends email with count and list of new links found
6. **Logging**: Records all activities in date-indexed log files

## Email Configuration

The scraper supports various email providers. Here are common configurations:

### Gmail
```json
{
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "sender_email": "your_email@gmail.com",
    "sender_password": "your_app_password"
}
```

### Outlook/Hotmail
```json
{
    "smtp_server": "smtp-mail.outlook.com",
    "smtp_port": 587,
    "sender_email": "your_email@outlook.com",
    "sender_password": "your_password"
}
```

### Yahoo
```json
{
    "smtp_server": "smtp.mail.yahoo.com",
    "smtp_port": 587,
    "sender_email": "your_email@yahoo.com",
    "sender_password": "your_app_password"
}
```

## Logs

Each run creates a detailed log file in the `logs/` directory:
- **Filename**: `log_YYYY-MM-DD.txt`
- **Content**: Timestamps, processing details, errors, and statistics
- **Location**: `logs/log_2024-01-15.txt` (example)

## Output Files

### Potential.txt
Contains links that potentially have new content:
```
https://nkp.gov.np/full_detail/123
https://nkp.gov.np/full_detail/456
https://nkp.gov.np/full_detail/789
```

## Troubleshooting

### Common Issues

1. **"No module named 'requests'"**
   ```bash
   pip install -r requirements.txt
   ```

2. **Email authentication failed**
   - For Gmail: Use App Password, not regular password
   - Enable 2-factor authentication first
   - Check SMTP server and port settings

3. **Permission denied errors**
   - Ensure you have write permissions in the directory
   - Run with appropriate permissions

4. **CSV file not found**
   - Ensure `sorted_links.csv` is in the same directory
   - Check file name spelling and case

### Testing Checklist

Before running in production:
- [ ] Run `python webscraper.py --test` successfully
- [ ] Verify email configuration with test run
- [ ] Check that `Potential.txt` is created
- [ ] Verify log files are created in `logs/` directory
- [ ] Confirm CSV file is being read correctly

### Performance Notes

- **Request Delay**: 1 second between requests to avoid overwhelming the server
- **Retry Logic**: Up to 3 attempts for failed requests
- **Timeout**: 10 seconds per request
- **Test Mode**: Processes only 10 links for quick testing

## Scheduling for Production

### Option 1: Using the built-in scheduler
```bash
python webscraper.py --schedule
```

### Option 2: Using system cron (Linux/Mac)
Add to crontab to run every 48 hours:
```bash
crontab -e
# Add this line (runs every 2 days at 2 AM):
0 2 */2 * * /usr/bin/python3 /path/to/webscraper.py --run
```

### Option 3: Using Windows Task Scheduler
1. Open Task Scheduler
2. Create Basic Task
3. Set trigger to repeat every 2 days
4. Set action to run Python script

## Support

For issues or questions:
1. Check the log files in `logs/` directory
2. Run in test mode first to isolate problems
3. Verify all configuration settings
4. Ensure all dependencies are installed

## License

This project is for educational and monitoring purposes. Please respect the target website's robots.txt and terms of service. 