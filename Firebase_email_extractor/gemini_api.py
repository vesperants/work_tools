import os
from google import genai
from pathlib import Path
import argparse
from datetime import datetime
from dotenv import load_dotenv
import time
import threading
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed

# Load environment variables
load_dotenv()

class GeminiPDFProcessor:
    """
    A simple class to process PDF files using Google's Gemini API.
    Extracts structured content (najirs) from PDFs and saves as text files.
    """
    
    def __init__(self, verbose=True):
        """Initialize the Gemini API client with API key from environment."""
        self.verbose = verbose
        
        # Get API key from environment variable
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables")
        
        if self.verbose:
            print("🔑 API key found, initializing Gemini client...")
        
        # Configure the Gemini API client
        self.client = genai.Client(api_key=api_key)
        
        if self.verbose:
            print("✅ Gemini API client initialized successfully")
        
        # Default system prompt for najir extraction
        self.system_prompt = """
                    Extract and structure the content from this PDF into plain text format. The document contains najirs (sections) with summarized bullet points.
                    Your task:

                    First, analyze the document structure to understand the organization
                    Extract only the najirs and their associated bullet points
                    Output in this hierarchy: Parent title → Najir title → Bullet points
                    Ignore all other content (book information, page numbers, etc.)

                    Output format requirements:

                    Plain text only (no formatting, bold, or markdown)
                    Add blank lines between different najirs for spacing
                    Use a dash (-) at the start of each bullet point
                    Each bullet point on a new line
                    No commentary or explanations
                    Just the extracted content in the specified format"""
    
    def log(self, message):
        """Print log message if verbose mode is enabled."""
        if self.verbose:
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"[{timestamp}] {message}")
    
    def get_available_models(self):
        """Get list of available Gemini models that support file uploads."""
        self.log("🔍 Fetching available Gemini models...")
        models = []
        try:
            for model in self.client.models.list():
                models.append(model.name)
                self.log(f"   ✓ Found model: {model.name}")
            
            self.log(f"📋 Found {len(models)} available models")
            return models
        except Exception as e:
            self.log(f"⚠️  Error fetching models: {e}")
            self.log("🔄 Using fallback model list")
            return ['models/gemini-1.5-flash', 'models/gemini-1.5-pro']  # Free tier models
    
    def get_recommended_free_model(self):
        """Get the recommended free tier model for PDF processing."""
        free_models = [
            'models/gemini-2.5-flash-preview-05-20',
        ]
        
        available_models = self.get_available_models()
        
        # Find the first available free model for text generation
        for model in free_models:
            if model in available_models:
                return model
        
        # Fallback: find any 1.5-flash or 1.5-pro model
        for model in available_models:
            if ('1.5-flash' in model or '1.5-pro' in model) and 'embedding' not in model.lower():
                return model
        
        # Ultimate fallback
        return 'models/gemini-1.5-flash'
    
    def upload_file(self, file_path):
        """
        Upload a PDF file to Gemini API.
        Returns the uploaded file object.
        """
        try:
            # Get file size for progress info
            file_size = os.path.getsize(file_path) / (1024 * 1024)  # Size in MB
            self.log(f"📄 Preparing to upload: {os.path.basename(file_path)} ({file_size:.1f} MB)")
            
            # Start upload
            self.log("⬆️  Starting file upload to Gemini...")
            start_time = time.time()
            
            uploaded_file = self.client.files.upload(file=file_path)
            
            upload_time = time.time() - start_time
            self.log(f"✅ File uploaded successfully in {upload_time:.1f} seconds")
            self.log(f"📁 File ID: {uploaded_file.name}")
            
            # Wait for file to be processed
            self.log("⏳ Waiting for file to be processed by Gemini...")
            while uploaded_file.state == "PROCESSING":
                time.sleep(1)
                uploaded_file = self.client.files.get(name=uploaded_file.name)
                self.log("   🔄 Still processing...")
            
            if uploaded_file.state == "FAILED":
                raise Exception(f"File processing failed: {uploaded_file.state}")
            
            self.log("✅ File processed and ready for analysis")
            return uploaded_file
            
        except Exception as e:
            raise Exception(f"Failed to upload file: {e}")
    
    def process_pdf(self, pdf_path, model_name=None, custom_prompt=None):
        """
        Process a PDF file using Gemini API.
        
        Args:
            pdf_path (str): Path to the PDF file
            model_name (str): Gemini model to use (auto-selects free model if None)
            custom_prompt (str): Custom system prompt (optional)
        
        Returns:
            str: Processed text response from Gemini
        """
        try:
            self.log("🚀 Starting PDF processing...")
            self.log(f"📖 PDF file: {os.path.basename(pdf_path)}")
            
            # Auto-select free model if none specified
            if model_name is None:
                model_name = self.get_recommended_free_model()
                self.log(f"🤖 Auto-selected free model: {model_name}")
            else:
                self.log(f"🤖 Using specified model: {model_name}")
            
            # Use custom prompt if provided, otherwise use default
            prompt = custom_prompt if custom_prompt else self.system_prompt
            if custom_prompt:
                self.log("📝 Using custom prompt")
            else:
                self.log("📝 Using default najir extraction prompt")
            
            # Upload the PDF file
            uploaded_file = self.upload_file(pdf_path)
            
            # Initialize the model and generate content
            self.log(f"🧠 Initializing {model_name}...")
            
            # Generate content with the uploaded file and prompt
            self.log("🔮 Sending request to Gemini for content analysis...")
            self.log("   This may take a few minutes depending on file size...")
            
            start_time = time.time()
            response = self.client.models.generate_content(
                model=model_name,
                contents=[prompt, uploaded_file]
            )
            processing_time = time.time() - start_time
            
            self.log(f"✅ Content analysis completed in {processing_time:.1f} seconds")
            
            # Check if response has text
            if not response.text:
                raise Exception("Gemini returned empty response")
            
            response_length = len(response.text)
            self.log(f"📊 Generated response: {response_length} characters")
            
            # Return the generated text
            return response.text
            
        except Exception as e:
            error_msg = str(e)
            
            # Check for quota/billing errors and provide helpful guidance
            if "429" in error_msg and "RESOURCE_EXHAUSTED" in error_msg:
                if "free quota tier" in error_msg.lower():
                    self.log("❌ Model requires paid plan - trying free alternative...")
                    # Try with a free model
                    free_model = self.get_recommended_free_model()
                    if free_model != model_name:
                        self.log(f"🔄 Retrying with free model: {free_model}")
                        return self.process_pdf(pdf_path, free_model, custom_prompt)
                    else:
                        raise Exception(f"Free tier quota exceeded. Please try again later or upgrade to a paid plan. Original error: {error_msg}")
                else:
                    raise Exception(f"Rate limit exceeded. Please wait and try again. Original error: {error_msg}")
            
            self.log(f"❌ Error during processing: {error_msg}")
            raise Exception(f"Error processing PDF: {error_msg}")
    
    def save_response(self, response_text, output_path=None):
        """
        Save the Gemini response to a text file.
        
        Args:
            response_text (str): The response text from Gemini
            output_path (str): Custom output path (optional)
        
        Returns:
            str: Path to the saved file
        """
        try:
            self.log("💾 Preparing to save response...")
            
            # Generate output filename if not provided
            if not output_path:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path = f"najir_extraction_{timestamp}.txt"
            
            self.log(f"📁 Output file: {output_path}")
            
            # Ensure output directory exists
            output_dir = Path(output_path).parent
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Save the response to file
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write("# Najir Extraction Results\n")
                f.write(f"# Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"# Model used: Gemini API\n\n")
                f.write(response_text)
            
            file_size = os.path.getsize(output_path) / 1024  # Size in KB
            self.log(f"✅ Response saved successfully ({file_size:.1f} KB)")
            self.log(f"📍 File location: {os.path.abspath(output_path)}")
            
            return output_path
            
        except Exception as e:
            self.log(f"❌ Error saving file: {e}")
            raise Exception(f"Error saving response: {e}")


class BatchPDFProcessor:
    """
    Batch processor for multiple PDF files using threaded processing with queue.
    Processes multiple PDFs concurrently with configurable thread count.
    """
    
    def __init__(self, max_threads=3, verbose=True):
        """
        Initialize the batch processor.
        
        Args:
            max_threads (int): Maximum number of concurrent processing threads
            verbose (bool): Enable verbose logging
        """
        self.max_threads = max_threads
        self.verbose = verbose
        self.processor = GeminiPDFProcessor(verbose=False)  # We'll handle logging ourselves
        self.results = {}
        self.errors = {}
        self.progress_callback = None
        
        if self.verbose:
            print(f"🔧 Batch processor initialized with {max_threads} threads")
    
    def log(self, message):
        """Print log message if verbose mode is enabled."""
        if self.verbose:
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"[{timestamp}] {message}")
        
        # Call progress callback if set
        if self.progress_callback:
            self.progress_callback(message)
    
    def set_progress_callback(self, callback):
        """Set a callback function for progress updates (useful for GUI)."""
        self.progress_callback = callback
    
    def process_single_file(self, file_info):
        """
        Process a single PDF file.
        
        Args:
            file_info (dict): Dictionary containing file processing information
                - pdf_path: Path to PDF file
                - output_path: Output file path (optional)
                - model_name: Model to use (optional)
                - custom_prompt: Custom prompt (optional)
        
        Returns:
            dict: Processing result with success/error information
        """
        pdf_path = file_info['pdf_path']
        thread_id = threading.current_thread().name
        
        try:
            self.log(f"🧵 Thread {thread_id}: Starting {os.path.basename(pdf_path)}")
            
            # Create a custom processor for this thread
            thread_processor = GeminiPDFProcessor(verbose=False)
            
            # Process the PDF
            response = thread_processor.process_pdf(
                pdf_path=pdf_path,
                model_name=file_info.get('model_name'),
                custom_prompt=file_info.get('custom_prompt')
            )
            
            # Generate output path if not provided
            output_path = file_info.get('output_path')
            if not output_path:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = Path(pdf_path).stem
                output_path = f"najir_extraction_{filename}_{timestamp}.txt"
            
            # Save the response
            saved_path = thread_processor.save_response(response, output_path)
            
            self.log(f"✅ Thread {thread_id}: Completed {os.path.basename(pdf_path)}")
            
            return {
                'pdf_path': pdf_path,
                'output_path': saved_path,
                'success': True,
                'response_length': len(response),
                'thread_id': thread_id
            }
            
        except Exception as e:
            self.log(f"❌ Thread {thread_id}: Error processing {os.path.basename(pdf_path)}: {e}")
            return {
                'pdf_path': pdf_path,
                'success': False,
                'error': str(e),
                'thread_id': thread_id
            }
    
    def process_batch(self, pdf_files, model_name=None, custom_prompt=None, output_dir=None):
        """
        Process multiple PDF files concurrently.
        
        Args:
            pdf_files (list): List of PDF file paths
            model_name (str): Model to use for all files (optional)
            custom_prompt (str): Custom prompt for all files (optional)
            output_dir (str): Output directory for all files (optional)
        
        Returns:
            dict: Processing results with success and error information
        """
        if not pdf_files:
            raise ValueError("No PDF files provided")
        
        self.log(f"🚀 Starting batch processing of {len(pdf_files)} files")
        self.log(f"🧵 Using {self.max_threads} concurrent threads")
        self.log(f"📋 Queue size: {len(pdf_files)} files")
        
        # Prepare file information for processing
        file_infos = []
        for pdf_path in pdf_files:
            if not os.path.exists(pdf_path):
                self.log(f"⚠️  Skipping non-existent file: {pdf_path}")
                continue
            
            # Generate output path if output directory is specified
            output_path = None
            if output_dir:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = Path(pdf_path).stem
                output_path = os.path.join(output_dir, f"najir_extraction_{filename}_{timestamp}.txt")
            
            file_infos.append({
                'pdf_path': pdf_path,
                'output_path': output_path,
                'model_name': model_name,
                'custom_prompt': custom_prompt
            })
        
        if not file_infos:
            raise ValueError("No valid PDF files found")
        
        self.log(f"📄 Processing {len(file_infos)} valid files")
        
        # Process files using ThreadPoolExecutor
        results = []
        completed_count = 0
        
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=self.max_threads, thread_name_prefix="PDFWorker") as executor:
            # Submit all tasks
            future_to_file = {executor.submit(self.process_single_file, file_info): file_info 
                             for file_info in file_infos}
            
            # Process completed tasks
            for future in as_completed(future_to_file):
                file_info = future_to_file[future]
                result = future.result()
                results.append(result)
                
                completed_count += 1
                progress = (completed_count / len(file_infos)) * 100
                
                if result['success']:
                    self.log(f"📊 Progress: {completed_count}/{len(file_infos)} ({progress:.1f}%) - ✅ {os.path.basename(result['pdf_path'])}")
                else:
                    self.log(f"📊 Progress: {completed_count}/{len(file_infos)} ({progress:.1f}%) - ❌ {os.path.basename(result['pdf_path'])}")
        
        total_time = time.time() - start_time
        
        # Compile final results
        successful = [r for r in results if r['success']]
        failed = [r for r in results if not r['success']]
        
        self.log("=" * 60)
        self.log(f"🎉 Batch processing completed!")
        self.log(f"⏱️  Total time: {total_time:.1f} seconds")
        self.log(f"✅ Successful: {len(successful)}")
        self.log(f"❌ Failed: {len(failed)}")
        self.log("=" * 60)
        
        if failed:
            self.log("❌ Failed files:")
            for result in failed:
                self.log(f"   • {os.path.basename(result['pdf_path'])}: {result['error']}")
        
        if successful:
            self.log("✅ Successful files:")
            for result in successful:
                self.log(f"   • {os.path.basename(result['pdf_path'])} → {os.path.basename(result['output_path'])}")
        
        return {
            'total_files': len(file_infos),
            'successful': successful,
            'failed': failed,
            'total_time': total_time,
            'success_rate': len(successful) / len(file_infos) * 100
        }


