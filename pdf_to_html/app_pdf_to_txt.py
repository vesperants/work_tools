# app.py

import os
import uuid
import json
import google.generativeai as genai
from flask import Flask, request, render_template, send_file, flash, redirect, url_for, jsonify
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import time
import traceback
from concurrent.futures import ThreadPoolExecutor # Or ProcessPoolExecutor
import PyPDF2  # For PDF splitting
import threading # For rate limiting locks
from datetime import date, datetime # For daily limit tracking
import zipfile # For creating zip archives
import io      # For in-memory file handling

# --- <<< NEW: Import and Initialize Flask-Executor >>> ---
from flask_executor import Executor

# --- Configuration ---
load_dotenv()

# --- Rate Limiting (NEW) ---
MAX_RPM_PER_KEY = 10  # Requests per minute for free tier Gemini (adjust if different for your model/tier)
RPM_WINDOW_SECONDS = 60
# Stores {api_key: [timestamp1, timestamp2, ...]}
api_request_timestamps = {}
# Stores {api_key: threading.Lock()} for thread-safe access to timestamps
api_key_locks = {}

# --- Auto-Splitting Configuration (NEW) ---
MAX_SPLIT_DEPTH = 5 # Max number of times a file lineage can be split automatically

UPLOAD_FOLDER = 'uploads'
GENERATED_FOLDER = 'generated_json'
ALLOWED_EXTENSIONS = {'pdf'}

# --- <<< RE-INSERTED: Flask App Initialization and Config >>> ---
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['GENERATED_FOLDER'] = GENERATED_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024  # Increase limit for multiple files - accommodating up to ~300 files
app.secret_key = os.getenv('FLASK_SECRET_KEY', os.urandom(24))

# --- <<< RE-INSERTED: Configure Executor >>> ---
# Use 'thread' for ThreadPoolExecutor (simpler, shares memory, GIL applies)
# Use 'process' for ProcessPoolExecutor (true parallelism, more overhead, careful with shared state)
# app.config['EXECUTOR_TYPE'] = 'process'
app.config['EXECUTOR_TYPE'] = 'thread'
app.config['EXECUTOR_MAX_WORKERS'] = 5 # Adjust based on your server resources
executor = Executor(app)

# --- <<< RE-INSERTED: Gemini API Setup >>> ---
# api_key = os.getenv("GOOGLE_API_KEY")
# api_key = 'AIzaSyCEmJCupw0LeA8EqIdQIEL_NLJVjzza2Qw' # Ensure this key is still valid or use env var
api_key = 'AIzaSyCvlTVUdbAFLuARdxQXj9k979pSfA9uSSc' # Ensure this key is still valid or use env var
# api_key = 'AIzaSyDNH-pa8RZe3SgBp8U_JJbA4clPfOxXwrE' # Ensure this key is still valid or use env var
# api_key = 'AIzaSyCtJqz3RXrInneBS4uoN0V0iw-w4usCAJs'
# api_key = 'AIzaSyCXufV68BV8bAgSZVWY-2a-LXv_ccf2eBw'
# api_key = 'AIzaSyAf6H9yCmR4y1esCTrw83emP0qrbKlgQgU'
# api_key = 'AIzaSyCaBg7D52E4ITIc6CM8LlBNKXj6XXCc80k'
if not api_key:
    raise ValueError("No GOOGLE_API_KEY found in .env or hardcoded")
GEMINI_MODEL_TO_USE = 'gemini-2.5-flash-preview-05-20'
print(f"--- Using Gemini Model: {GEMINI_MODEL_TO_USE} ---")
try:
    genai.configure(api_key=api_key)
except Exception as e:
    raise ValueError(f"Failed to configure Google Gemini API: {e}")

# --- <<< RE-INSERTED: Create necessary directories >>> ---
try:
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(GENERATED_FOLDER, exist_ok=True)
except OSError as e:
    raise OSError(f"Could not create necessary directories: {e}")

# --- <<< NEW: Job Status Storage (In-Memory) >>> ---
# WARNING: This dictionary is lost if the server restarts!
# Structure: { 'job_id': {'prompt': '...', 'files': [{'id': ..., 'original_name': ..., 'pdf_path':..., 'status': 'pending/processing/completed/failed', 'json_path': ..., 'error': ...}, ...]} }
job_status_db = {}

