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
import threading
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed
import random

# Set up logging with thread-safe configuration
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - [Thread-%(thread)d] - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('download_log.txt'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ThreadSafeCounter:
    """Thread-safe counter for statistics"""
    def __init__(self):
        self._value = 0
        self._lock = threading.Lock()
    
    def increment(self):
        with self._lock:
            self._value += 1
            return self._value
    
    def get(self):
        with self._lock:
            return self._value

class NepalGazetteDownloaderThreaded:
    def __init__(self, base_url="http://rajpatra.dop.gov.np", 
                 download_dir="nepal_gazettes_threaded", 
                 num_threads=4, delay_range=(1, 3)):
        self.base_url = base_url
        self.download_dir = Path(download_dir)
        self.num_threads = num_threads
        self.delay_range = delay_range  # Random delay between requests
        
        # Create main download directory
        self.download_dir.mkdir(exist_ok=True)
        
        # Thread-safe statistics
        self.stats = {
            'collections_processed': ThreadSafeCounter(),
            'gazettes_found': ThreadSafeCounter(),
            'gazettes_downloaded': ThreadSafeCounter(),
            'download_errors': ThreadSafeCounter(),
            'start_time': datetime.now()
        }
        
        self.gazette_types = {
            0: "अरि",     # Special gazettes
            1: "संख्या"    # Numbered gazettes
        }
        
        # Thread-safe progress tracking
        self.progress_lock = threading.Lock()
        self.processed_collections = []
        
    def create_session(self):
        """Create a new session for each thread"""
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        return session
    
    def random_delay(self):
        """Random delay to be more respectful to the server"""
        delay = random.uniform(self.delay_range[0], self.delay_range[1])
        time.sleep(delay)
    
    def create_safe_filename(self, text, max_length=150):
        """Create a safe filename from Nepali text"""
        safe_chars = re.sub(r'[<>:"/\\|?*]', '_', text)
        if len(safe_chars.encode('utf-8')) > max_length:
            safe_chars = safe_chars[:max_length] + "..."
        return safe_chars.strip()
    
    def get_available_gazette_collections(self):
        """Extract all gazette collection URLs from the main page"""
        logger.info("Fetching main page to extract gazette collections...")
        
        session = self.create_session()
        response = session.get(self.base_url)
        
        if response.status_code != 200:
            logger.error(f"Failed to fetch main page: {response.status_code}")
            return []
        
        soup = BeautifulSoup(response.content, 'html.parser')
        gazette_collections = []
        
        books_area = soup.find('div', class_='books_area')
        if not books_area:
            logger.error("Could not find books area on main page")
            return []
        
        gazette_links = books_area.find_all('div', class_='col-md-2')
        
        for book_div in gazette_links:
            link = book_div.find('a')
            if link and link.get('href'):
                href = link.get('href')
                
                match = re.search(r'/welcome/list_by_type/(\d+)/(\d+)', href)
                if match:
                    gazette_type = int(match.group(1))
                    year = int(match.group(2))
                    
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
        session.close()
        return gazette_collections
    
    def process_collection(self, collection_info):
        """Process a single collection (designed to run in a thread)"""
        thread_id = threading.current_thread().ident
        session = self.create_session()
        
        try:
            logger.info(f"[{thread_id}] Processing: {collection_info['type_name']} {collection_info['year']}")
            
            # Get individual gazettes from collection
            individual_gazettes = self.get_individual_gazettes_from_collection(collection_info, session)
            
            if not individual_gazettes:
                logger.info(f"[{thread_id}] No gazettes found in {collection_info['folder_name']}")
                return
            
            # Download each gazette in this collection
            downloaded_count = 0
            for gazette_info in individual_gazettes:
                try:
                    success = self.download_gazette(gazette_info, session)
                    if success:
                        downloaded_count += 1
                    
                    # Random delay between downloads
                    self.random_delay()
                    
                except Exception as e:
                    logger.error(f"[{thread_id}] Error downloading gazette: {e}")
                    self.stats['download_errors'].increment()
            
            # Update progress
            self.stats['collections_processed'].increment()
            
            with self.progress_lock:
                self.processed_collections.append({
                    'collection': collection_info['folder_name'],
                    'gazettes_found': len(individual_gazettes),
                    'gazettes_downloaded': downloaded_count,
                    'thread_id': thread_id
                })
            
            logger.info(f"[{thread_id}] Completed {collection_info['folder_name']}: "
                       f"{downloaded_count}/{len(individual_gazettes)} downloaded")
            
        except Exception as e:
            logger.error(f"[{thread_id}] Error processing collection {collection_info['folder_name']}: {e}")
        
        finally:
            session.close()
    
    def get_individual_gazettes_from_collection(self, collection_info, session):
        """Extract individual gazette links from a collection page"""
        url = collection_info['url']
        
        response = session.get(url)
        if response.status_code != 200:
            logger.warning(f"Failed to fetch collection page: {response.status_code}")
            return []
        
        soup = BeautifulSoup(response.content, 'html.parser')
        individual_gazettes = []
        
        if "Table of Contents" not in response.text:
            return []
        
        content_divs = soup.find_all('div', class_='list-content')
        
        for i, content_div in enumerate(content_divs, 1):
            link = content_div.find('a')
            if link and link.get('href'):
                href = link.get('href')
                title = link.get_text(strip=True)
                
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
        
        self.stats['gazettes_found'].increment()
        return individual_gazettes
    
    def download_gazette(self, gazette_info, session):
        """Download an individual gazette file"""
        collection = gazette_info['collection']
        
        # Create folder for this collection
        collection_folder = self.download_dir / collection['folder_name']
        collection_folder.mkdir(exist_ok=True)
        
        download_url = gazette_info['download_url']
        safe_filename = gazette_info['safe_filename']
        
        try:
            # Check content type
            head_response = session.head(download_url, allow_redirects=True, timeout=30)
            
            content_type = head_response.headers.get('content-type', '').lower()
            if 'pdf' in content_type:
                file_extension = '.pdf'
            elif 'zip' in content_type:
                file_extension = '.zip'
            elif 'image' in content_type:
                file_extension = '.jpg'
            else:
                file_extension = '.pdf'
            
            filename = safe_filename + file_extension
            filepath = collection_folder / filename
            
            # Skip if file already exists
            if filepath.exists():
                return True
            
            # Download the file
            response = session.get(download_url, stream=True, timeout=60)
            response.raise_for_status()
            
            # Save the file
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            self.stats['gazettes_downloaded'].increment()
            return True
            
        except Exception as e:
            logger.error(f"Failed to download {gazette_info['title'][:50]}: {e}")
            self.stats['download_errors'].increment()
            return False
    
    def download_all_gazettes_threaded(self, max_collections=None):
        """Main method to download all gazettes using multiple threads"""
        logger.info(f"Starting multi-threaded Nepal Rajpatra download with {self.num_threads} threads...")
        
        # Get all available gazette collections
        collections = self.get_available_gazette_collections()
        
        if not collections:
            logger.error("No gazette collections found")
            return
        
        if max_collections:
            collections = collections[:max_collections]
            logger.info(f"Limited to first {max_collections} collections for testing")
        
        logger.info(f"Processing {len(collections)} collections with {self.num_threads} threads")
        
        # Use ThreadPoolExecutor for better thread management
        with ThreadPoolExecutor(max_workers=self.num_threads, thread_name_prefix="GazetteWorker") as executor:
            # Submit all collections to the thread pool
            future_to_collection = {
                executor.submit(self.process_collection, collection): collection 
                for collection in collections
            }
            
            # Process completed tasks
            completed = 0
            for future in as_completed(future_to_collection):
                collection = future_to_collection[future]
                completed += 1
                
                try:
                    future.result()  # This will raise any exception that occurred
                    logger.info(f"Progress: {completed}/{len(collections)} collections completed")
                except Exception as e:
                    logger.error(f"Collection {collection['folder_name']} generated an exception: {e}")
        
        # Print final statistics
        self.print_final_stats()
    
    def print_progress(self):
        """Print current progress (can be called from another thread)"""
        while True:
            time.sleep(30)  # Print progress every 30 seconds
            collections_done = self.stats['collections_processed'].get()
            gazettes_found = self.stats['gazettes_found'].get()
            gazettes_downloaded = self.stats['gazettes_downloaded'].get()
            errors = self.stats['download_errors'].get()
            
            logger.info(f"PROGRESS: Collections: {collections_done}, "
                       f"Gazettes found: {gazettes_found}, "
                       f"Downloaded: {gazettes_downloaded}, "
                       f"Errors: {errors}")
    
    def print_final_stats(self):
        """Print final download statistics"""
        end_time = datetime.now()
        duration = end_time - self.stats['start_time']
        
        collections_processed = self.stats['collections_processed'].get()
        gazettes_found = self.stats['gazettes_found'].get()
        gazettes_downloaded = self.stats['gazettes_downloaded'].get()
        download_errors = self.stats['download_errors'].get()
        
        print("\n" + "="*70)
        print("MULTI-THREADED NEPAL RAJPATRA DOWNLOAD COMPLETE")
        print("="*70)
        print(f"Threads used: {self.num_threads}")
        print(f"Collections processed: {collections_processed}")
        print(f"Total gazettes found: {gazettes_found}")
        print(f"Successfully downloaded: {gazettes_downloaded}")
        print(f"Download errors: {download_errors}")
        print(f"Success rate: {(gazettes_downloaded / max(gazettes_found, 1)) * 100:.1f}%")
        print(f"Total time: {duration}")
        print(f"Average time per collection: {duration.total_seconds() / max(collections_processed, 1):.1f} seconds")
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
                'num_threads': self.num_threads,
                'delay_range': self.delay_range,
                'statistics': {
                    'collections_processed': self.stats['collections_processed'].get(),
                    'gazettes_found': self.stats['gazettes_found'].get(),
                    'gazettes_downloaded': self.stats['gazettes_downloaded'].get(),
                    'download_errors': self.stats['download_errors'].get(),
                },
                'processed_collections': self.processed_collections
            }
        }
        
        metadata_file = self.download_dir / 'download_metadata.json'
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Metadata saved to {metadata_file}")

