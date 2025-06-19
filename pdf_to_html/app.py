# app.py - Enhanced version with better PDF extraction and improved HTML generation

import os
import uuid
import json
import google.generativeai as genai
from flask import Flask, request, render_template, send_file, flash, redirect, url_for, jsonify
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
import PyPDF2  # For PDF splitting
import threading # For rate limiting locks
from datetime import date, datetime
import zipfile
import io
import re

# --- NEW: Enhanced PDF extraction imports ---
import fitz  # pymupdf - pip install pymupdf
import pdfplumber  # pip install pdfplumber

# --- Import and Initialize Flask-Executor ---
from flask_executor import Executor

# --- Configuration ---
load_dotenv()

# --- Rate Limiting ---
MAX_RPM_PER_KEY = 10
RPM_WINDOW_SECONDS = 60
api_request_timestamps = {}
api_key_locks = {}

# --- Auto-Splitting Configuration ---
MAX_SPLIT_DEPTH = 5

UPLOAD_FOLDER = 'uploads'
GENERATED_FOLDER = 'generated_html'
ALLOWED_EXTENSIONS = {'pdf'}

# --- Flask App Initialization and Config ---
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['GENERATED_FOLDER'] = GENERATED_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024
app.secret_key = os.getenv('FLASK_SECRET_KEY', os.urandom(24))

# --- Configure Executor ---
app.config['EXECUTOR_TYPE'] = 'thread'
app.config['EXECUTOR_MAX_WORKERS'] = 5
executor = Executor(app)

# --- Gemini API Setup ---
api_key = 'AIzaSyCvlTVUdbAFLuARdxQXj9k979pSfA9uSSc'  # Replace with your key
if not api_key:
    raise ValueError("No GOOGLE_API_KEY found")
GEMINI_MODEL_TO_USE = 'gemini-2.5-flash-preview-05-20'
print(f"--- Using Gemini Model: {GEMINI_MODEL_TO_USE} ---")
try:
    genai.configure(api_key=api_key)
except Exception as e:
    raise ValueError(f"Failed to configure Google Gemini API: {e}")

# --- Create necessary directories ---
try:
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(GENERATED_FOLDER, exist_ok=True)
except OSError as e:
    raise OSError(f"Could not create necessary directories: {e}")

# --- Job Status Storage ---
job_status_db = {}

# --- ENHANCED: Helper Functions ---
def allowed_file(filename):
    """Checks if the file extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def clean_text_output(raw_string):
    """
    Cleans the raw text output from Gemini.
    Attempts to remove common markdown code block fences if present.
    """
    if not isinstance(raw_string, str):
        print("Warning: clean_text_output received non-string input.")
        return ""

    text = raw_string.strip()
    content_to_clean = text

    start_tag = "<DOCUMENT_START>"
    end_tag = "<DOCUMENT_END>"

    start_index = text.find(start_tag)
    end_index = text.rfind(end_tag) 

    if start_index != -1 and end_index != -1 and start_index < end_index:
        content_to_clean = text[start_index + len(start_tag) : end_index].strip()
    elif start_index != -1 and end_index == -1:
        content_to_clean = text[start_index + len(start_tag) :].strip()
        print(f"Warning: clean_text_output found '{start_tag}' but no '{end_tag}'.")
    elif start_index == -1 and end_index != -1:
        content_to_clean = text[:end_index].strip()
        print(f"Warning: clean_text_output found '{end_tag}' but no '{start_tag}'.")

    final_cleaned_text = content_to_clean
    patterns_to_check = [
        ("```html", "```"),
        ("```text", "```"),
        ("```", "```")
    ]

    if not isinstance(final_cleaned_text, str):
        final_cleaned_text = ""

    for start_pattern, end_pattern in patterns_to_check:
        if final_cleaned_text and final_cleaned_text.startswith(start_pattern) and final_cleaned_text.endswith(end_pattern):
            if start_pattern == end_pattern:
                if final_cleaned_text.count(start_pattern) >= 2:
                    first_occurrence = final_cleaned_text.find(start_pattern)
                    last_occurrence = final_cleaned_text.rfind(end_pattern)
                    if last_occurrence > first_occurrence + len(start_pattern) -1 :
                        final_cleaned_text = final_cleaned_text[first_occurrence + len(start_pattern) : last_occurrence].strip()
                        break 
            elif start_pattern != end_pattern:
                if len(final_cleaned_text) > len(start_pattern) + len(end_pattern):
                    final_cleaned_text = final_cleaned_text[len(start_pattern):-len(end_pattern)].strip()
                    break 
    
    return final_cleaned_text

def delete_gemini_file_safely(file_object):
    """Attempts to delete a file uploaded to Gemini and prints status."""
    if file_object and hasattr(file_object, 'name'):
        try:
            print(f"Attempting to delete temporary Gemini file: {file_object.name}")
            genai.delete_file(file_object.name)
            print(f"Successfully deleted temporary Gemini file: {file_object.name}")
            return True
        except Exception as delete_err:
            print(f"Warning: Could not delete temporary Gemini file {file_object.name}: {delete_err}")
            return False
    return False

# --- ENHANCED: PDF Text Extraction Functions ---
def extract_text_with_advanced_tools(pdf_path, original_filename):
    """
    Extract text using both pymupdf and pdfplumber, then choose the best result.
    """
    print(f"[Enhanced Extraction] Processing: {pdf_path}")
    
    extraction_results = {
        'pymupdf_text': '',
        'pdfplumber_text': '',
        'tables_found': [],
        'method_used': '',
        'extraction_quality': 'unknown'
    }
    
    try:
        # Method 1: PyMuPDF (better for layout preservation)
        pymupdf_text = extract_with_pymupdf(pdf_path)
        extraction_results['pymupdf_text'] = pymupdf_text
        print(f"[PyMuPDF] Extracted {len(pymupdf_text)} characters")
        
    except Exception as e:
        print(f"[PyMuPDF] Failed: {e}")
        extraction_results['pymupdf_text'] = ''
    
    try:
        # Method 2: pdfplumber (excellent for tables and forms)
        pdfplumber_result = extract_with_pdfplumber(pdf_path)
        extraction_results['pdfplumber_text'] = pdfplumber_result['text']
        extraction_results['tables_found'] = pdfplumber_result['tables']
        print(f"[pdfplumber] Extracted {len(pdfplumber_result['text'])} characters and {len(pdfplumber_result['tables'])} tables")
        
    except Exception as e:
        print(f"[pdfplumber] Failed: {e}")
        extraction_results['pdfplumber_text'] = ''
        extraction_results['tables_found'] = []
    
    # Choose the best extraction method
    best_text = choose_best_extraction(extraction_results)
    
    return {
        'text': best_text,
        'tables_found': len(extraction_results['tables_found']),
        'method_used': extraction_results['method_used'],
        'extraction_stats': {
            'pymupdf_chars': len(extraction_results['pymupdf_text']),
            'pdfplumber_chars': len(extraction_results['pdfplumber_text']),
            'has_tables': len(extraction_results['tables_found']) > 0
        }
    }

def extract_with_pymupdf(pdf_path):
    """Extract text using PyMuPDF with layout preservation."""
    doc = fitz.open(pdf_path)
    full_text = []
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        
        # Get text with layout preservation
        text = page.get_text("dict")
        
        # Convert structured text to readable format
        page_text = []
        for block in text.get("blocks", []):
            if "lines" in block:  # Text block
                for line in block["lines"]:
                    line_text = ""
                    for span in line["spans"]:
                        line_text += span["text"]
                    if line_text.strip():
                        page_text.append(line_text.strip())
        
        if page_text:
            full_text.append(f"\n--- PAGE {page_num + 1} ---\n")
            full_text.append("\n".join(page_text))
    
    doc.close()
    return "\n".join(full_text)

def extract_with_pdfplumber(pdf_path):
    """Extract text and tables using pdfplumber."""
    extracted_text = []
    all_tables = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            page_text = f"\n--- PAGE {page_num + 1} ---\n"
            
            # Extract tables first
            tables = page.extract_tables()
            if tables:
                print(f"[pdfplumber] Found {len(tables)} tables on page {page_num + 1}")
                for i, table in enumerate(tables):
                    page_text += f"\n--- TABLE {i + 1} ---\n"
                    if table:
                        for row in table:
                            if row and any(cell for cell in row if cell):  # Skip empty rows
                                formatted_row = " | ".join([str(cell).strip() if cell else "" for cell in row])
                                page_text += formatted_row + "\n"
                    page_text += "\n"
                all_tables.extend(tables)
            
            # Extract regular text
            text = page.extract_text(layout=True)
            if text:
                page_text += text
            
            extracted_text.append(page_text)
    
    return {
        'text': "\n".join(extracted_text),
        'tables': all_tables
    }

def choose_best_extraction(results):
    """
    Choose the best extraction method based on content analysis.
    """
    pymupdf_text = results['pymupdf_text']
    pdfplumber_text = results['pdfplumber_text']
    tables_found = results['tables_found']
    
    # If pdfplumber found tables, prefer it
    if len(tables_found) > 0:
        results['method_used'] = 'pdfplumber (tables detected)'
        results['extraction_quality'] = 'high'
        return pdfplumber_text
    
    # If pdfplumber text is significantly longer, prefer it
    if len(pdfplumber_text) > len(pymupdf_text) * 1.2:
        results['method_used'] = 'pdfplumber (more content)'
        results['extraction_quality'] = 'medium'
        return pdfplumber_text
    
    # If pymupdf text is much longer, prefer it
    if len(pymupdf_text) > len(pdfplumber_text) * 1.2:
        results['method_used'] = 'pymupdf (more content)'
        results['extraction_quality'] = 'medium'
        return pymupdf_text
    
    # Default to pdfplumber for legal documents (better form handling)
    if pdfplumber_text:
        results['method_used'] = 'pdfplumber (default for legal docs)'
        results['extraction_quality'] = 'medium'
        return pdfplumber_text
    
    # Fallback to pymupdf
    results['method_used'] = 'pymupdf (fallback)'
    results['extraction_quality'] = 'low'
    return pymupdf_text

def preprocess_extracted_text(text):
    """
    Clean and preprocess the extracted text before sending to LLM.
    """
    if not text:
        return text
    
    # Remove excessive whitespace
    text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)  # Max 2 consecutive newlines
    text = re.sub(r'[ \t]+', ' ', text)  # Multiple spaces to single space
    
    # Clean up common OCR artifacts for Nepali text
    text = re.sub(r'([०-९])\s+([०-९])', r'\1\2', text)  # Fix split Nepali numbers
    text = re.sub(r'([क-ह])\s+([़्])', r'\1\2', text)  # Fix split Nepali characters
    
    # Remove page numbers that are clearly standalone
    text = re.sub(r'\n\s*\d+\s*\n', '\n', text)
    text = re.sub(r'\n\s*Page\s+\d+\s*\n', '\n', text, flags=re.IGNORECASE)
    
    # Remove common header/footer patterns
    text = re.sub(r'\n\s*www\..*\.gov\.np\s*\n', '\n', text)
    
    return text.strip()

# --- ENHANCED: Gemini Prompt Functions ---
def get_enhanced_gemini_prompt(original_filename, extraction_result):
    """
    Completely universal prompt that works for ANY Nepali document without specialization
    """
    
    enhanced_prompt = f"""Role: Ultra-precise document converter. You must be EXTREMELY careful and methodical.