# --- Helper Functions (allowed_file, clean_json_string, delete_gemini_file_safely - keep as before) ---
# (Include the functions from the previous app.py version here)
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
        return "" # Return empty string for non-string input

    text = raw_string.strip()
    content_to_clean = text # Default to the whole text

    start_tag = "<DOCUMENT_START>"
    end_tag = "<DOCUMENT_END>"

    start_index = text.find(start_tag)
    # Use rfind for the end_tag to get the last occurrence, in case of nested/malformed tags
    end_index = text.rfind(end_tag) 

    if start_index != -1 and end_index != -1 and start_index < end_index:
        # Both tags found and in correct order
        content_to_clean = text[start_index + len(start_tag) : end_index].strip()
    elif start_index != -1 and end_index == -1:
        # Start tag found, but no end tag (likely truncated or model didn't complete)
        content_to_clean = text[start_index + len(start_tag) :].strip()
        print(f"Warning: clean_text_output found '{start_tag}' but no '{end_tag}'. Processing content after start tag.")
    elif start_index == -1 and end_index != -1:
        # End tag found, but no start tag (unusual, could be model error)
        content_to_clean = text[:end_index].strip()
        print(f"Warning: clean_text_output found '{end_tag}' but no '{start_tag}'. Processing content before end tag.")
    # If neither tag is found, or if end_index is before start_index (e.g. "<END>...<START>"),
    # content_to_clean remains the original `text`.
    # The truncation/malformed checks in process_single_pdf will handle flagging these issues.

    # Now, clean markdown fences from the (potentially) extracted content
    final_cleaned_text = content_to_clean # Initialize with content after tag stripping
    patterns_to_check = [
        ("```text", "```"),
        ("```", "```")
    ]
    # Ensure we operate on a string before calling string methods
    if not isinstance(final_cleaned_text, str):
        final_cleaned_text = "" # Default to empty if it became non-string somehow

    for start_pattern, end_pattern in patterns_to_check:
        # Check if final_cleaned_text is not empty and is a string before proceeding
        if final_cleaned_text and final_cleaned_text.startswith(start_pattern) and final_cleaned_text.endswith(end_pattern):
            if start_pattern == end_pattern: # e.g. ```content```
                if final_cleaned_text.count(start_pattern) >= 2: # ensure there's a pair
                    first_occurrence = final_cleaned_text.find(start_pattern)
                    last_occurrence = final_cleaned_text.rfind(end_pattern)
                    if last_occurrence > first_occurrence + len(start_pattern) -1 :
                        final_cleaned_text = final_cleaned_text[first_occurrence + len(start_pattern) : last_occurrence].strip()
                        break 
            elif start_pattern != end_pattern: # e.g. ```text ... ```
                if len(final_cleaned_text) > len(start_pattern) + len(end_pattern):
                    final_cleaned_text = final_cleaned_text[len(start_pattern):-len(end_pattern)].strip()
                    break 
    
    return final_cleaned_text

def delete_gemini_file_safely(file_object):
    """Attempts to delete a file uploaded to Gemini and prints status."""
    # (Keep the robust version from previous answers)
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

# --- <<< NEW: PDF Splitting Function >>> ---
def split_pdf(pdf_path, original_filename):
    """
    Split a PDF file into two halves and save them separately.
    Returns a list of paths to the split PDF files.
    """
    try:
        print(f"Splitting PDF: {pdf_path}")
        # Get filename without extension
        base_name = os.path.splitext(original_filename)[0]
        
        # Create reader object
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            total_pages = len(pdf_reader.pages)
            
            if total_pages <= 2:
                print(f"PDF {pdf_path} has too few pages to split ({total_pages})")
                return None
                
            # Calculate middle page
            mid_point = total_pages // 2
            
            # Create two new PDF writers
            first_half_writer = PyPDF2.PdfWriter()
            second_half_writer = PyPDF2.PdfWriter()
            
            # Add pages to first half
            for page_num in range(mid_point):
                first_half_writer.add_page(pdf_reader.pages[page_num])
                
            # Add pages to second half
            for page_num in range(mid_point, total_pages):
                second_half_writer.add_page(pdf_reader.pages[page_num])
            
            # Create filenames for split PDFs
            first_half_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{base_name}_part1.pdf")
            second_half_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{base_name}_part2.pdf")
            
            # Write the split PDFs
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

