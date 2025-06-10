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
api_key = 'AIzaSyCWj5Dh2hLSgcrx_HSnQFeYD1hKdLeHwU0' # Ensure this key is still valid or use env var
# api_key = 'AIzaSyDNH-pa8RZe3SgBp8U_JJbA4clPfOxXwrE' # Ensure this key is still valid or use env var
# api_key = 'AIzaSyCtJqz3RXrInneBS4uoN0V0iw-w4usCAJs'
# api_key = 'AIzaSyCXufV68BV8bAgSZVWY-2a-LXv_ccf2eBw'
# api_key = 'AIzaSyAf6H9yCmR4y1esCTrw83emP0qrbKlgQgU'
# api_key = 'AIzaSyCaBg7D52E4ITIc6CM8LlBNKXj6XXCc80k'
if not api_key:
    raise ValueError("No GOOGLE_API_KEY found in .env or hardcoded")
GEMINI_MODEL_TO_USE = 'gemini-2.5-pro-preview-05-06'
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

def clean_json_string(raw_string):
    """Attempts to extract a valid JSON string from Gemini's response."""
    # (Keep the robust version from previous answers)
    if not isinstance(raw_string, str): return None
    text = raw_string.strip()
    # ... (full implementation of clean_json_string) ...
    json_block_start = text.find("```json")
    if json_block_start != -1:
        start_index = json_block_start + len("```json")
        end_index = text.rfind("```")
        if end_index > start_index:
            potential_json = text[start_index:end_index].strip()
            if potential_json.startswith(("{", "[")): return potential_json
    generic_block_start = text.find("```")
    if generic_block_start != -1:
        end_index = text.find("```", generic_block_start + 3)
        if end_index > generic_block_start:
            potential_json = text[generic_block_start + 3:end_index].strip()
            if potential_json.startswith(("{", "[")): return potential_json
    first_bracket = -1
    first_curly = text.find('{')
    first_square = text.find('[')
    if first_curly != -1 and first_square != -1: first_bracket = min(first_curly, first_square)
    elif first_curly != -1: first_bracket = first_curly
    elif first_square != -1: first_bracket = first_square
    if first_bracket != -1:
        last_curly = text.rfind('}')
        last_square = text.rfind(']')
        last_bracket = max(last_curly, last_square)
        if last_bracket > first_bracket:
            potential_json = text[first_bracket : last_bracket + 1]
            try: json.loads(potential_json); return potential_json
            except json.JSONDecodeError: pass
    if text.startswith(("{", "[")) and text.endswith(("}", "]")):
         try: json.loads(text); return text
         except json.JSONDecodeError: pass
    print("Warning: clean_json_string could not extract JSON.")
    return None

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
def process_single_pdf(job_id, file_id, prompt, pdf_path, original_filename):
    """Task executed by the Executor, respecting API rate limits and key rotation."""
    print(f"[Job {job_id}, File {file_id}] Starting processing for: {original_filename}")

    # --- Get Job Data --- 
    if job_id not in job_status_db:
        print(f"[Job {job_id}, File {file_id}] Error: Job not found.")
        return
    job_data = job_status_db[job_id]
    api_keys = job_data.get('api_keys', [])
    if not api_keys:
        api_keys = ['AIzaSyCtJqz3RXrInneBS4uoN0V0iw-w4usCAJs']
        job_data['api_keys'] = api_keys
        job_data['current_key_index'] = 0
        print(f"[Job {job_id}] Warning: No API keys found, using default.")

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
    generated_json_path = None
    error_message = None
    error_type = None
    status = 'failed'
    processed_successfully = False

    while not processed_successfully:
        # --- Key Selection ---
        current_key_index = job_data.get('current_key_index', 0)
        
        if current_key_index >= len(api_keys):
            print(f"[Job {job_id}, File {file_id}] All API keys have been tried and failed (likely quota/limit).")
            error_message = "All available API keys failed (quota/limit reached)."
            error_type = 'api_quota_exhausted'
            status = 'failed'
            break # Exit the main while loop

        current_api_key = api_keys[current_key_index]
        print(f"[Job {job_id}, File {file_id}] Attempting with API key index {current_key_index}")
        
        # --- API Call Attempt --- 
        try:
            # Configure Gemini with the current API key
            print(f"[Job {job_id}, File {file_id}] Configuring Gemini with API Key: {current_api_key}")
            genai.configure(api_key=current_api_key)
            
            # Upload to Gemini (only needs to be done once per file processing attempt)
            if gemini_file_object is None:
                print(f"[Job {job_id}, File {file_id}] Uploading to Gemini: {pdf_path}")
                gemini_file_object = genai.upload_file(
                    path=pdf_path,
                    display_name=f"{job_id}_{file_id}_{original_filename}",
                    mime_type='application/pdf'
                )
                print(f"[Job {job_id}, File {file_id}] Uploaded as: {gemini_file_object.name}")
            else:
                 print(f"[Job {job_id}, File {file_id}] Using existing Gemini file object: {gemini_file_object.name}")

            # Call Gemini API
            model = genai.GenerativeModel(model_name=GEMINI_MODEL_TO_USE)
            full_gemini_prompt = f"""
            **Task:** Analyze the attached PDF file ('{original_filename}') and extract information based on the user's request, formatting the output *strictly* as a valid JSON object.
            **User Request:**
            {prompt}
            **CRITICAL Instructions:** (Same detailed instructions as before)
            1. ...
            2. ...
            3. ...
            4. **Your entire response MUST be ONLY the JSON object.**
            5. ...
            6. Return JSON error object if needed: {{ "error": "..." }}
            """
            
            print(f"[Job {job_id}, File {file_id}] Sending request to Gemini with key index {current_key_index}...")
            response = model.generate_content(
                [full_gemini_prompt, gemini_file_object],
                request_options={"timeout": 600}
            )
            print(f"[Job {job_id}, File {file_id}] Received response.")
            raw_response_text = response.text

            # Process Response
            cleaned_json_string = clean_json_string(raw_response_text)
            if not cleaned_json_string:
                raise ValueError("Could not extract JSON structure from response.")

            # Create job-specific subdirectories (needed regardless of JSON validity)
            job_json_dir = os.path.join(app.config['GENERATED_FOLDER'], job_id)
            os.makedirs(job_json_dir, exist_ok=True)
            base_filename = os.path.splitext(original_filename)[0]
            json_filename = f"{file_id}_{base_filename}.json"
            generated_json_path = os.path.join(job_json_dir, json_filename)

            try:
                # Try to parse and validate the JSON
                json_data = json.loads(cleaned_json_string)
                pretty_json_string = json.dumps(json_data, indent=4, ensure_ascii=False)
                
                # Write the validated, pretty-printed JSON
                with open(generated_json_path, 'w', encoding='utf-8') as f:
                    f.write(pretty_json_string)
                print(f"[Job {job_id}, File {file_id}] Valid JSON saved to {generated_json_path}.")
                
                status = 'completed'
                error_message = None
                error_type = None
            except json.JSONDecodeError as json_err:
                # JSON parsing error - still save the raw response but mark as invalid
                print(f"[Job {job_id}, File {file_id}] JSON parsing error: {json_err}")
                
                # Save the raw cleaned string even though it has syntax errors
                with open(generated_json_path, 'w', encoding='utf-8') as f:
                    f.write(cleaned_json_string)
                print(f"[Job {job_id}, File {file_id}] Invalid JSON saved to {generated_json_path} for inspection.")
                
                # Mark as special error type but still provide download access
                status = 'completed'  # Still mark as completed so download is possible
                error_message = f"JSON syntax error (saved anyway): {str(json_err)}"
                error_type = 'json_syntax_error'
                
            processed_successfully = True # Exit the main while loop regardless

        except Exception as e:
            print(f"ERROR [Job {job_id}, File {file_id}, Key Index {current_key_index}]: Processing attempt failed: {e}")
            traceback.print_exc()
            error_message = str(e)
            status = 'failed'
            error_type = 'general_error' 

            # --- Error Analysis --- 
            error_lower = error_message.lower()
            is_quota_error = any(phrase in error_lower for phrase in [
                'quota exceeded', 'limit exceeded', 'rate limit', 'resource exhausted', 'api key invalid', '429'
            ])
            # Treat 'Could not extract JSON' as a potential size/complexity issue requiring split
            is_size_error = any(phrase in error_lower for phrase in [
                'too large', 'context length', 'token limit', 'capacity', 'could not extract json structure from response'
            ])

            if is_quota_error:
                print(f"[Job {job_id}, File {file_id}] Quota/Limit Error received from API with key index {current_key_index}. Moving to next key.")
                error_type = 'api_quota_error_retry'
                job_data['current_key_index'] = current_key_index + 1 # Move to the next key
            elif is_size_error:
                print(f"[Job {job_id}, File {file_id}] PDF too large or unprocessable error. Splitting may help. Failing this file.")
                error_type = 'pdf_too_large' # Keep this for split logic
            else:
                print(f"[Job {job_id}, File {file_id}] General processing error. Failing this file.")
                error_type = 'general_error'
            break # Exit the main while loop, file failed
        # No finally needed here as cleanup is outside the loop

    # --- End of Main While Loop --- 

    # --- Cleanup --- 
    if gemini_file_object:
        delete_gemini_file_safely(gemini_file_object)
    
    should_delete_pdf = (status == 'completed' or 
                         (status == 'failed' and error_type not in ['pdf_too_large', 'api_quota_exhausted']))
    
    if pdf_path and os.path.exists(pdf_path) and should_delete_pdf:
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
        file_info['json_path'] = generated_json_path if status == 'completed' else None
        file_info['error'] = error_message 
        file_info['error_type'] = error_type # Final error type reflects the outcome
        
        if 'pdf_path' in file_info and should_delete_pdf:
             file_info.pop('pdf_path', None)
             
    elif job_id not in job_status_db:
         print(f"[Job {job_id}, File {file_id}] Critical Error: Job data disappeared before final status update.")

    print(f"[Job {job_id}, File {file_id}] Finished processing task. Final Status: {status}, Final Error Type: {error_type}")

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
            'json_path': None,
            'error': None,
            'error_type': None
        })
        
        executor.submit(
            process_single_pdf,
            job_id,
            file_id,
            prompt,
            pdf_path,
            original_filename
        )
        
        print(f"Queued file for processing: {original_filename} with ID: {file_id}")

    return jsonify({
        "job_id": job_id,
        "num_files": len(valid_files_to_process),
        "message": f"Processing started for {len(valid_files_to_process)} files"
    })