def main():
    """Main function to run the PDF processor from command line."""
    parser = argparse.ArgumentParser(description='Process PDF files with Gemini API to extract najirs')
    parser.add_argument('pdf_paths', nargs='*', help='Path(s) to the PDF file(s) to process')
    parser.add_argument('--model', default=None, 
                       help='Gemini model to use (default: auto-select free model)')
    parser.add_argument('--output', help='Output file path for single file or directory for batch')
    parser.add_argument('--prompt', help='Custom system prompt (optional)')
    parser.add_argument('--threads', type=int, default=3,
                       help='Number of concurrent threads for batch processing (default: 3)')
    parser.add_argument('--list-models', action='store_true', 
                       help='List available Gemini models')
    parser.add_argument('--quiet', action='store_true', 
                       help='Suppress progress messages')
    
    args = parser.parse_args()
    
    try:
        # Initialize the processor
        processor = GeminiPDFProcessor(verbose=not args.quiet)
        
        # List models if requested
        if args.list_models:
            print("🔍 Available Gemini models:")
            models = processor.get_available_models()
            recommended = processor.get_recommended_free_model()
            
            for i, model in enumerate(models, 1):
                if model == recommended:
                    print(f"  {i}. {model} ⭐ (Recommended free)")
                elif 'flash' in model.lower() or '1.5' in model:
                    print(f"  {i}. {model} 🆓 (Free tier)")
                else:
                    print(f"  {i}. {model} 💰 (May require paid plan)")
            return
        
        # Check if PDF paths are provided
        if not args.pdf_paths:
            print("❌ Error: Please provide PDF file path(s)")
            print("Usage: python gemini_api.py <pdf_file1> [pdf_file2 ...] [options]")
            print("Use --help for more information")
            return
        
        # Validate PDF files exist
        valid_files = []
        for pdf_path in args.pdf_paths:
            if os.path.exists(pdf_path):
                valid_files.append(pdf_path)
            else:
                print(f"⚠️  Warning: PDF file not found: {pdf_path}")
        
        if not valid_files:
            print("❌ Error: No valid PDF files found")
            return
        
        # Single file processing
        if len(valid_files) == 1:
            pdf_path = valid_files[0]
            print(f"🎯 Processing single PDF: {pdf_path}")
            if args.model:
                print(f"🤖 Using model: {args.model}")
            else:
                print("🤖 Auto-selecting free model...")
            print("=" * 60)
            
            start_time = time.time()
            
            response = processor.process_pdf(
                pdf_path=pdf_path,
                model_name=args.model,
                custom_prompt=args.prompt
            )
            
            # Save the response
            output_path = processor.save_response(response, args.output)
            
            total_time = time.time() - start_time
            
            print("=" * 60)
            print("🎉 SUCCESS! PDF processed successfully.")
            print(f"⏱️  Total processing time: {total_time:.1f} seconds")
            print(f"📁 Output saved to: {output_path}")
            print("=" * 60)
        
        # Batch processing
        else:
            print(f"🎯 Processing {len(valid_files)} PDFs in batch mode")
            print(f"🧵 Using {args.threads} concurrent threads")
            if args.model:
                print(f"🤖 Using model: {args.model}")
            else:
                print("🤖 Auto-selecting free model...")
            print("=" * 60)
            
            # Initialize batch processor
            batch_processor = BatchPDFProcessor(max_threads=args.threads, verbose=not args.quiet)
            
            # Process batch
            results = batch_processor.process_batch(
                pdf_files=valid_files,
                model_name=args.model,
                custom_prompt=args.prompt,
                output_dir=args.output
            )
            
            print("=" * 60)
            print("🎉 BATCH PROCESSING COMPLETED!")
            print(f"📊 Success rate: {results['success_rate']:.1f}%")
            print(f"⏱️  Total time: {results['total_time']:.1f} seconds")
            print("=" * 60)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        if "free quota tier" in str(e).lower():
            print("\n💡 Tip: Try using a free model like 'gemini-1.5-flash'")
            print("   Run: python gemini_api.py --list-models")
        return 1

if __name__ == "__main__":
    main()