# --- <<< NEW: Background Task Function >>> ---
def process_single_pdf(job_id, file_id, prompt, pdf_path, original_filename, current_split_depth=0):
    """Task executed by the Executor, respecting API rate limits and key rotation."""
    print(f"[Job {job_id}, File {file_id}, Depth {current_split_depth}] Starting processing for: {original_filename}")

    # --- Get Job Data --- 
    if job_id not in job_status_db:
        print(f"[Job {job_id}, File {file_id}] Error: Job not found.")
        return
    job_data = job_status_db[job_id]
    api_keys = job_data.get('api_keys', [])
    if not api_keys:
        # Use the global default if none in job_data (e.g., from older jobs or direct calls)
        api_keys = [os.getenv("GOOGLE_API_KEY")] if os.getenv("GOOGLE_API_KEY") else ['AIzaSyCtJqz3RXrInneBS4uoN0V0iw-w4usCAJs'] # Fallback
        job_data['api_keys'] = api_keys
        job_data['current_key_index'] = 0
        print(f"[Job {job_id}] Warning: No API keys found in job, using default/fallback.")

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

    gemini_file_object = None
    generated_text_path = None 
    error_message = None
    error_type = None
    status = 'failed' # Default status
    processed_successfully_this_attempt = False # Tracks if API call and basic processing succeeded in the loop

    while not processed_successfully_this_attempt: # Loop for API key rotation
        # --- Key Selection ---
        current_key_index = job_data.get('current_key_index', 0)
        
        if current_key_index >= len(api_keys):
            print(f"[Job {job_id}, File {file_id}] All API keys have been tried and failed (likely quota/limit).")
            error_message = "All available API keys failed (quota/limit reached)."
            error_type = 'api_quota_exhausted'
            status = 'failed'
            break # Exit the API key retry loop

        current_api_key = api_keys[current_key_index]
        print(f"[Job {job_id}, File {file_id}, Depth {current_split_depth}] Attempting with API key index {current_key_index} (...{current_api_key[-4:]})")
        
        try:
            # Configure Gemini 
            genai.configure(api_key=current_api_key)
            
            if gemini_file_object is None: # Upload only once per process_single_pdf call
                print(f"[Job {job_id}, File {file_id}] Uploading to Gemini: {pdf_path}")
                gemini_file_object = genai.upload_file(
                    path=pdf_path,
                    display_name=f"{job_id}_{file_id}_{original_filename}",
                    mime_type='application/pdf'
                )
                print(f"[Job {job_id}, File {file_id}] Uploaded as: {gemini_file_object.name}")

            # Define Gemini Prompt (using the user's latest version)
            gemini_system_prompt = f"""Role: Act as a text extraction specialist with expertise in processing Nepali legal documents and maintaining document structure and completeness.
Task: Convert the provided PDF content from the file '{original_filename}' into clean, structured plain text format while preserving the document's logical flow and hierarchy.
Input: Plain text content extracted from a Nepali legal PDF document. Be aware that the extraction process might introduce artifacts such as:

Incorrect line breaks and lost formatting
Page numbers scattered throughout the text
Repeated headers, footers, or watermarks
OCR-related errors or inconsistencies

Output Requirements:

Clean Text Format: Produce well-formatted plain text that maintains readability
Structure Preservation: Maintain the logical hierarchy using:

Clear section breaks (using line spacing)
Proper indentation for subsections
Sequential numbering preservation (१, २, क, ख, etc.)


Content Completeness: Include ALL meaningful text content from the original document
Artifact Handling:

Remove page numbers
Remove repeated headers/footers/watermarks (keep only one instance if needed)
Fix obvious line break issues
Combine fragmented sentences



Formatting Guidelines:

Use consistent spacing between sections
Maintain original numbering schemes
Preserve titles and headings with appropriate emphasis (using line spacing/indentation)
Ensure paragraphs flow naturally
Keep related content grouped together

Output Format:

Start your output with: <DOCUMENT_START>
Include the clean, structured plain text that accurately represents the original document's content and organization
End your output with: <DOCUMENT_END>
"""
            
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
            print(f"[Job {job_id}, File {file_id}] Sending request to Gemini with key ...{current_api_key[-4:]}...")
            response = model.generate_content(
                [gemini_system_prompt, gemini_file_object],
                request_options={"timeout": 600} 
            )
            raw_response_text = response.text
            
            # --- Tag-Based Completion Check ---
            raw_text_stripped = raw_response_text.strip()
            is_complete = raw_text_stripped.startswith("<DOCUMENT_START>") and raw_text_stripped.endswith("<DOCUMENT_END>")
            
            # Save the (potentially incomplete) text first
            cleaned_text_output = clean_text_output(raw_response_text)
            job_output_dir = os.path.join(app.config['GENERATED_FOLDER'], job_id)
            os.makedirs(job_output_dir, exist_ok=True)
            base_filename = os.path.splitext(original_filename)[0]
            text_filename = f"{file_id}_{base_filename}_depth{current_split_depth}.txt" # Add depth to filename
            generated_text_path = os.path.join(job_output_dir, text_filename)
            
            try:
                with open(generated_text_path, 'w', encoding='utf-8') as f:
                    f.write(cleaned_text_output)
                print(f"[Job {job_id}, File {file_id}] Text (complete: {is_complete}) saved to {generated_text_path}.")
            except IOError as io_err:
                print(f"[Job {job_id}, File {file_id}] File saving error: {io_err}")
                # This is a critical error for this attempt, try next API key or fail file.
                error_message = f"Failed to save text file: {str(io_err)}"
                error_type = 'file_save_error'
                status = 'failed' 
                # Don't set processed_successfully_this_attempt = True, let API key loop continue or fail out.
                job_data['current_key_index'] = current_key_index + 1 # Try next key for file save error
                continue # To next iteration of API key retry loop


            if is_complete:
                print(f"[Job {job_id}, File {file_id}] Output is complete based on tags.")
                status = 'completed'
                error_message = None
                error_type = None
                processed_successfully_this_attempt = True # Success for this API key, exit loop.
            else: # Output is incomplete
                print(f"[Job {job_id}, File {file_id}, Depth {current_split_depth}] Output incomplete based on tags.")
                if current_split_depth < MAX_SPLIT_DEPTH:
                    print(f"[Job {job_id}, File {file_id}] Attempting auto-split (depth {current_split_depth} < {MAX_SPLIT_DEPTH}).")
                    # Update current file's status before attempting to split and queue children
                    if job_id in job_status_db and file_index != -1:
                        file_info = job_status_db[job_id]['files'][file_index]
                        file_info['status'] = 'failed' # Parent is "failed" as it's being split
                        file_info['error'] = "Output incomplete, auto-splitting and retrying with smaller parts."
                        file_info['error_type'] = 'auto_split_incomplete_retrying'
                        file_info['text_path'] = generated_text_path # Save path to the incomplete text

                    split_result = split_pdf(pdf_path, original_filename)
                    if split_result:
                        print(f"[Job {job_id}, File {file_id}] PDF split successfully. Queuing parts.")
                        # Get prompt and api_keys from parent job_data for children
                        parent_prompt = job_data.get('prompt', '')
                        
                        # Queue first half
                        first_half_id = f"{file_id}_p1_d{current_split_depth+1}"
                        job_status_db[job_id]['files'].append({
                            'id': first_half_id, 'original_name': split_result['first_half']['filename'],
                            'pdf_path': split_result['first_half']['path'], 'status': 'pending',
                            'text_path': None, 'error': None, 'error_type': None,
                            'split_depth': current_split_depth + 1
                        })
                        executor.submit(process_single_pdf, job_id, first_half_id, parent_prompt,
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
                        executor.submit(process_single_pdf, job_id, second_half_id, parent_prompt,
                                        split_result['second_half']['path'], split_result['second_half']['filename'],
                                        current_split_depth + 1)
                        
                        # Parent PDF (pdf_path) will be deleted in the cleanup phase of *this* function call
                        # as it's been successfully processed into children.
                        # The error_type 'auto_split_incomplete_retrying' signals this.
                        if gemini_file_object: delete_gemini_file_safely(gemini_file_object) # Clean up Gemini upload for parent
                        
                        # Delete the parent's local PDF copy now that children are queued.
                        if pdf_path and os.path.exists(pdf_path):
                            try:
                                os.remove(pdf_path)
                                print(f"[Job {job_id}, File {file_id}] Parent PDF {pdf_path} deleted after auto-splitting.")
                                # Remove pdf_path from parent's file_info as it's gone
                                if job_id in job_status_db and file_index != -1:
                                     job_status_db[job_id]['files'][file_index].pop('pdf_path', None)
                            except OSError as e:
                                print(f"Error deleting parent PDF {pdf_path} after auto-split: {e}")

                        return # IMPORTANT: Exit process_single_pdf for this parent file

                    else: # split_pdf failed
                        print(f"[Job {job_id}, File {file_id}] Auto-split failed (e.g., PDF too small). Marking as failed.")
                        status = 'failed'
                        error_message = "Output incomplete, and auto-split failed (PDF too small or corrupted)."
                        error_type = 'auto_split_pdf_error'
                        # PDF will be kept by default cleanup logic for 'failed' status if not 'auto_split_incomplete_retrying'
                        processed_successfully_this_attempt = True # This attempt is done, exit API key loop.
                
                else: # current_split_depth >= MAX_SPLIT_DEPTH
                    print(f"[Job {job_id}, File {file_id}] Output incomplete and max split depth ({MAX_SPLIT_DEPTH}) reached.")
                    status = 'failed'
                    error_message = f"Output incomplete after reaching max split depth ({MAX_SPLIT_DEPTH}). Manual review needed."
                    error_type = 'incomplete_max_splits'
                    # PDF will be kept by default cleanup logic
                    processed_successfully_this_attempt = True # This attempt is done, exit API key loop.

        except Exception as e:
            print(f"ERROR [Job {job_id}, File {file_id}, Depth {current_split_depth}, Key ...{current_api_key[-4:]}]: Processing attempt failed: {e}")
            traceback.print_exc()
            error_message = str(e)
            status = 'failed'
            # Default error_type if not more specific
            error_type = 'general_api_error' 

            error_lower = error_message.lower()
            is_quota_error = any(phrase in error_lower for phrase in [
                'quota exceeded', 'limit exceeded', 'rate limit', 'resource exhausted', 'api key invalid', '429'
            ])
            # is_size_error - this was for Gemini indicating size issues. With auto-split, less critical here.
            # We rely on tag check or split_pdf failure for size issues now.

            if is_quota_error:
                print(f"[Job {job_id}, File {file_id}] Quota/Limit Error. Moving to next key.")
                error_type = 'api_quota_error_retry'
                job_data['current_key_index'] = current_key_index + 1 
                # Continue to next iteration of API key retry loop for this file
            else:
                # For other general API errors, don't retry with another key for this file, just fail it.
                print(f"[Job {job_id}, File {file_id}] General API error. Failing this file for this attempt.")
                processed_successfully_this_attempt = True # Mark as "processed" to exit API key loop, status is 'failed'
        # No finally needed here as cleanup is outside the loop and also handled if auto-split returns early.

    # --- End of API Key Retry Loop --- 

    # --- Cleanup for this file attempt (if not returned early due to auto-split) --- 
    if gemini_file_object:
        delete_gemini_file_safely(gemini_file_object)
    
    # PDF Deletion Logic:
    # - If auto_split_incomplete_retrying: parent PDF was already deleted.
    # - If status is 'completed': delete local PDF.
    # - If status is 'failed' AND error_type is 'incomplete_max_splits' or 'auto_split_pdf_error' or 'api_quota_exhausted': KEEP PDF.
    # - For other 'failed' statuses (like general_api_error, file_save_error): delete local PDF.
    
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
    elif pdf_path and os.path.exists(pdf_path): # If not deleted, log why
        print(f"[Job {job_id}, File {file_id}] Keeping temporary PDF: {pdf_path} (Status: {status}, Error Type: {error_type})")

    # --- Update Final Status in DB for this file_id --- 
    # This block is reached if the file completed, failed terminally at this depth, or all API keys were exhausted.
    # If auto-split happened, the parent's status was updated before returning.
    if job_id in job_status_db and file_index != -1:
        file_info = job_status_db[job_id]['files'][file_index]
        file_info['status'] = status
        # generated_text_path was set when text was saved, regardless of completeness for record-keeping
        file_info['text_path'] = generated_text_path if generated_text_path and os.path.exists(generated_text_path) else file_info.get('text_path')
        file_info['error'] = error_message 
        file_info['error_type'] = error_type 
        
        if should_delete_this_pdf: # If PDF was deleted, remove path from record
             file_info.pop('pdf_path', None)
             
    elif job_id not in job_status_db:
         print(f"[Job {job_id}, File {file_id}] Critical Error: Job data disappeared before final status update.")

    print(f"[Job {job_id}, File {file_id}, Depth {current_split_depth}] Finished processing task. Final Status: {status}, Final Error Type: {error_type}")

# --- <<< MODIFIED: Upload Route >>> ---
@app.route('/upload', methods=['POST'])
def upload_queue_files():
    """Receives multiple files and queues them for processing."""
    print("\n--- UPLOAD REQUEST START ---")
    prompt = request.form.get('prompt', '').strip()
    api_keys_str = request.form.get('api_keys', '').strip()
    files = request.files.getlist('file') # Get list of files

    # --- Validation ---
    if not prompt:
        return jsonify({"error": "Please provide a prompt."}), 400
    if not files or all(f.filename == '' for f in files):
        return jsonify({"error": "No files selected."}), 400

    # Parse API keys
    api_keys = [key.strip() for key in api_keys_str.split(',') if key.strip()]
    if not api_keys:
        api_keys = [api_key]  # Default API key if none provided
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
        'api_keys': api_keys,          # Store the list of keys
        'current_key_index': 0,      # Start with the first key
        'files': [],
        'timestamp': time.time()
    }
    
    print(f"Created new job: {job_id} with {len(api_keys)} key(s) and prompt: {prompt}")

    # --- Process Each Valid File ---
    for file in valid_files_to_process:
        file_id = str(uuid.uuid4())
        # Temporarily disable secure_filename to test if it causes truncation
        # original_filename = secure_filename(file.filename)
        original_filename = file.filename # Use raw filename (Use with caution!)
        
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{file_id}_{original_filename}")
        # Ensure the combined path doesn't become too long or invalid
        try:
            file.save(pdf_path)
        except Exception as e:
            print(f"Error saving file {original_filename} to {pdf_path}: {e}")
            print(f"Skipping file due to save error.")
            continue # Skip this file if saving fails
        
        job_status_db[job_id]['files'].append({
            'id': file_id,
            'original_name': original_filename,
            'pdf_path': pdf_path,
            'status': 'pending',
            'text_path': None,
            'error': None,
            'error_type': None,
            'split_depth': 0  # Initialize split_depth
        })
        
        executor.submit(
            process_single_pdf,
            job_id,
            file_id,
            prompt,
            pdf_path,
            original_filename,
            0  # Pass initial split_depth
        )
        
        print(f"Queued file for processing: {original_filename} with ID: {file_id} at depth 0")

    return jsonify({
        "job_id": job_id,
        "num_files": len(valid_files_to_process),
        "message": f"Processing started for {len(valid_files_to_process)} files"
    })

