# Gemini PDF Processor - Najir Extractor

A simple Python application that processes PDF files using Google's Gemini API to extract structured content (najirs) and save the results as text files.

## 🆓 **FREE TIER FRIENDLY** 🆓

**This application automatically uses FREE Gemini models by default!** No billing required for basic usage.

## ✨ **NEW: BATCH PROCESSING WITH THREADING** ✨

**Process multiple PDF files simultaneously with configurable threading!** Queue management, progress tracking, and parallel processing for maximum efficiency.

## Features

- **🆓 Free by Default**: Automatically selects free Gemini models (gemini-1.5-flash, gemini-1.5-pro)
- **📄 PDF Processing**: Upload and process PDF files using Gemini AI
- **🚀 Batch Processing**: Process multiple PDFs simultaneously with threading
- **🧵 Configurable Threading**: 1-10 concurrent threads with queue management
- **📊 Progress Tracking**: Real-time progress updates and queue status
- **🔄 Smart Model Selection**: Auto-retry with free models if paid models fail
- **📝 Custom Prompts**: Use custom system prompts or the default najir extraction prompt
- **🖥️ Multiple Interfaces**: Both command-line and GUI versions with batch support
- **📁 Structured Output**: Automatically saves results as organized text files
- **⚠️ Error Handling**: Comprehensive error handling with helpful guidance
- **📈 Progress Logging**: Detailed progress logs to track processing status
- **💡 Smart Indicators**: Clear visual indicators for free vs paid models

## Prerequisites

- Python 3.7 or higher
- Google Cloud account with Gemini API access
- Gemini API key (FREE tier available!)

## Installation

1. **Clone or download this repository**
   ```bash
   git clone <repository-url>
   cd Firebase_email_extractor
   ```

2. **Install required dependencies**
   ```bash
   pip install -r requirements.txt
   ```

   Or install manually:
   ```bash
   pip install google-genai python-dotenv pathlib2
   ```

3. **Set up your API key**
   
   Create a `.env` file in the project directory:
   ```bash
   GEMINI_API_KEY=your_gemini_api_key_here
   ```
   
   Get your FREE API key from: https://makersuite.google.com/app/apikey

## Usage

### Command Line Interface

**Single file processing (auto-selects FREE model):**
```bash
python gemini_api.py your_document.pdf
```

**Batch processing multiple files:**
```bash
python gemini_api.py file1.pdf file2.pdf file3.pdf
```

**Batch processing with custom threading:**
```bash
python gemini_api.py *.pdf --threads 5 --output batch_results/
```

**With specific free model:**
```bash
python gemini_api.py file1.pdf file2.pdf --model models/gemini-1.5-flash --threads 3
```

**List available models with free/paid indicators:**
```bash
python gemini_api.py --list-models
```

**All command line options:**
```bash
python gemini_api.py --help
```

### Graphical User Interface (NEW BATCH MODE)

**Launch the GUI with batch processing:**
```bash
python gemini_gui.py
```

The GUI now provides:
- **📁 Multiple file selection** with Ctrl/Cmd support
- **🧵 Threading configuration** (1-10 threads)
- **📊 Real-time queue display** showing file status
- **📈 Progress tracking** with completion percentages
- Model selection dropdown with **🆓 Free** and **💰 Paid** indicators
- **⭐ Recommended free model** highlighted
- Custom prompt input
- Output directory configuration
- **📋 Three-tab interface**: Batch Processing, File Queue, Progress Log

### Programmatic Usage

**Single file processing:**
```python
from gemini_api import GeminiPDFProcessor

# Initialize processor
processor = GeminiPDFProcessor(verbose=True)

# Process PDF with auto-selected FREE model
response = processor.process_pdf("your_document.pdf")

# Save results
output_path = processor.save_response(response)
print(f"Results saved to: {output_path}")
```

**Batch processing with threading:**
```python
from gemini_api import BatchPDFProcessor

# Initialize batch processor with 3 threads
batch_processor = BatchPDFProcessor(max_threads=3, verbose=True)

# Process multiple files
pdf_files = ["doc1.pdf", "doc2.pdf", "doc3.pdf"]
results = batch_processor.process_batch(
    pdf_files=pdf_files,
    model_name=None,  # Auto-select free model
    output_dir="batch_output"
)

print(f"Success rate: {results['success_rate']:.1f}%")
print(f"Total time: {results['total_time']:.1f} seconds")
```

