#!/usr/bin/env python3
"""
Encoding Test and Fix Script
Tests Nepali text encoding and provides solutions for proper display
"""

import pandas as pd
import json
import sys

def test_nepali_encoding():
    """Test Nepali text encoding and display"""
    print("🔤 NEPALI TEXT ENCODING TEST")
    print("=" * 50)
    
    # Sample Nepali text
    nepali_texts = [
        "सर्वोच्च अदालत",
        "उच्च अदालत", 
        "जिल्ला अदालत",
        "विशेष अदालत",
        "मुद्दा दर्ता मिति"
    ]
    
    print("Testing Nepali text display:")
    for i, text in enumerate(nepali_texts, 1):
        print(f"{i}. {text}")
    
    print(f"\nPython version: {sys.version}")
    print(f"Default encoding: {sys.getdefaultencoding()}")
    print(f"File system encoding: {sys.getfilesystemencoding()}")
    
def create_sample_data_with_proper_encoding():
    """Create sample data with proper UTF-8 encoding"""
    print("\n📝 Creating sample data with proper encoding...")
    
    sample_data = [
        {
            'court_name': 'सर्वोच्च अदालत',
            'court_type': 'S',
            'case_name': 'नेपाल सरकार बनाम राम बहादुर',
            'plaintiff': 'नेपाल सरकार',
            'defendant': 'राम बहादुर श्रेष्ठ',
            'case_type': 'फौजदारी मुद्दा'
        },
        {
            'court_name': 'उच्च अदालत पाटन',
            'court_type': 'A', 
            'case_name': 'श्याम प्रसाद बनाम सीता देवी',
            'plaintiff': 'श्याम प्रसाद',
            'defendant': 'सीता देवी',
            'case_type': 'दीवानी मुद्दा'
        }
    ]
    
    # Save as CSV with UTF-8-sig encoding (includes BOM for proper Excel display)
    df = pd.DataFrame(sample_data)
    df.to_csv('sample_nepali_data.csv', index=False, encoding='utf-8-sig')
    print("✅ Sample data saved as 'sample_nepali_data.csv' (UTF-8 with BOM)")
    
    # Save as JSON with proper UTF-8 encoding
    with open('sample_nepali_data.json', 'w', encoding='utf-8') as f:
        json.dump(sample_data, f, indent=2, ensure_ascii=False)
    print("✅ Sample data saved as 'sample_nepali_data.json' (UTF-8)")
    
    return df

def provide_viewing_instructions():
    """Provide instructions for properly viewing Nepali text"""
    print("\n📖 INSTRUCTIONS FOR VIEWING NEPALI TEXT")
    print("=" * 50)
    
    print("🖥️  TERMINAL/COMMAND LINE:")
    print("   • Make sure your terminal supports UTF-8")
    print("   • On macOS: Terminal app should work by default")
    print("   • On Windows: Use Windows Terminal or set UTF-8 in Command Prompt")
    print("   • Test: cat sample_nepali_data.csv")
    
    print("\n📊 EXCEL/SPREADSHEET:")
    print("   • Excel: Use 'Data > Get Data > From File > From Text/CSV'")
    print("   • Select 'UTF-8' encoding in the import dialog")
    print("   • OR: Files saved with 'utf-8-sig' should open correctly")
    
    print("\n🔍 TEXT EDITORS:")
    print("   • VS Code: Should display correctly by default")
    print("   • Notepad++: Set encoding to 'UTF-8' or 'UTF-8-BOM'")
    print("   • Any modern editor should support UTF-8")
    
    print("\n🐍 PYTHON READING:")
    print("   • pd.read_csv('file.csv', encoding='utf-8-sig')")
    print("   • with open('file.json', encoding='utf-8') as f:")
    
    print("\n🌐 WEB BROWSERS:")
    print("   • HTML files: Add <meta charset='UTF-8'> in head")
    print("   • Should display correctly in any modern browser")

def test_csv_reading():
    """Test reading CSV with different encodings"""
    print("\n🧪 TESTING CSV READING WITH DIFFERENT ENCODINGS")
    print("=" * 55)
    
    if not pd.io.common.file_exists('sample_nepali_data.csv'):
        print("❌ Sample file not found. Run create_sample_data_with_proper_encoding() first.")
        return
    
    encodings_to_test = ['utf-8', 'utf-8-sig', 'latin1', 'cp1252']
    
    for encoding in encodings_to_test:
        try:
            df = pd.read_csv('sample_nepali_data.csv', encoding=encoding)
            print(f"✅ {encoding:12} -> {df.iloc[0]['court_name']}")
        except Exception as e:
            print(f"❌ {encoding:12} -> Error: {str(e)[:50]}...")

def fix_existing_csv(input_file, output_file=None):
    """Fix encoding issues in existing CSV file"""
    if output_file is None:
        output_file = input_file.replace('.csv', '_fixed.csv')
    
    print(f"\n🔧 FIXING ENCODING IN {input_file}")
    print("=" * 50)
    
    try:
        # Try reading with different encodings
        for encoding in ['utf-8-sig', 'utf-8', 'latin1', 'cp1252']:
            try:
                df = pd.read_csv(input_file, encoding=encoding)
                print(f"✅ Successfully read with {encoding}")
                
                # Save with proper UTF-8 encoding
                df.to_csv(output_file, index=False, encoding='utf-8-sig')
                print(f"✅ Fixed file saved as: {output_file}")
                
                # Show sample of fixed data
                if len(df) > 0 and 'court_name' in df.columns:
                    print(f"📄 Sample: {df.iloc[0]['court_name']}")
                
                return True
                
            except Exception as e:
                print(f"❌ Failed with {encoding}: {str(e)[:50]}...")
                continue
        
        print("❌ Could not read the file with any encoding")
        return False
        
    except Exception as e:
        print(f"❌ Error fixing file: {e}")
        return False

def main():
    """Main function to run all tests and fixes"""
    print("🚀 NEPALI TEXT ENCODING DIAGNOSTIC AND FIX TOOL")
    print("=" * 60)
    
    # Test basic Nepali text display
    test_nepali_encoding()
    
    # Create sample data with proper encoding
    create_sample_data_with_proper_encoding()
    
    # Test reading with different encodings
    test_csv_reading()
    
    # Provide viewing instructions
    provide_viewing_instructions()
    
    # Check if there are existing files to fix
    import glob
    csv_files = glob.glob("*.csv")
    if csv_files:
        print(f"\n🔍 Found {len(csv_files)} CSV files in current directory:")
        for file in csv_files[:5]:  # Show first 5
            print(f"   📄 {file}")
        
        print(f"\n💡 To fix encoding in any of these files, run:")
        print(f"   fix_existing_csv('filename.csv')")

if __name__ == "__main__":
    main() 