# --- <<< MODIFIED: get_job_status Route (example of adding split_depth and adjusting can_split) >>> ---
@app.route('/status/<job_id>', methods=['GET'])
def get_job_status(job_id):
    """Return the current processing status for a job."""
    if job_id not in job_status_db:
        return jsonify({"error": "Job not found"}), 404

    job_data = job_status_db[job_id]
    
    total_files = len(job_data['files'])
    completed = sum(1 for file in job_data['files'] if file['status'] == 'completed')
    # "failed" now includes those that were auto-split and delegated
    failed_or_split = sum(1 for file in job_data['files'] if file['status'] == 'failed' or file.get('error_type') == 'auto_split_incomplete_retrying')
    pending = sum(1 for file in job_data['files'] if file['status'] == 'pending')
    processing = sum(1 for file in job_data['files'] if file['status'] == 'processing')
    # 'split' status was for manual split parent, 'auto_split_incomplete_retrying' is for auto-split parent.
    
    file_details = []
    for file_info in job_data['files']: # Renamed to file_info to avoid conflict
        file_detail = {
            'id': file_info['id'],
            'name': file_info['original_name'],
            'status': file_info['status'],
            'can_download': file_info['status'] == 'completed',
            'error': file_info.get('error'),
            'error_type': file_info.get('error_type'),
            'split_depth': file_info.get('split_depth', 0) 
        }
        
        # Conditions for allowing MANUAL split and retry from UI
        manual_split_eligible_error_types = [
            'pdf_too_large', # If initial upload is too big (can add pre-check later)
            'incomplete_max_splits', # Reached max auto-splits, but user might want to try more
            'auto_split_pdf_error',  # Auto-split failed, user might want to try manually
            'api_quota_exhausted'    # If user wants to retry after quota reset
            # 'output_missing_end_tag', 'output_malformed_tags' - These are now handled by auto-split
        ]
        
        if file_info.get('error_type') in manual_split_eligible_error_types and \
           'pdf_path' in file_info and file_info['pdf_path'] and os.path.exists(file_info['pdf_path']):
            file_detail['can_split'] = True
        else:
            file_detail['can_split'] = False
            
        file_details.append(file_detail)
    
    # Recalculate 'all_done' based on statuses that mean no more processing for that specific file entry
    # 'pending' and 'processing' are active. 'completed' and 'failed' (with various error_types) are terminal *for that entry*.
    # If a file was auto-split ('auto_split_incomplete_retrying'), its own processing is done.
    terminal_statuses_count = sum(1 for f in job_data['files'] if f['status'] in ['completed', 'failed'])

    return jsonify({
        'job_id': job_id,
        'prompt': job_data['prompt'],
        'stats': {
            'total': total_files,
            'completed': completed,
            'failed_or_split': failed_or_split, # Sum of 'failed' status entries
            'pending': pending,
            'processing': processing
        },
        'all_done': terminal_statuses_count == total_files, # All entries have reached a terminal state
        'files': file_details
    })