## Threading and Performance

### Thread Configuration

- **Default**: 3 concurrent threads (recommended)
- **Range**: 1-10 threads
- **Optimal**: 3-5 threads for most systems
- **Queue**: Automatic queue management for pending files

### Performance Benefits

```bash
# Single threaded (1 file at a time)
python gemini_api.py *.pdf --threads 1

# Multi-threaded (3 files simultaneously) - FASTER!
python gemini_api.py *.pdf --threads 3

# High throughput (5 files simultaneously) - FASTEST!
python gemini_api.py *.pdf --threads 5
```

### Queue Management

The application automatically manages file processing with:
- **📋 Queue display**: Shows all files and their status
- **🔄 Status tracking**: Queued → Processing → Completed/Failed
- **🧵 Thread assignment**: Shows which thread is processing each file
- **📊 Progress updates**: Real-time completion percentages

## Model Selection

### 🆓 Free Models (Recommended)
- **models/gemini-1.5-flash** ⭐ - Fast and free, perfect for most tasks
- **models/gemini-1.5-pro** - More capable, still free with generous limits
- **models/gemini-2.0-flash-exp** - Experimental but free

### 💰 Paid Models
- **models/gemini-2.5-pro-preview-05-06** - Advanced but requires billing

The application **automatically selects free models** and **retries with free alternatives** if you accidentally select a paid model without billing enabled.

## Configuration

### Default System Prompt

The application uses this default prompt for najir extraction:

```
I will give you a pdf file. There are najirs and related points. I just want that in a structured text format. structure could be the parent title, then najir title and the given points for that najir. understand how the whole document is structured first. then figure out the best way to structure the output text. i don't care about anything about the book or the page numbers or anything other than the najirs with the organized format.
```

### Custom Prompts

You can provide custom prompts for different extraction needs:

```python
custom_prompt = """
Extract all main sections and subsections from this PDF.
Format as numbered lists with clear hierarchy.
Ignore page numbers and headers.
"""

# Single file
response = processor.process_pdf(
    pdf_path="document.pdf",
    custom_prompt=custom_prompt
)

# Batch processing
results = batch_processor.process_batch(
    pdf_files=["doc1.pdf", "doc2.pdf"],
    custom_prompt=custom_prompt
)
```

## Progress Logging

The application provides detailed progress logging with threading information:

```
[23:50:53] 🔑 API key found, initializing Gemini client...
[23:50:56] ✅ Gemini API initialized successfully
[23:50:56] 📋 Found 45 available models
[23:50:56] ⭐ Recommended free model: models/gemini-1.5-flash
[23:51:03] 🚀 Starting batch processing of 3 files
[23:51:03] 🧵 Using 3 concurrent threads
[23:51:03] 📋 Queue size: 3 files
[23:51:04] 🧵 Thread PDFWorker-1: Starting document1.pdf
[23:51:04] 🧵 Thread PDFWorker-2: Starting document2.pdf
[23:51:04] 🧵 Thread PDFWorker-3: Starting document3.pdf
[23:51:35] ✅ Thread PDFWorker-1: Completed document1.pdf
[23:51:42] ✅ Thread PDFWorker-2: Completed document2.pdf
[23:51:48] ✅ Thread PDFWorker-3: Completed document3.pdf
[23:51:48] 📊 Progress: 3/3 (100.0%) - ✅ document3.pdf
[23:51:48] 🎉 Batch processing completed!
[23:51:48] ⏱️  Total time: 44.2 seconds
[23:51:48] ✅ Successful: 3
[23:51:48] ❌ Failed: 0
```

## Error Handling & Smart Recovery

The application includes intelligent error handling with threading support:

### Automatic Free Model Retry
If you select a paid model without billing:
```
❌ Model requires paid plan - trying free alternative...
🔄 Retrying with free model: models/gemini-1.5-flash
✅ Content analysis completed successfully
```