# --- <<< NEW: Status Route >>> ---
@app.route('/status/<job_id>', methods=['GET'])
def get_job_status(job_id):
    """Return the current processing status for a job."""
    if job_id not in job_status_db:
        return jsonify({"error": "Job not found"}), 404

    job_data = job_status_db[job_id]
    
    # Calculate overall statistics
    total_files = len(job_data['files'])
    completed = sum(1 for file in job_data['files'] if file['status'] == 'completed')
    failed = sum(1 for file in job_data['files'] if file['status'] == 'failed')
    pending = sum(1 for file in job_data['files'] if file['status'] == 'pending')
    processing = sum(1 for file in job_data['files'] if file['status'] == 'processing')
    split = sum(1 for file in job_data['files'] if file['status'] == 'split')
    
    # Format file details for client
    file_details = []
    for file in job_data['files']:
        file_detail = {
            'id': file['id'],
            'name': file['original_name'],
            'status': file['status'],
            'can_download': file['status'] == 'completed',
            'error': file['error'] if 'error' in file and file['error'] else None,
            'error_type': file.get('error_type', None)  # Include error_type in response
        }
        
        # Add split option info if this is a 'pdf_too_large' error
        if file.get('error_type') == 'pdf_too_large' and 'pdf_path' in file and os.path.exists(file['pdf_path']):
            file_detail['can_split'] = True
        else:
            file_detail['can_split'] = False
            
        file_details.append(file_detail)
    
    return jsonify({
        'job_id': job_id,
        'prompt': job_data['prompt'],
        'stats': {
            'total': total_files,
            'completed': completed,
            'failed': failed,
            'pending': pending,
            'processing': processing,
            'split': split
        },
        'all_done': completed + failed + split == total_files,
        'files': file_details
    })