Document: '{original_filename}'
Extraction: {extraction_result['tables_found']} tables detected using {extraction_result['method_used']}

CRITICAL MISSION: Create HTML that is VISUALLY IDENTICAL to the original PDF with ZERO errors.

STEP-BY-STEP ANALYSIS REQUIRED:
1. FIRST: Examine the PDF very carefully - look at EVERY element
2. Count table columns from left to right - be precise
3. Read each table header text exactly as written
4. Note all form fields (dots, lines, blank spaces)
5. Identify text alignment (center, left, right)
6. THEN create the HTML

COMPLETE HTML STRUCTURE:
```html
<!DOCTYPE html>
<html lang="ne">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{original_filename}</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Devanagari:wght@300;400;500;600;700&display=swap');
        
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Noto Sans Devanagari', 'Preeti', 'Mukti', Arial, sans-serif;
            font-size: 14px;
            line-height: 1.4;
            color: #000;
            background: #fff;
            max-width: 21cm;
            margin: 0 auto;
            padding: 2.5cm;
            min-height: 29.7cm;
        }}
        
        .header-section {{
            text-align: center;
            margin-bottom: 30px;
        }}
        
        .document-title {{
            font-size: 18px;
            font-weight: 600;
            margin: 15px 0;
            text-align: center;
        }}
        
        .document-subtitle {{
            font-size: 14px;
            margin: 10px 0;
            text-align: center;
        }}
        
        .content-paragraph {{
            margin: 15px 0;
            line-height: 1.7;
            text-align: justify;
        }}
        
        .form-field {{
            border-bottom: 1px dotted #000;
            display: inline-block;
            margin: 0 2px;
            padding-bottom: 2px;
            min-height: 18px;
            vertical-align: baseline;
        }}
        
        .form-field.tiny {{ min-width: 30px; }}
        .form-field.small {{ min-width: 80px; }}
        .form-field.medium {{ min-width: 150px; }}
        .form-field.large {{ min-width: 250px; }}
        .form-field.xlarge {{ min-width: 350px; }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 25px 0;
            font-size: 13px;
            border: 2px solid #000;
        }}
        
        th, td {{
            border: 1px solid #000;
            padding: 12px 8px;
            text-align: left;
            vertical-align: top;
            word-wrap: break-word;
        }}
        
        th {{
            background-color: #f8f8f8;
            font-weight: 600;
            text-align: center;
            line-height: 1.3;
        }}
        
        td {{
            min-height: 40px;
            background-color: #fff;
        }}
        
        .signature-section {{
            margin-top: 50px;
            text-align: right;
            line-height: 2.5;
        }}
        
        .text-center {{ text-align: center; }}
        .text-right {{ text-align: right; }}
        .text-left {{ text-align: left; }}
        .bold {{ font-weight: 600; }}
        .underline {{ text-decoration: underline; }}
        
        @media print {{
            body {{ margin: 0; padding: 1.5cm; font-size: 12px; }}
            @page {{ margin: 1.5cm; size: A4; }}
        }}
    </style>
</head>
<body>
```

ULTRA-STRICT CONVERSION RULES:

1. COMPLETELY IGNORE (DO NOT INCLUDE):
   - All watermarks and background text/images
   - Website URLs (www.*.gov.np, etc.)
   - Page headers with government logos  
   - Page numbers at bottom of pages
   - Any decorative elements or stamps

