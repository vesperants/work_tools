#!/usr/bin/env python3
"""
Example usage of the Gemini PDF Processor.
This script demonstrates how to use the processor programmatically.
"""

from gemini_api import GeminiPDFProcessor, BatchPDFProcessor
import os

def example_basic_usage():
    """Basic example of processing a single PDF file."""
    try:
        # Initialize the processor with verbose logging
        print("🚀 Initializing Gemini PDF Processor...")
        processor = GeminiPDFProcessor(verbose=True)
        
        # Example PDF path (replace with your actual PDF)
        pdf_path = "example_document.pdf"
        
        # Check if file exists
        if not os.path.exists(pdf_path):
            print(f"❌ Example PDF not found: {pdf_path}")
            print("Please place a PDF file named 'example_document.pdf' in this directory")
            return
        
        print("\n" + "="*60)
        print("📖 Processing single PDF with auto-selected free model...")
        print("="*60)
        
        # Process the PDF with auto-selected free model (no model specified)
        response = processor.process_pdf(pdf_path)
        
        # Save the response
        output_path = processor.save_response(response)
        
        print(f"\n🎉 Success! Output saved to: {output_path}")
        
    except Exception as e:
        print(f"❌ Error: {e}")

def example_batch_processing():
    """Example of processing multiple PDF files with threading."""
    try:
        print("🚀 Initializing Batch PDF Processor...")
        
        # Example PDF files (replace with your actual PDFs)
        pdf_files = [
            "document1.pdf",
            "document2.pdf", 
            "document3.pdf"
        ]
        
        # Check which files exist
        existing_files = [f for f in pdf_files if os.path.exists(f)]
        
        if not existing_files:
            print(f"❌ No example PDFs found from: {pdf_files}")
            print("Please place some PDF files in this directory and update the file names")
            return
        
        print(f"📄 Found {len(existing_files)} PDF files to process")
        print("\n" + "="*60)
        print("📖 Processing multiple PDFs with batch processor...")
        print("="*60)
        
        # Initialize batch processor with 3 threads
        batch_processor = BatchPDFProcessor(max_threads=3, verbose=True)
        
        # Process all files
        results = batch_processor.process_batch(
            pdf_files=existing_files,
            model_name=None,  # Auto-select free model
            custom_prompt=None,  # Use default prompt
            output_dir="batch_output"  # Save to specific directory
        )
        
        print(f"\n🎉 Batch processing completed!")
        print(f"📊 Success rate: {results['success_rate']:.1f}%")
        print(f"⏱️ Total time: {results['total_time']:.1f} seconds")
        
    except Exception as e:
        print(f"❌ Error: {e}")

def example_advanced_batch():
    """Advanced example with custom settings for batch processing."""
    try:
        print("🚀 Advanced batch processing example...")
        
        # Custom prompt for different extraction needs
        custom_prompt = """
        Extract all the main sections and subsections from this PDF.
        Format the output as:
        1. Main Section Title
           - Subsection 1
           - Subsection 2
        2. Next Main Section
           - Its subsections
        
        Focus on the hierarchical structure and ignore page numbers.
        """
        
        # Example PDF files
        pdf_files = ["doc1.pdf", "doc2.pdf", "doc3.pdf", "doc4.pdf", "doc5.pdf"]
        existing_files = [f for f in pdf_files if os.path.exists(f)]
        
        if not existing_files:
            print(f"❌ No PDFs found. Create some test files: {pdf_files}")
            return
        
        print(f"📄 Processing {len(existing_files)} files with custom settings")
        print("\n" + "="*60)
        print("📖 Advanced batch processing with custom prompt and 5 threads...")
        print("="*60)
        
        # Initialize batch processor with more threads
        batch_processor = BatchPDFProcessor(max_threads=5, verbose=True)
        
        # Process with custom settings
        results = batch_processor.process_batch(
            pdf_files=existing_files,
            model_name='models/gemini-1.5-flash',  # Specific free model
            custom_prompt=custom_prompt,
            output_dir="advanced_output"
        )
        
        print(f"\n🎉 Advanced batch processing completed!")
        print(f"✅ Successful files: {len(results['successful'])}")
        print(f"❌ Failed files: {len(results['failed'])}")
        
        # Show detailed results
        if results['successful']:
            print("\n✅ Successfully processed:")
            for result in results['successful']:
                print(f"   • {os.path.basename(result['pdf_path'])} → {os.path.basename(result['output_path'])}")
        
        if results['failed']:
            print("\n❌ Failed to process:")
            for result in results['failed']:
                print(f"   • {os.path.basename(result['pdf_path'])}: {result['error']}")
        
    except Exception as e:
        print(f"❌ Error: {e}")

