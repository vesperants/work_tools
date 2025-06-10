#!/usr/bin/env python3
"""
Test Resume Mechanism
Quick test to show how many combinations have been completed and how many remain
"""

import pandas as pd
import glob
from multithreaded_comprehensive_scraper import MultithreadedCourtScraper

def test_resume_analysis():
    """Test the resume mechanism"""
    print("🔍 TESTING RESUME MECHANISM")
    print("=" * 50)
    
    scraper = MultithreadedCourtScraper()
    
    # Get completed combinations
    completed_combinations = scraper.get_completed_tasks()
    
    # Get all courts and dates to calculate total combinations
    court_types = ['S', 'A', 'D', 'T']
    all_courts = []
    for court_type in court_types:
        courts = scraper.get_court_list(court_type)
        all_courts.extend(courts)
    
    dates = scraper.generate_date_range(2069, 2081)
    
    total_combinations = len(all_courts) * len(dates)
    remaining_combinations = total_combinations - len(completed_combinations)
    
    print(f"📊 RESUME ANALYSIS:")
    print(f"  Total possible combinations: {total_combinations:,}")
    print(f"  Completed combinations: {len(completed_combinations):,}")
    print(f"  Remaining combinations: {remaining_combinations:,}")
    print(f"  Progress: {(len(completed_combinations)/total_combinations)*100:.2f}%")
    
    # Check some recent completion examples
    print(f"\n📋 SAMPLE COMPLETED COMBINATIONS:")
    sample_completed = list(completed_combinations)[-10:]
    for court_id, date in sample_completed:
        print(f"  Court {court_id} on {date}")
    
    if remaining_combinations > 0:
        print(f"\n✅ Resume will skip {len(completed_combinations):,} completed combinations")
        print(f"⏰ Estimated remaining time: {(remaining_combinations * 0.2 / 12 / 3600):.1f} hours")
    else:
        print(f"\n🎉 ALL COMBINATIONS COMPLETED!")

if __name__ == "__main__":
    test_resume_analysis() 