# --- <<< NEW: Download Route >>> ---
@app.route('/download/<job_id>/<file_id>', methods=['GET'])
def download_text_file(job_id, file_id):
    """Sends the generated TXT file for a specific completed file in a job."""
    print(f"--- DOWNLOAD REQUEST for Job ID: {job_id}, File ID: {file_id} (expecting TXT) ---")
    job_info = job_status_db.get(job_id)
    if not job_info:
        flash("Job not found.", "error")
        return redirect(url_for('index')) # Or return 404

    file_to_download = None
    for f in job_info['files']:
        if f['id'] == file_id:
            file_to_download = f
            break

    if not file_to_download:
        flash(f"File '{file_id}' not found in job '{job_id}'.", "error")
        return redirect(url_for('index')) # Or return 404

    if file_to_download['status'] != 'completed':
        flash(f"File '{file_to_download['original_name']}' is not yet completed or failed.", "warning")
        return redirect(url_for('index')) # Or return error

    output_path = file_to_download.get('text_path')
    if not output_path or not os.path.exists(output_path):
        flash(f"Error: Generated TXT file for '{file_to_download['original_name']}' not found on server.", "error")
        print(f"ERROR: TXT path missing or file not found for Job {job_id}, File {file_id}. Path: {output_path}")
        return redirect(url_for('index')) # Or return 500

    # Get the original filename and create a download name with the same base name but .txt extension
    base_filename = os.path.splitext(file_to_download['original_name'])[0]
    download_name = f"{base_filename}.txt" # Changed to .txt

    print(f"Sending file: {output_path} as {download_name}")
    try:
        # Send the file with an explicit download name and attachment disposition
        return send_file(
            output_path,
            as_attachment=True,
            download_name=download_name,
            mimetype='text/plain' # Changed to text/plain
        )
    except Exception as e:
         print(f"Error sending file {output_path}: {e}")
         flash(f"Error occurred while trying to send the file.", "error")
         return redirect(url_for('index'))