2. TABLE CONVERSION - BE EXTREMELY CAREFUL:
   STEP 1: Count columns in the PDF table from left to right
   STEP 2: Read each column header text EXACTLY as written
   STEP 3: Create HTML table with EXACT same number of columns
   STEP 4: Copy header text PRECISELY - no changes, no additions
   
   Example methodology:
   - If PDF has 6 columns, HTML must have 6 columns
   - If column header says "सि.नं.", write exactly "सि.नं."
   - If column header says "सुचना कर्ता", write exactly "सुचना कर्ता"
   - Empty cells get &nbsp;
   
   ```html
   <table>
       <thead>
           <tr>
               <th>[Column 1 text exactly]</th>
               <th>[Column 2 text exactly]</th>
               <th>[Column 3 text exactly]</th>
               <th>[Column 4 text exactly]</th>
               <th>[Column 5 text exactly]</th>
               <th>[Column 6 text exactly]</th>
           </tr>
       </thead>
       <tbody>
           <tr>
               <td>&nbsp;</td>
               <td>&nbsp;</td>
               <td>&nbsp;</td>
               <td>&nbsp;</td>
               <td>&nbsp;</td>
               <td>&nbsp;</td>
           </tr>
           <!-- Add more rows as shown in PDF -->
       </tbody>
   </table>
   ```

3. FORM FIELD CONVERSION:
   - Dotted lines (...........): `<span class="form-field medium"></span>`
   - Long dotted lines: `<span class="form-field large"></span>`
   - Short dotted lines: `<span class="form-field small"></span>`
   - Blank lines for writing: `<span class="form-field large"></span>`

4. TEXT PRESERVATION - ZERO TOLERANCE FOR ERRORS:
   - Copy ALL visible text character by character
   - Maintain exact spelling and punctuation  
   - Keep Nepali numerals (०१२३४५६७८९)
   - Preserve all special characters and symbols
   - Maintain exact spacing and line breaks

5. LAYOUT ACCURACY:
   - Center-aligned text: `<div class="text-center">`
   - Right-aligned text: `<div class="text-right">`
   - Bold text: `<span class="bold">`
   - Underlined text: `<span class="underline">`

6. DOCUMENT STRUCTURE HIERARCHY:
   - Main title: `<div class="document-title">`
   - Subtitles: `<div class="document-subtitle">`
   - Body text: `<div class="content-paragraph">`
   - Signature area: `<div class="signature-section">`

VERIFICATION CHECKLIST (CHECK BEFORE FINALIZING):
✓ Table column count matches PDF exactly
✓ All table headers copied word-for-word from PDF  
✓ Every piece of visible text is included
✓ All dotted lines converted to form fields
✓ No page numbers included
✓ No website URLs included
✓ Layout alignment matches original
✓ HTML structure is complete and valid

CRITICAL FAILURE POINTS TO AVOID:
❌ Wrong number of table columns
❌ Missing or altered table headers
❌ Including page numbers
❌ Including website URLs
❌ Missing any visible text content
❌ Incorrect alignment or formatting

WORK METHODOLOGY:
1. Scan PDF top to bottom systematically
2. Note each element and its exact content
3. Create HTML step by step
4. Double-check table structure carefully
5. Verify all text is preserved exactly

OUTPUT FORMAT:
<DOCUMENT_START>
[Complete HTML document - visually identical to PDF]
<DOCUMENT_END>