# --- <<< NEW: Download Route >>> ---
@app.route('/download/<job_id>/<file_id>', methods=['GET'])
def download_json_file(job_id, file_id):
    """Sends the generated JSON file for a specific completed file in a job."""
    print(f"--- DOWNLOAD REQUEST for Job ID: {job_id}, File ID: {file_id} ---")
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

    json_path = file_to_download.get('json_path')
    if not json_path or not os.path.exists(json_path):
        flash(f"Error: Generated JSON file for '{file_to_download['original_name']}' not found on server.", "error")
        print(f"ERROR: JSON path missing or file not found for Job {job_id}, File {file_id}. Path: {json_path}")
        return redirect(url_for('index')) # Or return 500

    # Get the original filename and create a download name with the same base name
    base_filename = os.path.splitext(file_to_download['original_name'])[0]
    download_name = f"{base_filename}.json"

    print(f"Sending file: {json_path} as {download_name}")
    try:
        # Send the file with an explicit download name and attachment disposition
        return send_file(
            json_path,
            as_attachment=True,
            download_name=download_name,
            mimetype='application/json'
        )
    except Exception as e:
         print(f"Error sending file {json_path}: {e}")
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
        if f['status'] == 'completed' and 'json_path' in f and f['json_path'] and os.path.exists(f['json_path']):
            completed_files.append({
                'path': f['json_path'],
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
                zip_arcname = f"{base_filename}.json" # Filename inside the zip
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
    """Split a large PDF into two halves and process each separately."""
    print(f"\n--- SPLIT AND RETRY REQUEST START for Job {job_id}, File {file_id} ---")
    
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
    job_status_db[job_id]['files'].append({
        'id': first_half_id,
        'original_name': split_result['first_half']['filename'],
        'pdf_path': split_result['first_half']['path'],
        'status': 'pending',
        'json_path': None,
        'error': None,
        'error_type': None
    })
    
    job_status_db[job_id]['files'].append({
        'id': second_half_id,
        'original_name': split_result['second_half']['filename'],
        'pdf_path': split_result['second_half']['path'],
        'status': 'pending',
        'json_path': None,
        'error': None,
        'error_type': None
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
        split_result['first_half']['filename']
    )
    
    executor.submit(
        process_single_pdf,
        job_id,
        second_half_id,
        prompt,
        split_result['second_half']['path'],
        split_result['second_half']['filename']
    )
    
    print(f"--- SPLIT AND RETRY REQUEST END: Successfully split PDF and queued {first_half_id} and {second_half_id} for processing ---")
    
    return jsonify({
        "success": True,
        "message": "PDF has been split and processing started",
        "parts": [first_half_id, second_half_id]
    })

# --- Root Route ---
@app.route('/', methods=['GET'])
def index():
    """Renders the main upload form."""
    # Clear out very old jobs? (Simple example doesn't do this)
    return render_template('index.html')

# --- Run the App ---
if __name__ == '__main__':
    print("Starting Flask development server...")
    app.run(debug=True, host='0.0.0.0', port=5001)