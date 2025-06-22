import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
import json
import os
from datetime import datetime
import logging
from urllib.parse import urljoin, urlparse, parse_qs
import urllib.request
from pathlib import Path

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class NepalGazetteDownloader:
    def __init__(self, base_url="http://rajpatra.dop.gov.np", delay=2, download_dir="nepal_gazettes"):
        self.base_url = base_url
        self.delay = delay
        self.download_dir = Path(download_dir)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        # Create main download directory
        self.download_dir.mkdir(exist_ok=True)
        
        # Statistics
        self.stats = {
            'collections_processed': 0,
            'gazettes_found': 0,
            'gazettes_downloaded': 0,
            'download_errors': 0,
            'start_time': datetime.now()
        }
        
        self.gazette_types = {
            0: "अरि",     # Special gazettes
            1: "संख्या"    # Numbered gazettes
        }
    
    def create_safe_filename(self, text, max_length=150):
        """Create a safe filename from Nepali text"""
        # Remove invalid characters for filenames
        safe_chars = re.sub(r'[<>:"/\\|?*]', '_', text)
        # Limit length
        if len(safe_chars.encode('utf-8')) > max_length:
            safe_chars = safe_chars[:max_length] + "..."
        return safe_chars.strip()
    
    def get_available_gazette_collections(self):
        """Extract all gazette collection URLs from the main page"""
        logger.info("Fetching main page to extract gazette collections...")
        
        response = self.session.get(self.base_url)
        if response.status_code != 200:
            logger.error(f"Failed to fetch main page: {response.status_code}")
            return []
        
        soup = BeautifulSoup(response.content, 'html.parser')
        gazette_collections = []
        
        # Find the books area div
        books_area = soup.find('div', class_='books_area')
        if not books_area:
            logger.error("Could not find books area on main page")
            return []
        
        # Extract all gazette links
        gazette_links = books_area.find_all('div', class_='col-md-2')
        
        for book_div in gazette_links:
            link = book_div.find('a')
            if link and link.get('href'):
                href = link.get('href')
                
                # Extract type and year from URL
                match = re.search(r'/welcome/list_by_type/(\d+)/(\d+)', href)
                if match:
                    gazette_type = int(match.group(1))
                    year = int(match.group(2))
                    
                    # Get the title from the span
                    title_span = book_div.find('span', class_='book_title')
                    title = title_span.get_text(strip=True) if title_span else f"{self.gazette_types.get(gazette_type, 'Unknown')} {year}"
                    
                    collection_info = {
                        'type': gazette_type,
                        'type_name': self.gazette_types.get(gazette_type, 'Unknown'),
                        'year': year,
                        'title': title,
                        'url': urljoin(self.base_url, href),
                        'folder_name': f"{self.gazette_types.get(gazette_type, 'Unknown')}_{year}"
                    }
                    
                    gazette_collections.append(collection_info)
        
        logger.info(f"Found {len(gazette_collections)} gazette collections")
        return gazette_collections
    
    def get_individual_gazettes_from_collection(self, collection_info):
        """Extract individual gazette links from a collection page"""
        url = collection_info['url']
        logger.info(f"Processing collection: {collection_info['type_name']} {collection_info['year']}")
        
        response = self.session.get(url)
        if response.status_code != 200:
            logger.warning(f"Failed to fetch collection page: {response.status_code}")
            return []
        
        soup = BeautifulSoup(response.content, 'html.parser')
        individual_gazettes = []
        
        # Check if page has gazette entries
        if "Table of Contents" not in response.text:
            logger.info(f"No gazettes found in {collection_info['type_name']} {collection_info['year']}")
            return []
        
        # Find gazette links in the list-content divs
        content_divs = soup.find_all('div', class_='list-content')
        
        for i, content_div in enumerate(content_divs, 1):
            link = content_div.find('a')
            if link and link.get('href'):
                href = link.get('href')
                title = link.get_text(strip=True)
                
                # Extract ref parameter from URL
                ref_match = re.search(r'ref=(\d+)', href)
                if ref_match:
                    ref_id = ref_match.group(1)
                    
                    gazette_info = {
                        'collection': collection_info,
                        'entry_number': i,
                        'title': title,
                        'ref_id': ref_id,
                        'gazette_url': urljoin(self.base_url, href),
                        'download_url': f"{self.base_url}/welcome/download?ref={ref_id}",
                        'safe_filename': self.create_safe_filename(f"{i:02d}_{title}")
                    }
                    
                    individual_gazettes.append(gazette_info)
        
        logger.info(f"Found {len(individual_gazettes)} individual gazettes in collection")
        self.stats['gazettes_found'] += len(individual_gazettes)
        return individual_gazettes
    
    def download_gazette(self, gazette_info):
        """Download an individual gazette file"""
        collection = gazette_info['collection']
        
        # Create folder for this collection
        collection_folder = self.download_dir / collection['folder_name']
        collection_folder.mkdir(exist_ok=True)
        
        # Determine file extension (try to get from headers)
        download_url = gazette_info['download_url']
        safe_filename = gazette_info['safe_filename']
        
        try:
            # First, make a HEAD request to check content type
            head_response = self.session.head(download_url, allow_redirects=True)
            
            # Determine file extension from content type
            content_type = head_response.headers.get('content-type', '').lower()
            if 'pdf' in content_type:
                file_extension = '.pdf'
            elif 'zip' in content_type:
                file_extension = '.zip'
            elif 'image' in content_type:
                file_extension = '.jpg'
            else:
                file_extension = '.pdf'  # Default assumption
            
            filename = safe_filename + file_extension
            filepath = collection_folder / filename
            
            # Skip if file already exists
            if filepath.exists():
                logger.info(f"File already exists: {filename}")
                return True
            
            # Download the file
            logger.info(f"Downloading: {filename}")
            response = self.session.get(download_url, stream=True)
            response.raise_for_status()
            
            # Save the file
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            file_size = filepath.stat().st_size
            logger.info(f"Downloaded: {filename} ({file_size:,} bytes)")
            
            self.stats['gazettes_downloaded'] += 1
            return True
            
        except Exception as e:
            logger.error(f"Failed to download {gazette_info['title']}: {e}")
            self.stats['download_errors'] += 1
            return False
    
    def download_all_gazettes(self, max_collections=None):
        """Main method to download all gazettes"""
        logger.info("Starting comprehensive Nepal Rajpatra download...")
        
        # Get all available gazette collections
        collections = self.get_available_gazette_collections()
        
        if not collections:
            logger.error("No gazette collections found")
            return
        
        # Limit collections if specified (for testing)
        if max_collections:
            collections = collections[:max_collections]
            logger.info(f"Limited to first {max_collections} collections for testing")
        
        # Process each collection
        for i, collection_info in enumerate(collections, 1):
            logger.info(f"\n=== Processing collection {i}/{len(collections)} ===")
            logger.info(f"Collection: {collection_info['type_name']} {collection_info['year']}")
            
            try:
                # Get individual gazettes from this collection
                individual_gazettes = self.get_individual_gazettes_from_collection(collection_info)
                
                if not individual_gazettes:
                    logger.info("No gazettes found in this collection, skipping...")
                    continue
                
                # Download each gazette
                for j, gazette_info in enumerate(individual_gazettes, 1):
                    logger.info(f"Processing gazette {j}/{len(individual_gazettes)}: {gazette_info['title'][:50]}...")
                    
                    success = self.download_gazette(gazette_info)
                    if not success:
                        logger.warning(f"Failed to download gazette {j}")
                    
                    # Be respectful to the server
                    time.sleep(self.delay)
                
                self.stats['collections_processed'] += 1
                
            except Exception as e:
                logger.error(f"Error processing collection {collection_info['folder_name']}: {e}")
                continue
        
        # Print final statistics
        self.print_final_stats()
    
    def print_final_stats(self):
        """Print final download statistics"""
        end_time = datetime.now()
        duration = end_time - self.stats['start_time']
        
        print("\n" + "="*70)
        print("NEPAL RAJPATRA DOWNLOAD COMPLETE")
        print("="*70)
        print(f"Collections processed: {self.stats['collections_processed']}")
        print(f"Total gazettes found: {self.stats['gazettes_found']}")
        print(f"Successfully downloaded: {self.stats['gazettes_downloaded']}")
        print(f"Download errors: {self.stats['download_errors']}")
        print(f"Success rate: {(self.stats['gazettes_downloaded'] / max(self.stats['gazettes_found'], 1)) * 100:.1f}%")
        print(f"Total time: {duration}")
        print(f"Download directory: {self.download_dir.absolute()}")
        print("="*70)
        
        # Show folder structure
        if self.download_dir.exists():
            print("\nDownload folder structure:")
            for folder in sorted(self.download_dir.iterdir()):
                if folder.is_dir():
                    file_count = len(list(folder.glob('*')))
                    print(f"  📁 {folder.name}/ ({file_count} files)")
    
    def save_metadata(self):
        """Save download metadata to JSON file"""
        metadata = {
            'download_info': {
                'completed_at': datetime.now().isoformat(),
                'statistics': self.stats
            }
        }
        
        metadata_file = self.download_dir / 'download_metadata.json'
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Metadata saved to {metadata_file}")