REMEMBER: This must work perfectly for ANY Nepali document. Be methodical, careful, and precise in every conversion step."""

    return enhanced_prompt

def add_post_processing_improvements(html_content):
    """
    Post-process the generated HTML to fix common issues and improve quality
    """
    # Fix common spacing issues in Nepali text
    html_content = re.sub(r'(\d+)\s+([।॥])', r'\1\2', html_content)  # Fix number-punctuation spacing
    html_content = re.sub(r'([क-ह])\s+([्])', r'\1\2', html_content)  # Fix character-matra spacing
    
    # Improve form field detection and replacement
    def replace_dots_with_fields(match):
        dot_count = len(match.group())
        if dot_count <= 8:
            field_class = "small"
        elif dot_count <= 15:
            field_class = "medium"
        elif dot_count <= 25:
            field_class = "large"
        else:
            field_class = "xlarge"
        return f'<span class="form-field {field_class}"></span>'
    
    html_content = re.sub(r'\.{3,}', replace_dots_with_fields, html_content)
    
    # Fix table structure issues
    html_content = re.sub(r'<td>\s*</td>', '<td>&nbsp;</td>', html_content)
    html_content = re.sub(r'<th>\s*</th>', '<th>&nbsp;</th>', html_content)
    
    # Improve signature line formatting
    html_content = re.sub(
        r'([।:])\s*\.{6,}',
        r'\1 <span class="signature-line"></span>',
        html_content
    )
    
    # Fix common HTML issues
    html_content = re.sub(r'<br\s*/?>\s*<br\s*/?>', '<br><br>', html_content)  # Clean up line breaks
    html_content = re.sub(r'\s+', ' ', html_content)  # Clean up excessive whitespace
    html_content = re.sub(r'>\s+<', '><', html_content)  # Remove spaces between tags
    
    # Ensure proper table borders
    html_content = re.sub(
        r'<table(?![^>]*class=)',
        '<table class="main-table"',
        html_content
    )
    
    return html_content

# --- PDF Splitting Function ---
def split_pdf(pdf_path, original_filename):
    """
    Split a PDF file into two halves and save them separately.
    """
    try:
        print(f"Splitting PDF: {pdf_path}")
        base_name = os.path.splitext(original_filename)[0]
        
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            total_pages = len(pdf_reader.pages)
            
            if total_pages <= 2:
                print(f"PDF {pdf_path} has too few pages to split ({total_pages})")
                return None
                
            mid_point = total_pages // 2
            
            first_half_writer = PyPDF2.PdfWriter()
            second_half_writer = PyPDF2.PdfWriter()
            
            for page_num in range(mid_point):
                first_half_writer.add_page(pdf_reader.pages[page_num])
                
            for page_num in range(mid_point, total_pages):
                second_half_writer.add_page(pdf_reader.pages[page_num])
            
            first_half_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{base_name}_part1.pdf")
            second_half_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{base_name}_part2.pdf")
            
            with open(first_half_path, 'wb') as first_output:
                first_half_writer.write(first_output)
            
            with open(second_half_path, 'wb') as second_output:
                second_half_writer.write(second_output)
                
            print(f"PDF split successfully into: {first_half_path} and {second_half_path}")
            return {
                'first_half': {
                    'path': first_half_path,
                    'filename': f"{base_name}_part1.pdf"
                },
                'second_half': {
                    'path': second_half_path,
                    'filename': f"{base_name}_part2.pdf"
                }
            }
            
    except Exception as e:
        print(f"Error splitting PDF {pdf_path}: {e}")
        traceback.print_exc()
        return None

# --- ENHANCED: Background Task Function ---
def process_single_pdf_html(job_id, file_id, prompt, pdf_path, original_filename, current_split_depth=0):
    """Enhanced PDF processing that outputs HTML with improved styling and layout."""
    print(f"[Enhanced Job {job_id}, File {file_id}, Depth {current_split_depth}] Starting enhanced HTML processing for: {original_filename}")

    # --- Get Job Data ---
    if job_id not in job_status_db:
        print(f"[Job {job_id}, File {file_id}] Error: Job not found.")
        return
    job_data = job_status_db[job_id]
    api_keys = job_data.get('api_keys', [])
    if not api_keys:
        api_keys = [api_key]
        job_data['api_keys'] = api_keys
        job_data['current_key_index'] = 0
        print(f"[Job {job_id}] Warning: No API keys found in job, using default.")

    # --- Update File Status to Processing ---
    file_index = -1
    for idx, f_info in enumerate(job_data['files']):
        if f_info['id'] == file_id:
            f_info['status'] = 'processing'
            file_index = idx
            break
    if file_index == -1:
        print(f"[Job {job_id}, File {file_id}] Error: File ID not found in job.")
        return

    # --- ENHANCED: Better Text Extraction ---
    try:
        print(f"[Job {job_id}, File {file_id}] Extracting text with advanced tools...")
        extraction_result = extract_text_with_advanced_tools(pdf_path, original_filename)
        extracted_text = extraction_result['text']
        
        # Preprocess the text
        processed_text = preprocess_extracted_text(extracted_text)
        
        print(f"[Job {job_id}, File {file_id}] Extraction complete:")
        print(f"  - Method: {extraction_result['method_used']}")
        print(f"  - Raw text: {len(extracted_text)} chars")
        print(f"  - Processed text: {len(processed_text)} chars")
        print(f"  - Tables found: {extraction_result['tables_found']}")
        
        if not processed_text.strip():
            print(f"[Job {job_id}, File {file_id}] Warning: No text extracted from PDF")
            if job_id in job_status_db and file_index != -1:
                job_status_db[job_id]['files'][file_index].update({
                    'status': 'failed',
                    'error': 'No text could be extracted from PDF',
                    'error_type': 'extraction_failed'
                })
            return
            
    except Exception as e:
        print(f"[Job {job_id}, File {file_id}] Text extraction failed: {e}")
        if job_id in job_status_db and file_index != -1:
            job_status_db[job_id]['files'][file_index].update({
                'status': 'failed',
                'error': f'Text extraction failed: {str(e)}',
                'error_type': 'extraction_error'
            })
        return

    # --- Enhanced Gemini Processing ---
    gemini_file_object = None
    generated_text_path = None 
    error_message = None
    error_type = None
    status = 'failed'
    processed_successfully_this_attempt = False

    while not processed_successfully_this_attempt:
        current_key_index = job_data.get('current_key_index', 0)
        
        if current_key_index >= len(api_keys):
            print(f"[Job {job_id}, File {file_id}] All API keys have been tried and failed.")
            error_message = "All available API keys failed (quota/limit reached)."
            error_type = 'api_quota_exhausted'
            status = 'failed'
            break

        current_api_key = api_keys[current_key_index]
        print(f"[Job {job_id}, File {file_id}, Depth {current_split_depth}] Attempting with API key index {current_key_index} (...{current_api_key[-4:]})")
        
        try:
            genai.configure(api_key=current_api_key)
            
            if gemini_file_object is None:
                print(f"[Job {job_id}, File {file_id}] Uploading to Gemini: {pdf_path}")
                gemini_file_object = genai.upload_file(
                    path=pdf_path,
                    display_name=f"{job_id}_{file_id}_{original_filename}",
                    mime_type='application/pdf'
                )
                print(f"[Job {job_id}, File {file_id}] Uploaded as: {gemini_file_object.name}")

            # Use Enhanced Gemini Prompt
            enhanced_system_prompt = get_enhanced_gemini_prompt(original_filename, extraction_result)
            
            # Rate Limiting
            key_lock = api_key_locks.setdefault(current_api_key, threading.Lock())
            with key_lock:
                current_time = time.time()
                timestamps_for_key = api_request_timestamps.setdefault(current_api_key, [])
                timestamps_for_key[:] = [ts for ts in timestamps_for_key if current_time - ts < RPM_WINDOW_SECONDS]
                if len(timestamps_for_key) >= MAX_RPM_PER_KEY:
                    timestamps_for_key.sort()
                    oldest_relevant_timestamp = timestamps_for_key[0]
                    wait_duration = (oldest_relevant_timestamp + RPM_WINDOW_SECONDS) - current_time
                    if wait_duration > 0:
                        print(f"[Job {job_id}, File {file_id}, Key ...{current_api_key[-4:]}] Rate limit: {len(timestamps_for_key)}/{MAX_RPM_PER_KEY} req. Waiting {wait_duration:.2f}s.")
                        time.sleep(wait_duration)
                        current_time = time.time()
                        timestamps_for_key[:] = [ts for ts in timestamps_for_key if current_time - ts < RPM_WINDOW_SECONDS]
                timestamps_for_key.append(current_time)

            # Call Gemini API
            model = genai.GenerativeModel(model_name=GEMINI_MODEL_TO_USE)
            print(f"[Job {job_id}, File {file_id}] Sending request to Gemini with enhanced prompt...")
            response = model.generate_content(
                [enhanced_system_prompt, gemini_file_object],
                request_options={"timeout": 600} 
            )
            raw_response_text = response.text
            
            # Tag-Based Completion Check
            raw_text_stripped = raw_response_text.strip()
            is_complete = raw_text_stripped.startswith("<DOCUMENT_START>") and raw_text_stripped.endswith("<DOCUMENT_END>")
            
            # Clean and post-process the text
            cleaned_text_output = clean_text_output(raw_response_text)
            enhanced_html_output = add_post_processing_improvements(cleaned_text_output)
            
            # Save the enhanced HTML
            job_output_dir = os.path.join(app.config['GENERATED_FOLDER'], job_id)
            os.makedirs(job_output_dir, exist_ok=True)
            base_filename = os.path.splitext(original_filename)[0]
            html_filename = f"{file_id}_{base_filename}_depth{current_split_depth}.html"
            generated_html_path = os.path.join(job_output_dir, html_filename)
            generated_text_path = generated_html_path
            
            try:
                with open(generated_html_path, 'w', encoding='utf-8') as f:
                    f.write(enhanced_html_output)
                print(f"[Job {job_id}, File {file_id}] Enhanced HTML saved to {generated_html_path}")
            except IOError as io_err:
                print(f"[Job {job_id}, File {file_id}] File saving error: {io_err}")
                error_message = f"Failed to save HTML file: {str(io_err)}"
                error_type = 'file_save_error'
                status = 'failed' 
                job_data['current_key_index'] = current_key_index + 1
                continue

            if is_complete:
                print(f"[Job {job_id}, File {file_id}] Enhanced HTML output is complete based on tags.")
                status = 'completed'
                error_message = None
                error_type = None
                processed_successfully_this_attempt = True
            else:
                print(f"[Job {job_id}, File {file_id}, Depth {current_split_depth}] Output incomplete based on tags.")
                if current_split_depth < MAX_SPLIT_DEPTH:
                    print(f"[Job {job_id}, File {file_id}] Attempting auto-split (depth {current_split_depth} < {MAX_SPLIT_DEPTH}).")
                    
                    if job_id in job_status_db and file_index != -1:
                        file_info = job_status_db[job_id]['files'][file_index]
                        file_info['status'] = 'failed'
                        file_info['error'] = "Output incomplete, auto-splitting and retrying with smaller parts."
                        file_info['error_type'] = 'auto_split_incomplete_retrying'
                        file_info['text_path'] = generated_text_path

                    split_result = split_pdf(pdf_path, original_filename)
                    if split_result:
                        print(f"[Job {job_id}, File {file_id}] PDF split successfully. Queuing parts.")
                        parent_prompt = job_data.get('prompt', '')
                        
                        # Queue first half
                        first_half_id = f"{file_id}_p1_d{current_split_depth+1}"
                        job_status_db[job_id]['files'].append({
                            'id': first_half_id, 'original_name': split_result['first_half']['filename'],
                            'pdf_path': split_result['first_half']['path'], 'status': 'pending',
                            'text_path': None, 'error': None, 'error_type': None,
                            'split_depth': current_split_depth + 1
                        })
                        executor.submit(process_single_pdf_html, job_id, first_half_id, parent_prompt,
                                        split_result['first_half']['path'], split_result['first_half']['filename'],
                                        current_split_depth + 1)

                        # Queue second half
                        second_half_id = f"{file_id}_p2_d{current_split_depth+1}"
                        job_status_db[job_id]['files'].append({
                            'id': second_half_id, 'original_name': split_result['second_half']['filename'],
                            'pdf_path': split_result['second_half']['path'], 'status': 'pending',
                            'text_path': None, 'error': None, 'error_type': None,
                            'split_depth': current_split_depth + 1
                        })
                        executor.submit(process_single_pdf_html, job_id, second_half_id, parent_prompt,
                                        split_result['second_half']['path'], split_result['second_half']['filename'],
                                        current_split_depth + 1)
                        
                        if gemini_file_object: 
                            delete_gemini_file_safely(gemini_file_object)
                        
                        if pdf_path and os.path.exists(pdf_path):
                            try:
                                os.remove(pdf_path)
                                print(f"[Job {job_id}, File {file_id}] Parent PDF {pdf_path} deleted after auto-splitting.")
                                if job_id in job_status_db and file_index != -1:
                                     job_status_db[job_id]['files'][file_index].pop('pdf_path', None)
                            except OSError as e:
                                print(f"Error deleting parent PDF {pdf_path} after auto-split: {e}")

                        return

                    else:
                        print(f"[Job {job_id}, File {file_id}] Auto-split failed.")
                        status = 'failed'
                        error_message = "Output incomplete, and auto-split failed (PDF too small or corrupted)."
                        error_type = 'auto_split_pdf_error'
                        processed_successfully_this_attempt = True
                
                else:
                    print(f"[Job {job_id}, File {file_id}] Output incomplete and max split depth ({MAX_SPLIT_DEPTH}) reached.")
                    status = 'failed'
                    error_message = f"Output incomplete after reaching max split depth ({MAX_SPLIT_DEPTH}). Manual review needed."
                    error_type = 'incomplete_max_splits'
                    processed_successfully_this_attempt = True

        except Exception as e:
            print(f"ERROR [Job {job_id}, File {file_id}, Depth {current_split_depth}, Key ...{current_api_key[-4:]}]: Processing attempt failed: {e}")
            traceback.print_exc()
            error_message = str(e)
            status = 'failed'
            error_type = 'general_api_error' 

            error_lower = error_message.lower()
            is_quota_error = any(phrase in error_lower for phrase in [
                'quota exceeded', 'limit exceeded', 'rate limit', 'resource exhausted', 'api key invalid', '429'
            ])

            if is_quota_error:
                print(f"[Job {job_id}, File {file_id}] Quota/Limit Error. Moving to next key.")
                error_type = 'api_quota_error_retry'
                job_data['current_key_index'] = current_key_index + 1 
            else:
                print(f"[Job {job_id}, File {file_id}] General API error. Failing this file for this attempt.")
                processed_successfully_this_attempt = True

    # --- Cleanup ---
    if gemini_file_object:
        delete_gemini_file_safely(gemini_file_object)
    
    # PDF Deletion Logic
    should_delete_this_pdf = False
    if status == 'completed':
        should_delete_this_pdf = True
    elif status == 'failed':
        if error_type not in ['incomplete_max_splits', 'auto_split_pdf_error', 'api_quota_exhausted', 'auto_split_incomplete_retrying']:
            should_delete_this_pdf = True
    
    if pdf_path and os.path.exists(pdf_path) and should_delete_this_pdf:
        try:
            os.remove(pdf_path)
            print(f"[Job {job_id}, File {file_id}] Temp PDF deleted: {pdf_path}")
        except OSError as e:
            print(f"Error deleting temp PDF {pdf_path}: {e}")
    elif pdf_path and os.path.exists(pdf_path):
        print(f"[Job {job_id}, File {file_id}] Keeping temporary PDF: {pdf_path} (Status: {status}, Error Type: {error_type})")

    # --- Update Final Status ---
    if job_id in job_status_db and file_index != -1:
        file_info = job_status_db[job_id]['files'][file_index]
        file_info['status'] = status
        file_info['text_path'] = generated_text_path if generated_text_path and os.path.exists(generated_text_path) else file_info.get('text_path')
        file_info['error'] = error_message 
        file_info['error_type'] = error_type 
        
        if should_delete_this_pdf:
             file_info.pop('pdf_path', None)
             
    elif job_id not in job_status_db:
         print(f"[Job {job_id}, File {file_id}] Critical Error: Job data disappeared before final status update.")

    print(f"[Job {job_id}, File {file_id}, Depth {current_split_depth}] Finished enhanced processing task. Final Status: {status}, Final Error Type: {error_type}")

# --- Upload Route ---
@app.route('/upload', methods=['POST'])
def upload_queue_files():
    """Receives multiple files and queues them for enhanced processing."""
    print("\n--- ENHANCED UPLOAD REQUEST START ---")
    prompt = request.form.get('prompt', '').strip()
    api_keys_str = request.form.get('api_keys', '').strip()
    files = request.files.getlist('file')

    # --- Validation ---
    if not prompt:
        return jsonify({"error": "Please provide a prompt."}), 400
    if not files or all(f.filename == '' for f in files):
        return jsonify({"error": "No files selected."}), 400

    # Parse API keys
    api_keys = [key.strip() for key in api_keys_str.split(',') if key.strip()]
    if not api_keys:
        api_keys = [api_key]
        print(f"No API keys provided, using default.")
    else:
        print(f"Using {len(api_keys)} provided API key(s).")

    valid_files_to_process = []
    for file in files:
        if file and allowed_file(file.filename):
            valid_files_to_process.append(file)
        elif file and file.filename != '':
             print(f"Warning: Disallowed file type skipped: {file.filename}")

    if not valid_files_to_process:
         return jsonify({"error": "No valid PDF files found in selection."}), 400

    # --- Create Job ID and Setup ---
    job_id = str(uuid.uuid4())
    job_status_db[job_id] = {
        'prompt': prompt,
        'api_keys': api_keys,
        'current_key_index': 0,
        'files': [],
        'timestamp': time.time()
    }
    
    print(f"Created new enhanced job: {job_id} with {len(api_keys)} key(s) and prompt: {prompt}")

    # --- Process Each Valid File ---
    for file in valid_files_to_process:
        file_id = str(uuid.uuid4())
        original_filename = file.filename
        
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{file_id}_{original_filename}")
        try:
            file.save(pdf_path)
        except Exception as e:
            print(f"Error saving file {original_filename} to {pdf_path}: {e}")
            print(f"Skipping file due to save error.")
            continue
        
        job_status_db[job_id]['files'].append({
            'id': file_id,
            'original_name': original_filename,
            'pdf_path': pdf_path,
            'status': 'pending',
            'text_path': None,
            'error': None,
            'error_type': None,
            'split_depth': 0
        })
        
        executor.submit(
            process_single_pdf_html,
            job_id,
            file_id,
            prompt,
            pdf_path,
            original_filename,
            0
        )
        
        print(f"Queued file for enhanced processing: {original_filename} with ID: {file_id} at depth 0")

    return jsonify({
        "job_id": job_id,
        "num_files": len(valid_files_to_process),
        "message": f"Enhanced processing started for {len(valid_files_to_process)} files"
    })

# --- Status Route ---
@app.route('/status/<job_id>', methods=['GET'])
def get_job_status(job_id):
    """Return the current processing status for a job."""
    if job_id not in job_status_db:
        return jsonify({"error": "Job not found"}), 404

    job_data = job_status_db[job_id]
    
    total_files = len(job_data['files'])
    completed = sum(1 for file in job_data['files'] if file['status'] == 'completed')
    failed_or_split = sum(1 for file in job_data['files'] if file['status'] == 'failed' or file.get('error_type') == 'auto_split_incomplete_retrying')
    pending = sum(1 for file in job_data['files'] if file['status'] == 'pending')
    processing = sum(1 for file in job_data['files'] if file['status'] == 'processing')
    
    file_details = []
    for file_info in job_data['files']:
        file_detail = {
            'id': file_info['id'],
            'name': file_info['original_name'],
            'status': file_info['status'],
            'can_download': file_info['status'] == 'completed',
            'error': file_info.get('error'),
            'error_type': file_info.get('error_type'),
            'split_depth': file_info.get('split_depth', 0) 
        }
        
        manual_split_eligible_error_types = [
            'pdf_too_large',
            'incomplete_max_splits',
            'auto_split_pdf_error',
            'api_quota_exhausted'
        ]
        
        if file_info.get('error_type') in manual_split_eligible_error_types and \
           'pdf_path' in file_info and file_info['pdf_path'] and os.path.exists(file_info['pdf_path']):
            file_detail['can_split'] = True
        else:
            file_detail['can_split'] = False
            
        file_details.append(file_detail)
    
    terminal_statuses_count = sum(1 for f in job_data['files'] if f['status'] in ['completed', 'failed'])

    return jsonify({
        'job_id': job_id,
        'prompt': job_data['prompt'],
        'stats': {
            'total': total_files,
            'completed': completed,
            'failed_or_split': failed_or_split,
            'pending': pending,
            'processing': processing
        },
        'all_done': terminal_statuses_count == total_files,
        'files': file_details
    })

# --- Download Route ---
@app.route('/download/<job_id>/<file_id>', methods=['GET'])
def download_html_file(job_id, file_id):
    """Sends the generated HTML file for a specific completed file in a job."""
    print(f"--- DOWNLOAD REQUEST for Job ID: {job_id}, File ID: {file_id} (expecting enhanced HTML) ---")
    job_info = job_status_db.get(job_id)
    if not job_info:
        flash("Job not found.", "error")
        return redirect(url_for('index'))

    file_to_download = None
    for f in job_info['files']:
        if f['id'] == file_id:
            file_to_download = f
            break

    if not file_to_download:
        flash(f"File '{file_id}' not found in job '{job_id}'.", "error")
        return redirect(url_for('index'))

    if file_to_download['status'] != 'completed':
        flash(f"File '{file_to_download['original_name']}' is not yet completed or failed.", "warning")
        return redirect(url_for('index'))

    output_path = file_to_download.get('text_path')
    if not output_path or not os.path.exists(output_path):
        flash(f"Error: Generated HTML file for '{file_to_download['original_name']}' not found on server.", "error")
        return redirect(url_for('index'))

    # Create download name with .html extension
    base_filename = os.path.splitext(file_to_download['original_name'])[0]
    download_name = f"{base_filename}_enhanced.html"

    print(f"Sending enhanced HTML file: {output_path} as {download_name}")
    try:
        return send_file(
            output_path,
            as_attachment=True,
            download_name=download_name,
            mimetype='text/html'
        )
    except Exception as e:
         print(f"Error sending file {output_path}: {e}")
         flash(f"Error occurred while trying to send the file.", "error")
         return redirect(url_for('index'))

# --- Download All Route ---
@app.route('/download-all/<job_id>', methods=['GET'])
def download_all_html_files(job_id):
    """Downloads all completed HTML files as a zip."""
    print(f"--- DOWNLOAD ALL REQUEST for Job ID: {job_id} ---")
    job_info = job_status_db.get(job_id)
    if not job_info:
        flash("Job not found.", "error")
        return redirect(url_for('index'))

    completed_files = []
    for f in job_info['files']:
        if f['status'] == 'completed' and 'text_path' in f and f['text_path'] and os.path.exists(f['text_path']):
            completed_files.append({
                'path': f['text_path'],
                'original_name': f['original_name']
            })

    if not completed_files:
        flash("No completed files found to download for this job.", "warning")
        return redirect(url_for('index'))

    # Create zip file in memory
    memory_file = io.BytesIO()
    try:
        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            for file_to_zip in completed_files:
                base_filename = os.path.splitext(file_to_zip['original_name'])[0]
                zip_arcname = f"{base_filename}_enhanced.html"
                print(f"Adding {file_to_zip['path']} to zip as {zip_arcname}")
                zf.write(file_to_zip['path'], arcname=zip_arcname)
    except Exception as e:
        print(f"Error creating zip file for job {job_id}: {e}")
        traceback.print_exc()
        flash("Error creating zip archive.", "error")
        return redirect(url_for('index'))

    memory_file.seek(0)

    zip_download_name = f"job_{job_id}_enhanced_results.zip"
    print(f"Sending enhanced zip file: {zip_download_name}")

    return send_file(
        memory_file,
        mimetype='application/zip',
        as_attachment=True,
        download_name=zip_download_name
    )

# --- Split PDF and Retry Route ---
@app.route('/split-retry/<job_id>/<file_id>', methods=['POST'])
def split_and_retry(job_id, file_id):
    """Split a large PDF into two halves and process each separately (manual trigger)."""
    print(f"\n--- MANUAL SPLIT AND RETRY REQUEST START for Job {job_id}, File {file_id} ---")
    
    if job_id not in job_status_db:
        return jsonify({"error": "Job not found"}), 404
    
    file_info = None
    for f in job_status_db[job_id]['files']:
        if f['id'] == file_id:
            file_info = f
            break
    
    if not file_info:
        return jsonify({"error": "File not found in job"}), 404
    
    if file_info.get('error_type') != 'pdf_too_large' or 'pdf_path' not in file_info:
        return jsonify({"error": "This file cannot be split for retry. Either it's not a size-related error or the original PDF is no longer available."}), 400
    
    original_pdf_path = file_info['pdf_path']
    original_filename = file_info['original_name']
    
    if not os.path.exists(original_pdf_path):
        return jsonify({"error": "Original PDF no longer exists on the server"}), 400
    
    prompt = job_status_db[job_id].get('prompt', '')
    
    split_result = split_pdf(original_pdf_path, original_filename)
    
    if not split_result:
        return jsonify({"error": "Failed to split the PDF. It may be too small or corrupted."}), 500
    
    first_half_id = f"{file_id}_part1"
    second_half_id = f"{file_id}_part2"
    
    parent_split_depth = file_info.get('split_depth', -1)
    new_parts_depth = parent_split_depth + 1 if parent_split_depth != -1 else 0

    job_status_db[job_id]['files'].append({
        'id': first_half_id,
        'original_name': split_result['first_half']['filename'],
        'pdf_path': split_result['first_half']['path'],
        'status': 'pending',
        'text_path': None, 
        'error': None,
        'error_type': None,
        'split_depth': new_parts_depth
    })
    
    job_status_db[job_id]['files'].append({
        'id': second_half_id,
        'original_name': split_result['second_half']['filename'],
        'pdf_path': split_result['second_half']['path'],
        'status': 'pending',
        'text_path': None, 
        'error': None,
        'error_type': None,
        'split_depth': new_parts_depth
    })
    
    file_info['status'] = 'split'
    file_info['error'] = "PDF was split into two parts for processing"
    file_info['error_type'] = 'split_for_retry'
    
    executor.submit(
        process_single_pdf_html,
        job_id,
        first_half_id,
        prompt,
        split_result['first_half']['path'],
        split_result['first_half']['filename'],
        new_parts_depth
    )
    
    executor.submit(
        process_single_pdf_html,
        job_id,
        second_half_id,
        prompt,
        split_result['second_half']['path'],
        split_result['second_half']['filename'],
        new_parts_depth
    )
    
    print(f"--- MANUAL SPLIT AND RETRY REQUEST END: Successfully split PDF and queued {first_half_id} (depth {new_parts_depth}) and {second_half_id} (depth {new_parts_depth}) for enhanced processing ---")
    
    return jsonify({
        "success": True,
        "message": "PDF has been split and enhanced processing started",
        "parts": [first_half_id, second_half_id]
    })

# --- Root Route ---
@app.route('/', methods=['GET'])
def index():
    """Renders the main upload form."""
    return render_template('index.html')

# --- Additional Helper Routes ---
@app.route('/preview/<job_id>/<file_id>', methods=['GET'])
def preview_html_file(job_id, file_id):
    """Preview the generated HTML file in browser."""
    print(f"--- PREVIEW REQUEST for Job ID: {job_id}, File ID: {file_id} ---")
    job_info = job_status_db.get(job_id)
    if not job_info:
        return jsonify({"error": "Job not found"}), 404

    file_to_preview = None
    for f in job_info['files']:
        if f['id'] == file_id:
            file_to_preview = f
            break

    if not file_to_preview:
        return jsonify({"error": "File not found"}), 404

    if file_to_preview['status'] != 'completed':
        return jsonify({"error": "File is not yet completed"}), 400

    output_path = file_to_preview.get('text_path')
    if not output_path or not os.path.exists(output_path):
        return jsonify({"error": "Generated HTML file not found"}), 404

    try:
        with open(output_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        return html_content, 200, {'Content-Type': 'text/html; charset=utf-8'}
    except Exception as e:
        print(f"Error reading HTML file {output_path}: {e}")
        return jsonify({"error": "Error reading HTML file"}), 500

@app.route('/job-info/<job_id>', methods=['GET'])
def get_job_info(job_id):
    """Get detailed information about a job."""
    if job_id not in job_status_db:
        return jsonify({"error": "Job not found"}), 404

    job_data = job_status_db[job_id]
    
    # Calculate statistics
    files = job_data['files']
    total_files = len(files)
    completed_files = [f for f in files if f['status'] == 'completed']
    failed_files = [f for f in files if f['status'] == 'failed']
    processing_files = [f for f in files if f['status'] == 'processing']
    pending_files = [f for f in files if f['status'] == 'pending']
    
    # Calculate total characters processed
    total_chars_processed = 0
    for f in completed_files:
        if f.get('text_path') and os.path.exists(f['text_path']):
            try:
                with open(f['text_path'], 'r', encoding='utf-8') as file:
                    content = file.read()
                    total_chars_processed += len(content)
            except:
                pass
    
    return jsonify({
        'job_id': job_id,
        'created_at': job_data['timestamp'],
        'prompt': job_data['prompt'],
        'api_keys_count': len(job_data.get('api_keys', [])),
        'statistics': {
            'total_files': total_files,
            'completed': len(completed_files),
            'failed': len(failed_files),
            'processing': len(processing_files),
            'pending': len(pending_files),
            'total_chars_processed': total_chars_processed
        },
        'files': [{
            'id': f['id'],
            'name': f['original_name'],
            'status': f['status'],
            'error': f.get('error'),
            'error_type': f.get('error_type'),
            'split_depth': f.get('split_depth', 0),
            'can_download': f['status'] == 'completed',
            'can_preview': f['status'] == 'completed'
        } for f in files]
    })

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'timestamp': time.time(),
        'active_jobs': len(job_status_db),
        'gemini_model': GEMINI_MODEL_TO_USE
    })

@app.route('/cleanup-jobs', methods=['POST'])
def cleanup_old_jobs():
    """Cleanup old jobs and their files."""
    current_time = time.time()
    cleanup_threshold = 24 * 60 * 60  # 24 hours
    
    jobs_to_remove = []
    files_cleaned = 0
    
    for job_id, job_data in job_status_db.items():
        job_age = current_time - job_data.get('timestamp', current_time)
        
        if job_age > cleanup_threshold:
            # Clean up associated files
            for file_info in job_data.get('files', []):
                # Remove generated HTML files
                if file_info.get('text_path') and os.path.exists(file_info['text_path']):
                    try:
                        os.remove(file_info['text_path'])
                        files_cleaned += 1
                    except OSError as e:
                        print(f"Error removing file {file_info['text_path']}: {e}")
                
                # Remove uploaded PDF files
                if file_info.get('pdf_path') and os.path.exists(file_info['pdf_path']):
                    try:
                        os.remove(file_info['pdf_path'])
                        files_cleaned += 1
                    except OSError as e:
                        print(f"Error removing PDF {file_info['pdf_path']}: {e}")
            
            jobs_to_remove.append(job_id)
    
    # Remove job records
    for job_id in jobs_to_remove:
        del job_status_db[job_id]
        
        # Remove job output directory
        job_output_dir = os.path.join(app.config['GENERATED_FOLDER'], job_id)
        if os.path.exists(job_output_dir):
            try:
                import shutil
                shutil.rmtree(job_output_dir)
            except OSError as e:
                print(f"Error removing job directory {job_output_dir}: {e}")
    
    return jsonify({
        'cleaned_jobs': len(jobs_to_remove),
        'cleaned_files': files_cleaned,
        'remaining_jobs': len(job_status_db)
    })

# --- Error Handlers ---
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

@app.errorhandler(413)
def too_large(error):
    return jsonify({'error': 'File too large'}), 413

# --- Enhanced Template Creation (Optional) ---
def create_enhanced_index_template():
    """Create an enhanced index.html template if it doesn't exist."""
    template_dir = os.path.join(os.path.dirname(__file__), 'templates')
    os.makedirs(template_dir, exist_ok=True)
    
    template_path = os.path.join(template_dir, 'index.html')
    
    if not os.path.exists(template_path):
        enhanced_template = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Enhanced PDF to HTML Converter</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f5f5f5; }
        .container { max-width: 800px; margin: 50px auto; padding: 20px; }
        .card { background: white; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); padding: 30px; }
        h1 { color: #333; margin-bottom: 10px; text-align: center; }
        .subtitle { text-align: center; color: #666; margin-bottom: 30px; }
        .form-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 5px; font-weight: 500; color: #333; }
        input, textarea, select { width: 100%; padding: 12px; border: 2px solid #ddd; border-radius: 5px; font-size: 14px; }
        input:focus, textarea:focus { border-color: #007bff; outline: none; }
        .file-input { border: 2px dashed #ddd; padding: 20px; text-align: center; border-radius: 5px; }
        .btn { background: #007bff; color: white; padding: 12px 30px; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; }
        .btn:hover { background: #0056b3; }
        .progress { display: none; margin-top: 20px; }
        .progress-bar { width: 100%; height: 20px; background: #f0f0f0; border-radius: 10px; overflow: hidden; }
        .progress-fill { height: 100%; background: #007bff; width: 0%; transition: width 0.3s; }
        .results { margin-top: 30px; display: none; }
        .file-result { padding: 10px; margin: 5px 0; border-radius: 5px; border-left: 4px solid #007bff; background: #f8f9fa; }
        .enhancement-note { background: #e7f3ff; border: 1px solid #007bff; border-radius: 5px; padding: 15px; margin-bottom: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <h1>🚀 Enhanced PDF to HTML Converter</h1>
            <p class="subtitle">Advanced conversion with improved layout preservation and Nepali text support</p>
            
            <div class="enhancement-note">
                <strong>✨ Enhanced Features:</strong>
                <ul style="margin-left: 20px; margin-top: 10px;">
                    <li>Better Nepali font rendering with Noto Sans Devanagari</li>
                    <li>Improved table structure preservation</li>
                    <li>Smart form field detection and styling</li>
                    <li>Enhanced typography and spacing</li>
                    <li>Print-ready and responsive design</li>
                </ul>
            </div>
            
            <form id="uploadForm" enctype="multipart/form-data">
                <div class="form-group">
                    <label for="prompt">Conversion Instructions:</label>
                    <textarea id="prompt" name="prompt" rows="3" placeholder="Enter specific instructions for the conversion process..." required>Convert this Nepali legal document to clean, semantic HTML while preserving the exact layout, formatting, and structure.</textarea>
                </div>
                
                <div class="form-group">
                    <label for="api_keys">API Keys (comma-separated, optional):</label>
                    <input type="text" id="api_keys" name="api_keys" placeholder="key1,key2,key3...">
                </div>
                
                <div class="form-group">
                    <label>Select PDF Files:</label>
                    <div class="file-input">
                        <input type="file" id="files" name="file" multiple accept=".pdf" required>
                        <p>Click to select PDF files or drag and drop them here</p>
                    </div>
                </div>
                
                <button type="submit" class="btn">🚀 Start Enhanced Conversion</button>
            </form>
            
            <div class="progress" id="progress">
                <h3>Processing...</h3>
                <div class="progress-bar">
                    <div class="progress-fill" id="progressFill"></div>
                </div>
                <p id="progressText">Preparing files...</p>
            </div>
            
            <div class="results" id="results">
                <h3>Results</h3>
                <div id="fileResults"></div>
                <button class="btn" id="downloadAll" style="display:none;">📦 Download All Files</button>
            </div>
        </div>
    </div>

    <script>
        let currentJobId = null;
        let pollInterval = null;

        document.getElementById('uploadForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const formData = new FormData(e.target);
            const progress = document.getElementById('progress');
            const results = document.getElementById('results');
            
            progress.style.display = 'block';
            results.style.display = 'none';
            
            try {
                const response = await fetch('/upload', {
                    method: 'POST',
                    body: formData
                });
                
                const data = await response.json();
                
                if (response.ok) {
                    currentJobId = data.job_id;
                    startPolling();
                } else {
                    alert('Error: ' + data.error);
                    progress.style.display = 'none';
                }
            } catch (error) {
                alert('Error uploading files: ' + error.message);
                progress.style.display = 'none';
            }
        });

        function startPolling() {
            if (pollInterval) clearInterval(pollInterval);
            
            pollInterval = setInterval(async () => {
                try {
                    const response = await fetch(`/status/${currentJobId}`);
                    const data = await response.json();
                    
                    updateProgress(data);
                    
                    if (data.all_done) {
                        clearInterval(pollInterval);
                        showResults(data);
                    }
                } catch (error) {
                    console.error('Polling error:', error);
                }
            }, 2000);
        }

        function updateProgress(data) {
            const progress = (data.stats.completed + data.stats.failed_or_split) / data.stats.total * 100;
            document.getElementById('progressFill').style.width = progress + '%';
            document.getElementById('progressText').textContent = 
                `Processing: ${data.stats.completed} completed, ${data.stats.processing} processing, ${data.stats.pending} pending`;
        }

        function showResults(data) {
            const progress = document.getElementById('progress');
            const results = document.getElementById('results');
            const fileResults = document.getElementById('fileResults');
            const downloadAll = document.getElementById('downloadAll');
            
            progress.style.display = 'none';
            results.style.display = 'block';
            
            fileResults.innerHTML = '';
            
            let hasCompletedFiles = false;
            
            data.files.forEach(file => {
                const div = document.createElement('div');
                div.className = 'file-result';
                
                let statusColor = '#6c757d';
                let statusText = file.status;
                let actions = '';
                
                if (file.status === 'completed') {
                    statusColor = '#28a745';
                    statusText = '✅ Completed';
                    actions = `
                        <a href="/download/${data.job_id}/${file.id}" class="btn" style="margin-right: 10px; padding: 5px 15px; font-size: 12px;">📁 Download</a>
                        <a href="/preview/${data.job_id}/${file.id}" target="_blank" class="btn" style="padding: 5px 15px; font-size: 12px; background: #17a2b8;">👁️ Preview</a>
                    `;
                    hasCompletedFiles = true;
                } else if (file.status === 'failed') {
                    statusColor = '#dc3545';
                    statusText = '❌ Failed';
                    if (file.error) {
                        statusText += ': ' + file.error;
                    }
                    if (file.can_split) {
                        actions = `<button onclick="splitFile('${data.job_id}', '${file.id}')" class="btn" style="padding: 5px 15px; font-size: 12px; background: #ffc107; color: #000;">✂️ Split & Retry</button>`;
                    }
                } else if (file.status === 'processing') {
                    statusColor = '#007bff';
                    statusText = '⏳ Processing...';
                }
                
                div.innerHTML = `
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <strong>${file.name}</strong>
                            <span style="color: ${statusColor}; margin-left: 10px;">${statusText}</span>
                            ${file.split_depth > 0 ? `<span style="color: #6c757d; font-size: 12px;"> (Depth: ${file.split_depth})</span>` : ''}
                        </div>
                        <div>${actions}</div>
                    </div>
                `;
                
                fileResults.appendChild(div);
            });
            
            if (hasCompletedFiles) {
                downloadAll.style.display = 'inline-block';
                downloadAll.onclick = () => window.location.href = `/download-all/${data.job_id}`;
            }
        }

        async function splitFile(jobId, fileId) {
            try {
                const response = await fetch(`/split-retry/${jobId}/${fileId}`, { method: 'POST' });
                const data = await response.json();
                
                if (response.ok) {
                    alert('File split successfully! Processing will resume automatically.');
                    startPolling(); // Resume polling
                } else {
                    alert('Error splitting file: ' + data.error);
                }
            } catch (error) {
                alert('Error: ' + error.message);
            }
        }
    </script>
</body>
</html>'''
        
        with open(template_path, 'w', encoding='utf-8') as f:
            f.write(enhanced_template)
        print(f"Created enhanced template at: {template_path}")

# --- Run the App ---
if __name__ == '__main__':
    print("Starting Enhanced Flask PDF to HTML Converter...")
    
    # Create enhanced template if it doesn't exist
    create_enhanced_index_template()
    
    print("✨ Enhanced Features Loaded:")
    print("  - Advanced PDF extraction with PyMuPDF and pdfplumber")
    print("  - Improved HTML generation with better CSS styling")
    print("  - Enhanced Nepali font support with Noto Sans Devanagari")
    print("  - Smart form field detection and conversion")
    print("  - Better table structure preservation")
    print("  - Print-ready and responsive design")
    print("  - Post-processing improvements")
    print("  - Enhanced error handling and auto-splitting")
    
    app.run(debug=True, host='0.0.0.0', port=5001)