def main():
    """Main execution function"""
    print("Multi-threaded Nepal Rajpatra Downloader")
    print("=" * 50)
    print("This version uses multiple threads to download gazettes faster")
    print("Each thread handles one collection at a time")
    print("-" * 50)
    
    # Configuration
    NUM_THREADS = 4  # Number of concurrent threads
    DELAY_RANGE = (1, 3)  # Random delay between downloads (seconds)
    DOWNLOAD_DIRECTORY = "nepal_gazettes_threaded"
    
    # For testing: limit number of collections
    MAX_COLLECTIONS = None  # Set to 10 for testing, None for all
    
    print(f"Number of threads: {NUM_THREADS}")
    print(f"Delay range: {DELAY_RANGE[0]}-{DELAY_RANGE[1]} seconds")
    print(f"Download directory: {DOWNLOAD_DIRECTORY}")
    if MAX_COLLECTIONS:
        print(f"Testing mode: Limited to {MAX_COLLECTIONS} collections")
    
    print("\n⚠️  IMPORTANT:")
    print("- Higher thread count = faster download but more server load")
    print("- Be respectful to the government server")
    print("- The download will create a log file: download_log.txt")
    
    proceed = input("\nProceed with multi-threaded download? (y/N): ").lower().strip()
    if proceed != 'y':
        print("Download cancelled.")
        return
    
    # Initialize downloader
    downloader = NepalGazetteDownloaderThreaded(
        num_threads=NUM_THREADS,
        delay_range=DELAY_RANGE,
        download_dir=DOWNLOAD_DIRECTORY
    )
    
    try:
        # Start download process
        downloader.download_all_gazettes_threaded(max_collections=MAX_COLLECTIONS)
        
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