### Thread-Safe Error Isolation
Failed files don't stop other threads:
```
🧵 Thread PDFWorker-1: ✅ Completed document1.pdf
🧵 Thread PDFWorker-2: ❌ Error processing document2.pdf: Rate limit
🧵 Thread PDFWorker-3: ✅ Completed document3.pdf
📊 Final results: 2/3 successful (66.7% success rate)
```

### Common Error Solutions

1. **"Model requires paid plan"**
   - ✅ **Automatic fix**: App retries with free model
   - 💡 **Manual fix**: Select a model marked with 🆓

2. **"Free tier quota exceeded"**
   - ⏰ **Solution**: Wait a few minutes and try again
   - 🔄 **Alternative**: Try a different free model
   - 🧵 **Batch tip**: Reduce thread count to avoid rate limits

3. **"GEMINI_API_KEY not found"**
   - 📝 **Solution**: Create a `.env` file with your API key
   - 🔗 **Get key**: https://makersuite.google.com/app/apikey

4. **"Failed to upload file"**
   - 🌐 **Check**: Internet connection
   - 📄 **Verify**: PDF file is not corrupted
   - 📏 **Limit**: File size under 2GB

## File Structure

```
Firebase_email_extractor/
├── gemini_api.py          # Main processor with batch support
├── gemini_gui.py          # GUI with batch processing interface
├── example_usage.py       # Usage examples including batch
├── requirements.txt       # Dependencies
├── README.md             # This file
└── .env                  # API key (create this)
```

## Troubleshooting

### Quick Fixes

| Problem | Solution |
|---------|----------|
| Billing error | Use free models (🆓) - app auto-selects them |
| Rate limit | Reduce thread count or wait 1-2 minutes |
| No API key | Create `.env` file with `GEMINI_API_KEY=your_key` |
| Upload fails | Check internet, verify PDF is valid |
| Slow processing | Increase thread count (up to 5) |
| Memory issues | Reduce thread count to 1-2 |

### Threading Best Practices

- **Start with 3 threads** (default recommendation)
- **Increase to 5** for faster processing if system handles it well
- **Reduce to 1-2** if experiencing rate limits or memory issues
- **Monitor queue display** in GUI for optimal thread utilization

### Getting Help

- 📊 Check the progress logs for detailed error information
- 🆓 Use free models to avoid billing issues
- 📚 Run `python example_usage.py` for working examples
- 🧵 Try different thread counts if experiencing issues

## Dependencies

- `google-genai>=0.3.0` - Google Generative AI SDK (NEW version)
- `python-dotenv>=1.0.0` - Environment variable management
- `pathlib2>=2.3.7` - Path utilities
- `tkinter` - GUI framework (usually included with Python)

## What's New

**Latest Updates:**
- ✅ **Batch processing**: Process multiple PDFs simultaneously
- 🧵 **Threading support**: Configurable 1-10 concurrent threads
- 📊 **Queue management**: Real-time status tracking and progress
- 🖥️ **Enhanced GUI**: Three-tab interface with queue display
- 📈 **Performance boost**: Parallel processing for faster results
- 🔄 **Smart retry**: Automatic fallback to free models on quota errors
- 🏷️ **Clear indicators**: Visual markers for free (🆓) vs paid (💰) models
- 📋 **Better logging**: Thread-aware progress information
- ⚡ **Updated SDK**: Uses latest `google-genai` library
- 🛡️ **Error isolation**: Failed files don't stop other threads

## License

This project is open source. Please ensure you comply with Google's API terms of service when using the Gemini API.

---

## 🎯 **Quick Start for Batch Processing**

1. Get your FREE API key: https://makersuite.google.com/app/apikey
2. Create `.env` file: `GEMINI_API_KEY=your_key_here`
3. Install: `pip install google-genai python-dotenv`
4. **Single file**: `python gemini_api.py document.pdf`
5. **Batch mode**: `python gemini_api.py *.pdf --threads 3`
6. **GUI batch**: `python gemini_gui.py`
7. ✅ **Done!** - Process multiple files simultaneously with free models! 