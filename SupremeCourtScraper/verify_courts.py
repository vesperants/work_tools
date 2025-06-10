#!/usr/bin/env python3
"""
Verification script to confirm all three courts are configured correctly.
"""

from redirect_courts_scraper import MegaRedirectCourtsScraper

def verify_court_setup():
    """Verify that all three courts are properly configured."""
    print("🔍 VERIFYING COURT SETUP")
    print("=" * 50)
    
    # Initialize scraper (don't start scraping)
    scraper = MegaRedirectCourtsScraper(max_workers=1, delay=1.0)
    
    print(f"✅ Scraper initialized with {len(scraper.court_configs)} courts")
    print()
    
    # Check court configurations
    print("🏛️  COURT CONFIGURATIONS:")
    for court_key, court_config in scraper.court_configs.items():
        print(f"   Court Key: {court_key}")
        print(f"   Name: {court_config['name']}")
        print(f"   Type Code: {court_config['type_code']}")
        print(f"   URL: {court_config['decisions_url']}")
        print()
    
    # Check task generation
    print("📋 TASK GENERATION VERIFICATION:")
    print(f"   Total tasks: {len(scraper.task_list)}")
    
    # Count tasks by court
    court_counts = {}
    for task in scraper.task_list:
        court_type = task['court_config']['type_code']
        court_name = task['court_config']['name']
        if court_type not in court_counts:
            court_counts[court_type] = {'name': court_name, 'count': 0}
        court_counts[court_type]['count'] += 1
    
    for court_type, info in court_counts.items():
        print(f"   {info['name']} ({court_type}): {info['count']} tasks")
    
    # Show sample tasks for each court
    print("\n📝 SAMPLE TASKS (first 3 dates for each court):")
    for court_key, court_config in scraper.court_configs.items():
        court_tasks = [t for t in scraper.task_list if t['court_key'] == court_key][:3]
        print(f"\n   {court_config['name']} ({court_config['type_code']}):")
        for task in court_tasks:
            print(f"      Task: {task['task_id']} | Date: {task['date']}")
    
    # Verify equal distribution
    expected_tasks_per_court = len(scraper.task_list) // 3
    print(f"\n📊 DISTRIBUTION CHECK:")
    print(f"   Expected tasks per court: ~{expected_tasks_per_court}")
    
    all_equal = True
    for court_type, info in court_counts.items():
        if abs(info['count'] - expected_tasks_per_court) > 100:  # Allow some variance
            print(f"   ⚠️  {info['name']}: {info['count']} (deviation > 100)")
            all_equal = False
        else:
            print(f"   ✅ {info['name']}: {info['count']} (OK)")
    
    if all_equal:
        print("\n🎉 VERIFICATION PASSED!")
        print("All three courts are properly configured with equal task distribution.")
    else:
        print("\n⚠️  VERIFICATION WARNING!")
        print("Task distribution is uneven between courts.")
    
    return all_equal

if __name__ == "__main__":
    verify_court_setup() 