def main():
    """Main execution function"""
    print("Nepal Rajpatra Complete Downloader")
    print("=" * 50)
    print("This will download ALL gazettes from the Nepal Department of Printing website")
    print("Files will be organized by collection type and year")
    print("-" * 50)
    
    # Configuration
    DELAY_BETWEEN_DOWNLOADS = 2  # seconds (be respectful!)
    DOWNLOAD_DIRECTORY = "nepal_gazettes_complete"
    
    # For testing: limit number of collections (set to None for all)
    MAX_COLLECTIONS = None  # Set to 3 for testing, None for all collections
    
    print(f"Download directory: {DOWNLOAD_DIRECTORY}")
    print(f"Delay between downloads: {DELAY_BETWEEN_DOWNLOADS} seconds")
    if MAX_COLLECTIONS:
        print(f"Testing mode: Limited to {MAX_COLLECTIONS} collections")
    
    proceed = input("\nProceed with download? (y/N): ").lower().strip()
    if proceed != 'y':
        print("Download cancelled.")
        return
    
    # Initialize downloader
    downloader = NepalGazetteDownloader(
        delay=DELAY_BETWEEN_DOWNLOADS,
        download_dir=DOWNLOAD_DIRECTORY
    )
    
    try:
        # Start download process
        downloader.download_all_gazettes(max_collections=MAX_COLLECTIONS)
        
        # Save metadata
        downloader.save_metadata()
        
    except KeyboardInterrupt:
        logger.info("\nDownload interrupted by user")
        downloader.print_final_stats()
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        downloader.print_final_stats()

if __name__ == "__main__":
    main()