# --- <<< NEW: Download All Route >>> ---
@app.route('/download-all/<job_id>', methods=['GET'])
def download_all_job_files(job_id):
    """Finds all completed JSON files for a job and sends them as a zip archive."""
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
                'original_name': f['original_name'] # Use the original PDF name as basis
            })

    if not completed_files:
        flash("No completed files found to download for this job.", "warning")
        return redirect(url_for('index'))

    # Create zip file in memory
    memory_file = io.BytesIO()
    try:
        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            for file_to_zip in completed_files:
                # Construct the filename to use inside the zip archive
                base_filename = os.path.splitext(file_to_zip['original_name'])[0]
                zip_arcname = f"{base_filename}.txt" # Filename inside the zip, changed to .txt
                print(f"Adding {file_to_zip['path']} to zip as {zip_arcname}")
                zf.write(file_to_zip['path'], arcname=zip_arcname)
    except Exception as e:
        print(f"Error creating zip file for job {job_id}: {e}")
        traceback.print_exc()
        flash("Error creating zip archive.", "error")
        return redirect(url_for('index'))

    memory_file.seek(0) # Rewind the buffer to the beginning

    # Define the download name for the zip file itself
    zip_download_name = f"job_{job_id}_results.zip"
    print(f"Sending zip file: {zip_download_name}")

    return send_file(
        memory_file,
        mimetype='application/zip',
        as_attachment=True,
        download_name=zip_download_name
    )

