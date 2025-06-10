#!/usr/bin/env python3
"""
Final Dataset Merger
Combines all checkpoint files into a comprehensive final dataset
"""

import pandas as pd
import glob
import json
from datetime import datetime
import os

def merge_comprehensive_dataset():
    """Merge all checkpoint files into final comprehensive dataset"""
    print("🔄 MERGING COMPREHENSIVE DATASET")
    print("=" * 50)
    
    # Get all checkpoint files
    checkpoint_files = sorted(glob.glob("checkpoint_*.csv"), key=lambda x: int(x.split('_')[1].split('.')[0]))
    
    if not checkpoint_files:
        print("❌ No checkpoint files found!")
        return
    
    print(f"📁 Found {len(checkpoint_files)} checkpoint files to merge")
    
    # Initialize list to store all dataframes
    all_dataframes = []
    total_decisions = 0
    file_count = 0
    
    print("\n🔍 Processing checkpoint files...")
    
    for i, file in enumerate(checkpoint_files, 1):
        try:
            # Read each checkpoint file
            df = pd.read_csv(file, encoding='utf-8-sig')
            
            if not df.empty:
                all_dataframes.append(df)
                total_decisions += len(df)
                file_count += 1
                
            # Progress indicator
            if i % 100 == 0 or i == len(checkpoint_files):
                print(f"  ✓ Processed {i}/{len(checkpoint_files)} files - {total_decisions:,} decisions so far")
                
        except Exception as e:
            print(f"  ⚠️ Error reading {file}: {e}")
            continue
    
    if not all_dataframes:
        print("❌ No valid data found in checkpoint files!")
        return
    
    print(f"\n📊 Merging {file_count} valid files with {total_decisions:,} total decisions...")
    
    # Combine all dataframes
    final_df = pd.concat(all_dataframes, ignore_index=True)
    
    # Remove duplicates (in case of any overlaps)
    initial_count = len(final_df)
    final_df = final_df.drop_duplicates()
    final_count = len(final_df)
    
    if initial_count != final_count:
        print(f"🧹 Removed {initial_count - final_count:,} duplicate records")
    
    # Sort by court type, court name, and date for better organization
    final_df = final_df.sort_values(['court_type_name', 'court_name', 'registration_date'], 
                                   na_position='last').reset_index(drop=True)
    
    # Generate statistics
    stats = generate_comprehensive_stats(final_df)
    
    # Save final dataset
    final_filename = f"nepal_supreme_court_comprehensive_dataset_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    final_df.to_csv(final_filename, index=False, encoding='utf-8-sig')
    
    # Save statistics
    stats_filename = f"dataset_statistics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(stats_filename, 'w', encoding='utf-8') as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    
    print(f"\n🎉 MERGE COMPLETE!")
    print(f"📁 Final dataset: {final_filename}")
    print(f"📊 Statistics file: {stats_filename}")
    print(f"💾 Dataset size: {os.path.getsize(final_filename) / (1024*1024):.1f} MB")
    print(f"📈 Total decisions: {final_count:,}")
    
    return final_df, stats

def generate_comprehensive_stats(df):
    """Generate comprehensive statistics for the dataset"""
    print("\n📈 Generating comprehensive statistics...")
    
    stats = {
        'generation_info': {
            'generated_at': datetime.now().isoformat(),
            'total_records': len(df),
            'total_checkpoint_files': len(glob.glob("checkpoint_*.csv"))
        },
        'court_statistics': {},
        'temporal_analysis': {},
        'case_type_analysis': {},
        'download_statistics': {}
    }
    
    # Court statistics
    court_type_counts = df['court_type_name'].value_counts().to_dict()
    court_name_counts = df['court_name'].value_counts().to_dict()
    
    stats['court_statistics'] = {
        'by_court_type': court_type_counts,
        'by_court_name': dict(list(court_name_counts.items())[:20]),  # Top 20 courts
        'total_unique_courts': df['court_name'].nunique()
    }
    
    # Temporal analysis
    if 'registration_date' in df.columns:
        # Extract years from dates
        df_temp = df.copy()
        df_temp['year'] = df_temp['registration_date'].str[:4]
        year_counts = df_temp['year'].value_counts().sort_index().to_dict()
        
        stats['temporal_analysis'] = {
            'by_year': year_counts,
            'date_range': {
                'earliest': df['registration_date'].min(),
                'latest': df['registration_date'].max()
            }
        }
    
    # Case type analysis
    if 'case_type' in df.columns:
        case_type_counts = df['case_type'].value_counts().to_dict()
        stats['case_type_analysis'] = {
            'by_case_type': case_type_counts,
            'total_case_types': df['case_type'].nunique()
        }
    
    # Download statistics
    if 'download_url' in df.columns:
        has_download = (df['download_url'].notna() & (df['download_url'] != '')).sum()
        no_download = len(df) - has_download
        
        stats['download_statistics'] = {
            'with_download_links': int(has_download),
            'without_download_links': int(no_download),
            'download_availability_percentage': round((has_download / len(df)) * 100, 2)
        }
    
    return stats

def print_summary_report(stats):
    """Print a beautiful summary report"""
    print("\n" + "="*60)
    print("🏛️  NEPAL SUPREME COURT DATASET - FINAL SUMMARY")
    print("="*60)
    
    gen_info = stats['generation_info']
    print(f"📅 Generated: {gen_info['generated_at']}")
    print(f"📊 Total Records: {gen_info['total_records']:,}")
    print(f"💾 Checkpoint Files Processed: {gen_info['total_checkpoint_files']:,}")
    
    # Court statistics
    court_stats = stats['court_statistics']
    print(f"\n🏛️  COURT COVERAGE:")
    print(f"   Total Unique Courts: {court_stats['total_unique_courts']}")
    
    if 'by_court_type' in court_stats:
        print(f"   By Court Type:")
        for court_type, count in court_stats['by_court_type'].items():
            print(f"     • {court_type}: {count:,} decisions")
    
    # Temporal analysis
    if 'temporal_analysis' in stats:
        temporal = stats['temporal_analysis']
        if 'date_range' in temporal:
            print(f"\n📅 TEMPORAL COVERAGE:")
            print(f"   Date Range: {temporal['date_range']['earliest']} to {temporal['date_range']['latest']}")
        
        if 'by_year' in temporal:
            print(f"   Decisions by Year (Top 5):")
            year_items = sorted(temporal['by_year'].items(), key=lambda x: int(x[1]), reverse=True)[:5]
            for year, count in year_items:
                print(f"     • {year}: {count:,} decisions")
    
    # Download statistics
    if 'download_statistics' in stats:
        dl_stats = stats['download_statistics']
        print(f"\n📥 DOWNLOAD AVAILABILITY:")
        print(f"   With Download Links: {dl_stats['with_download_links']:,} ({dl_stats['download_availability_percentage']}%)")
        print(f"   Upload Pending: {dl_stats['without_download_links']:,}")
    
    print("\n" + "="*60)
    print("✅ COMPREHENSIVE SCRAPING COMPLETED SUCCESSFULLY!")
    print("="*60)

if __name__ == "__main__":
    # Execute the merge
    final_df, stats = merge_comprehensive_dataset()
    
    if final_df is not None:
        # Print summary report
        print_summary_report(stats)
        
        print(f"\n🎯 Ready for analysis! Use the generated CSV file for further processing.")
        print(f"📁 All files are saved in the current directory.") 