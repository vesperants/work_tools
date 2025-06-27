#!/usr/bin/env python3
"""
Quick Start Script for Auto-WebScraper
This script helps you get started quickly with basic setup and testing
"""

import os
import sys
import json
import subprocess


def check_requirements():
    """Check if required packages are installed"""
    try:
        import requests
        import schedule
        print("✓ All required packages are installed")
        return True
    except ImportError as e:
        print(f"✗ Missing package: {e}")
        print("Installing required packages...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
            print("✓ Packages installed successfully")
            return True
        except subprocess.CalledProcessError:
            print("✗ Failed to install packages")
            return False


def check_csv_file():
    """Check if CSV file exists"""
    if os.path.exists("sorted_links.csv"):
        print("✓ sorted_links.csv found")
        return True
    else:
        print("✗ sorted_links.csv not found in current directory")
        return False


def setup_config():
    """Setup email configuration interactively"""
    config_file = "config.json"
    
    if os.path.exists(config_file):
        print("✓ config.json already exists")
        return True
    
    print("\n" + "="*50)
    print("EMAIL CONFIGURATION SETUP")
    print("="*50)
    print("For Gmail users:")
    print("1. Enable 2-factor authentication")
    print("2. Generate an App Password")
    print("3. Use the App Password below (not your regular password)")
    print()
    
    email_config = {}
    
    # Get email provider
    print("Select email provider:")
    print("1. Gmail")
    print("2. Outlook/Hotmail")
    print("3. Yahoo")
    print("4. Other")
    
    choice = input("Enter choice (1-4): ").strip()
    
    if choice == "1":
        email_config["smtp_server"] = "smtp.gmail.com"
        email_config["smtp_port"] = 587
    elif choice == "2":
        email_config["smtp_server"] = "smtp-mail.outlook.com"
        email_config["smtp_port"] = 587
    elif choice == "3":
        email_config["smtp_server"] = "smtp.mail.yahoo.com"
        email_config["smtp_port"] = 587
    else:
        email_config["smtp_server"] = input("SMTP Server: ").strip()
        email_config["smtp_port"] = int(input("SMTP Port (usually 587): ").strip() or "587")
    
    email_config["sender_email"] = input("Your email address: ").strip()
    email_config["sender_password"] = input("Your password (App Password for Gmail): ").strip()
    email_config["recipient_email"] = input("Recipient email address: ").strip()
    
    # Save configuration
    config = {"email": email_config}
    
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=4)
    
    print(f"✓ Configuration saved to {config_file}")
    return True


def run_test():
    """Run the scraper in test mode"""
    print("\n" + "="*50)
    print("RUNNING TEST")
    print("="*50)
    print("Testing with first 10 links...")
    
    try:
        result = subprocess.run([sys.executable, "webscraper.py", "--test"], 
                               capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✓ Test completed successfully!")
            print("\nTest output:")
            print(result.stdout)
        else:
            print("✗ Test failed!")
            print("Error output:")
            print(result.stderr)
            return False
            
    except Exception as e:
        print(f"✗ Error running test: {e}")
        return False
    
    return True


def main():
    """Main quickstart function"""
    print("="*60)
    print("AUTO-WEBSCRAPER QUICK START")
    print("="*60)
    
    # Step 1: Check requirements
    print("\n1. Checking requirements...")
    if not check_requirements():
        print("Please install requirements manually: pip install -r requirements.txt")
        return
    
    # Step 2: Check CSV file
    print("\n2. Checking CSV file...")
    if not check_csv_file():
        print("Please ensure 'sorted_links.csv' is in the current directory")
        return
    
    # Step 3: Setup configuration
    print("\n3. Setting up configuration...")
    setup_email = input("Do you want to set up email notifications now? (y/n): ").lower().strip()
    
    if setup_email == 'y':
        if not setup_config():
            return
    else:
        print("Skipping email setup. You can run 'python webscraper.py --setup' later.")
    
    # Step 4: Run test
    print("\n4. Running test...")
    run_test_now = input("Do you want to run a test now? (y/n): ").lower().strip()
    
    if run_test_now == 'y':
        if run_test():
            print("\n✓ Quick start completed successfully!")
            print("\nNext steps:")
            print("- Check the 'logs/' directory for detailed logs")
            print("- Check 'Potential.txt' for any links found")
            print("- Run 'python webscraper.py --run' for a full manual run")
            print("- Run 'python webscraper.py --schedule' to start automatic scheduling")
        else:
            print("\n✗ Test failed. Please check the error messages above.")
    else:
        print("\nQuick start setup completed!")
        print("Run 'python webscraper.py --test' when ready to test.")


if __name__ == "__main__":
    main() 