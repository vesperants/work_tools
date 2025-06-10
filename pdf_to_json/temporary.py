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

# --- <<< NEW: Import and Initialize Flask-Executor >>> ---
from flask_executor import Executor

# --- Configuration ---
load_dotenv()

UPLOAD_FOLDER = 'uploads'
GENERATED_FOLDER = 'generated_json'
ALLOWED_EXTENSIONS = {'pdf'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['GENERATED_FOLDER'] = GENERATED_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 128 * 1024 * 1024 # Increase limit for multiple files
app.secret_key = os.getenv('FLASK_SECRET_KEY', os.urandom(24))

# --- <<< NEW: Configure Executor >>> ---
# Use 'thread' for ThreadPoolExecutor (simpler, shares memory, GIL applies)
# Use 'process' for ProcessPoolExecutor (true parallelism, more overhead, careful with shared state)
# app.config['EXECUTOR_TYPE'] = 'process'
app.config['EXECUTOR_TYPE'] = 'thread'
app.config['EXECUTOR_MAX_WORKERS'] = 5 # Adjust based on your server resources
executor = Executor(app)

# --- Gemini API Setup ---
# api_key = os.getenv("GOOGLE_API_KEY")
# api_key = 'AIzaSyCJJXEFZgl8nVtB4kdE6agWLmCLonbSKEA'
api_key = 'AIzaSyCtJqz3RXrInneBS4uoN0V0iw-w4usCAJs'
# api_key = 'AIzaSyAf6H9yCmR4y1esCTrw83emP0qrbKlgQgU'
# api_key = 'AIzaSyCaBg7D52E4ITIc6CM8LlBNKXj6XXCc80k'
if not api_key:
    raise ValueError("No GOOGLE_API_KEY found in .env")
GEMINI_MODEL_TO_USE = 'gemini-2.5-pro-exp-03-25'
print(f"--- Using Gemini Model: {GEMINI_MODEL_TO_USE} ---")
try:
    genai.configure(api_key=api_key)
except Exception as e:
    raise ValueError(f"Failed to configure Google Gemini API: {e}")

# Create necessary directories
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

# --- <<< NEW: Background Task Function >>> ---
def process_single_pdf(job_id, file_id, prompt, pdf_path, original_filename):
    """Task executed by the Executor to process one PDF."""
    print(f"[Job {job_id}, File {file_id}] Starting processing for: {original_filename}")

    # 1. Update status to 'processing'
    if job_id in job_status_db:
        for file_info in job_status_db[job_id]['files']:
            if file_info['id'] == file_id:
                file_info['status'] = 'processing'
                break

    gemini_file_object = None
    generated_json_path = None
    error_message = None

    try:
        # 2. Upload to Gemini
        print(f"[Job {job_id}, File {file_id}] Uploading to Gemini: {pdf_path}")
        gemini_file_object = genai.upload_file(
            path=pdf_path,
            display_name=f"{job_id}_{file_id}_{original_filename}", # Unique display name
            mime_type='application/pdf'
        )
        print(f"[Job {job_id}, File {file_id}] Uploaded as: {gemini_file_object.name}")

        # 3. Call Gemini API
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
        print(f"[Job {job_id}, File {file_id}] Sending request to Gemini...")
        response = model.generate_content(
            [full_gemini_prompt, gemini_file_object],
             request_options={"timeout": 600}
        )
        print(f"[Job {job_id}, File {file_id}] Received response.")
        raw_response_text = response.text # Add error checking as before if needed

        # 4. Process Response
        cleaned_json_string = clean_json_string(raw_response_text)
        if not cleaned_json_string:
            raise ValueError("Could not extract JSON structure from response.")

        # 5. Validate and Save JSON
        json_data = json.loads(cleaned_json_string)
        pretty_json_string = json.dumps(json_data, indent=4, ensure_ascii=False)

        # Create job-specific subdirectories if they don't exist
        job_json_dir = os.path.join(app.config['GENERATED_FOLDER'], job_id)
        os.makedirs(job_json_dir, exist_ok=True)

        base_filename = os.path.splitext(original_filename)[0]
        # Use file_id for uniqueness within the job
        json_filename = f"{file_id}_{base_filename}.json"
        generated_json_path = os.path.join(job_json_dir, json_filename)

        print(f"[Job {job_id}, File {file_id}] Saving JSON to: {generated_json_path}")
        with open(generated_json_path, 'w', encoding='utf-8') as f:
            f.write(pretty_json_string)
        print(f"[Job {job_id}, File {file_id}] JSON saved.")
        status = 'completed'

    except Exception as e:
        print(f"ERROR [Job {job_id}, File {file_id}]: Processing failed for {original_filename}: {e}")
        traceback.print_exc()
        error_message = str(e)
        status = 'failed'

    finally:
        # 6. Cleanup Gemini file
        if gemini_file_object:
            delete_gemini_file_safely(gemini_file_object)
        # 7. Cleanup local temporary PDF
        if pdf_path and os.path.exists(pdf_path):
            try:
                os.remove(pdf_path)
                print(f"[Job {job_id}, File {file_id}] Temp PDF deleted: {pdf_path}")
            except OSError as e:
                print(f"Error deleting temp PDF {pdf_path}: {e}")

        # 8. Update final status in the shared dictionary
        if job_id in job_status_db:
            for file_info in job_status_db[job_id]['files']:
                if file_info['id'] == file_id:
                    file_info['status'] = status
                    file_info['json_path'] = generated_json_path if status == 'completed' else None
                    file_info['error'] = error_message if status == 'failed' else None
                    break
        print(f"[Job {job_id}, File {file_id}] Finished processing. Status: {status}")

# --- <<< MODIFIED: Upload Route >>> ---
@app.route('/upload', methods=['POST'])
def upload_queue_files():
    """Receives multiple files and queues them for processing."""
    print("\n--- UPLOAD REQUEST START ---")
    prompt = request.form.get('prompt', '').strip()
    files = request.files.getlist('file') # Get list of files

    # --- Validation ---
    if not prompt:
        # Returning JSON error for fetch request
        return jsonify({"error": "Please provide a prompt."}), 400
    if not files or all(f.filename == '' for f in files):
        return jsonify({"error": "No files selected."}), 400

    valid_files_to_process = []
    for file in files:
        if file and allowed_file(file.filename):
            valid_files_to_process.append(file)
        elif file and file.filename != '':
            # Ignore disallowed files silently or return specific error
             print(f"Warning: Disallowed file type skipped: {file.filename}")
            # Optionally: return jsonify({"error": f"Invalid file type: {file.filename}"}), 400

    if not valid_files_to_process:
         return jsonify({"error": "No valid PDF files found in selection."}), 400

    # --- Job Creation ---
    job_id = uuid.uuid4().hex[:10] # Shorter job ID
    job_data = {'prompt': prompt, 'files': []}
    job_upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], job_id)
    os.makedirs(job_upload_dir, exist_ok=True) # Create job-specific upload dir

    print(f"Created Job ID: {job_id} with {len(valid_files_to_process)} files.")

    for index, file in enumerate(valid_files_to_process):
        original_filename = secure_filename(file.filename)
        file_id = f"file_{index}" # Simple file identifier within the job

        # Save file temporarily within the job's folder
        temp_pdf_filename = f"{file_id}_{original_filename}"
        pdf_path = os.path.join(job_upload_dir, temp_pdf_filename)

        try:
            file.save(pdf_path)
            print(f"Saved temp file: {pdf_path}")

            file_info = {
                'id': file_id,
                'original_name': original_filename,
                'pdf_path': pdf_path, # Path for the background task
                'status': 'pending',
                'json_path': None,
                'error': None
            }
            job_data['files'].append(file_info)

            # Submit task to executor
            executor.submit(process_single_pdf, job_id, file_id, prompt, pdf_path, original_filename)
            print(f"Submitted task for file {file_id}: {original_filename}")

        except Exception as e:
            print(f"Error saving or queuing file {original_filename}: {e}")
            # Handle error: Maybe skip this file or fail the whole job?
            # For now, just don't add it to the job_data to be processed
            if os.path.exists(pdf_path): os.remove(pdf_path) # Clean up if save failed mid-way

    if not job_data['files']: # Check if any files were successfully queued
        return jsonify({"error": "Failed to save or queue any of the uploaded files."}), 500

    job_status_db[job_id] = job_data
    print(f"Job {job_id} created and tasks submitted.")
    print("--- UPLOAD REQUEST END ---")

    # Return the Job ID to the client
    return jsonify({"job_id": job_id})

# --- <<< NEW: Status Route >>> ---
@app.route('/status/<job_id>', methods=['GET'])
def get_job_status(job_id):
    """Returns the status of all files within a job."""
    print(f"--- STATUS REQUEST for Job ID: {job_id} ---")
    job_info = job_status_db.get(job_id)
    if not job_info:
        return jsonify({"error": "Job not found"}), 404

    # Return only necessary info to the client (don't expose full paths)
    client_safe_files = []
    for f in job_info['files']:
        client_safe_files.append({
            'id': f['id'],
            'original_name': f['original_name'],
            'status': f['status'],
            'error': f['error']
            # Don't send json_path or pdf_path to client via status
        })

    return jsonify({"job_id": job_id, "files": client_safe_files})

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

    base_filename = os.path.splitext(file_to_download['original_name'])[0]
    download_name = f"{base_filename}_extracted.json"

    print(f"Sending file: {json_path} as {download_name}")
    try:
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