# --- <<< NEW: Split PDF and Retry Route >>> ---
@app.route('/split-retry/<job_id>/<file_id>', methods=['POST'])
def split_and_retry(job_id, file_id):
    """Split a large PDF into two halves and process each separately (manual trigger)."""
    print(f"\n--- MANUAL SPLIT AND RETRY REQUEST START for Job {job_id}, File {file_id} ---")
    
    # Verify job and file exist
    if job_id not in job_status_db:
        return jsonify({"error": "Job not found"}), 404
    
    # Find the file info
    file_info = None
    for f in job_status_db[job_id]['files']:
        if f['id'] == file_id:
            file_info = f
            break
    
    if not file_info:
        return jsonify({"error": "File not found in job"}), 404
    
    # Check if file has the right error and the PDF is still available
    if file_info.get('error_type') != 'pdf_too_large' or 'pdf_path' not in file_info:
        return jsonify({"error": "This file cannot be split for retry. Either it's not a size-related error or the original PDF is no longer available."}), 400
    
    # Get original path and filename
    original_pdf_path = file_info['pdf_path']
    original_filename = file_info['original_name']
    
    if not os.path.exists(original_pdf_path):
        return jsonify({"error": "Original PDF no longer exists on the server"}), 400
    
    # Get the prompt from the job
    prompt = job_status_db[job_id].get('prompt', '')
    
    # Split the PDF
    split_result = split_pdf(original_pdf_path, original_filename)
    
    if not split_result:
        return jsonify({"error": "Failed to split the PDF. It may be too small or corrupted."}), 500
    
    # Create two new file entries for the split PDFs
    first_half_id = f"{file_id}_part1"
    second_half_id = f"{file_id}_part2"
    
    # Add new files to the job
    # For manually split parts, let's reset their depth or set to parent_depth +1.
    # For simplicity of manual override, let's try resetting to 0.
    # Alternatively, find parent depth:
    parent_split_depth = file_info.get('split_depth', -1) # default to -1 if not found
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
    
    # Update original file status to indicate it was split
    file_info['status'] = 'split'
    file_info['error'] = "PDF was split into two parts for processing"
    file_info['error_type'] = 'split_for_retry'
    
    # Start processing the split PDFs
    # Note: The process_single_pdf function will now use the job's API key
    executor.submit(
        process_single_pdf,
        job_id,
        first_half_id,
        prompt,
        split_result['first_half']['path'],
        split_result['first_half']['filename'],
        new_parts_depth # Pass new depth
    )
    
    executor.submit(
        process_single_pdf,
        job_id,
        second_half_id,
        prompt,
        split_result['second_half']['path'],
        split_result['second_half']['filename'],
        new_parts_depth # Pass new depth
    )
    
    print(f"--- MANUAL SPLIT AND RETRY REQUEST END: Successfully split PDF and queued {first_half_id} (depth {new_parts_depth}) and {second_half_id} (depth {new_parts_depth}) for processing ---")
    
    return jsonify({
        "success": True,
        "message": "PDF has been split and processing started",
        "parts": [first_half_id, second_half_id]
    })

# --- Root Route ---
@app.route('/', methods=['GET'])
def index():
    """Renders the main upload form."""
    # The 'prompt' field in index.html will still be sent to the backend,
    # and stored in job_status_db[job_id]['prompt'].
    # However, the core Gemini call in process_single_pdf now uses the fixed, detailed prompt.
    # The UI prompt could be used for other metadata or if different processing modes were added later.
    return render_template('index.html')

# --- Run the App ---
if __name__ == '__main__':
    print("Starting Flask development server...")
    app.run(debug=True, host='0.0.0.0', port=5001)