def example_threading_comparison():
    """Example comparing different thread counts."""
    try:
        print("🧵 Threading performance comparison...")
        
        # Create some test files (you would replace with real PDFs)
        test_files = ["test1.pdf", "test2.pdf", "test3.pdf", "test4.pdf"]
        existing_files = [f for f in test_files if os.path.exists(f)]
        
        if len(existing_files) < 2:
            print("❌ Need at least 2 PDF files for threading comparison")
            return
        
        thread_counts = [1, 2, 3]
        
        for thread_count in thread_counts:
            print(f"\n🧵 Testing with {thread_count} thread(s)...")
            print("-" * 40)
            
            batch_processor = BatchPDFProcessor(max_threads=thread_count, verbose=False)
            
            import time
            start_time = time.time()
            
            results = batch_processor.process_batch(
                pdf_files=existing_files[:2],  # Process first 2 files
                output_dir=f"thread_test_{thread_count}"
            )
            
            elapsed_time = time.time() - start_time
            
            print(f"⏱️ {thread_count} thread(s): {elapsed_time:.1f} seconds")
            print(f"📊 Success rate: {results['success_rate']:.1f}%")
        
    except Exception as e:
        print(f"❌ Error: {e}")

def example_model_selection():
    """Example showing how to select different models."""
    try:
        print("🔍 Demonstrating model selection...")
        processor = GeminiPDFProcessor(verbose=False)
        
        # Get available models
        models = processor.get_available_models()
        recommended = processor.get_recommended_free_model()
        
        print("📋 Available models:")
        for i, model in enumerate(models, 1):
            if model == recommended:
                print(f"  {i}. {model} ⭐ (Recommended free)")
            elif 'flash' in model.lower() or '1.5' in model:
                print(f"  {i}. {model} 🆓 (Free tier)")
            else:
                print(f"  {i}. {model} 💰 (May require paid plan)")
        
        print(f"\n🎯 Recommended free model: {recommended}")
        
    except Exception as e:
        print(f"❌ Error listing models: {e}")

def example_error_handling():
    """Example showing how to handle quota and billing errors."""
    try:
        print("⚠️  Demonstrating error handling...")
        processor = GeminiPDFProcessor(verbose=True)
        
        pdf_path = "example_document.pdf"
        
        if not os.path.exists(pdf_path):
            print(f"❌ Example PDF not found: {pdf_path}")
            return
        
        # Try processing with auto-retry on quota errors
        try:
            response = processor.process_pdf(pdf_path)
            output_path = processor.save_response(response)
            print(f"✅ Success! Output: {output_path}")
        except Exception as e:
            if "free quota tier" in str(e).lower():
                print("💡 Quota error detected - the application automatically retries with free models")
            elif "429" in str(e):
                print("💡 Rate limit error - try again in a few minutes")
            else:
                print(f"❌ Other error: {e}")
        
    except Exception as e:
        print(f"❌ Error: {e}")

def main():
    """Run example demonstrations."""
    print("=" * 70)
    print("🎯 Gemini PDF Processor Examples")
    print("   Using google-genai library with FREE models by default")
    print("   Now with BATCH PROCESSING and THREADING support!")
    print("=" * 70)
    
    # List available models
    print("\n1️⃣  Listing available models:")
    print("-" * 40)
    example_model_selection()
    
    # Basic usage example
    print("\n2️⃣  Basic single file processing:")
    print("-" * 40)
    example_basic_usage()
    
    # Batch processing example
    print("\n3️⃣  Batch processing example (NEW!):")
    print("-" * 40)
    example_batch_processing()
    
    # Advanced batch processing
    print("\n4️⃣  Advanced batch processing:")
    print("-" * 40)
    example_advanced_batch()
    
    # Threading comparison
    print("\n5️⃣  Threading performance comparison:")
    print("-" * 40)
    example_threading_comparison()
    
    # Error handling example
    print("\n6️⃣  Error handling example:")
    print("-" * 40)
    example_error_handling()
    
    print("\n" + "=" * 70)
    print("✅ Examples completed!")
    print("\n📝 To run with your own PDFs:")
    print("   1. Place your PDF files in this directory")
    print("   2. Update the file names in the examples")
    print("   3. Run this script again")
    print("\n🚀 Command line usage:")
    print("   Single file: python gemini_api.py your_document.pdf")
    print("   Batch mode:  python gemini_api.py file1.pdf file2.pdf file3.pdf --threads 3")
    print("\n🖥️  GUI with batch support:")
    print("   python gemini_gui.py")
    print("\n📦 Make sure to install the library:")
    print("   pip install google-genai")
    print("\n💡 Key Features:")
    print("   ✅ Auto-selects FREE models by default")
    print("   ✅ Batch processing with configurable threading")
    print("   ✅ Queue management and progress tracking")
    print("   ✅ Automatic retry with free models on quota errors")
    print("   ✅ Real-time progress updates and logging")
    print("   ✅ Thread-safe processing with error isolation")
    print("=" * 70)

if __name__ == "__main__":
    main() 