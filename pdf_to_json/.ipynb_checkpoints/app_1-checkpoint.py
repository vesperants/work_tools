# app.py

import os
import uuid
import json
import google.generativeai as genai
from flask import Flask, request, render_template, send_file, flash, redirect, url_for, Response
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import time
import traceback # For detailed error logging

# --- Configuration ---
load_dotenv()  # Load environment variables from .env file

UPLOAD_FOLDER = 'uploads'
GENERATED_FOLDER = 'generated_json'
ALLOWED_EXTENSIONS = {'pdf'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['GENERATED_FOLDER'] = GENERATED_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024  # 32 MB upload limit (adjust as needed)
# It's better practice to set this in .env or system environment
app.secret_key = os.getenv('FLASK_SECRET_KEY', os.urandom(24))

# --- Gemini API Setup ---
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise ValueError("No GOOGLE_API_KEY found. Please set it in the .env file.")

# --- Load Gemini Model Name from environment variable ---
# Provide a sensible default if the variable is not set in .env
GEMINI_MODEL_TO_USE = 'gemini-2.5-pro-exp-03-25'
print(f"--- Using Gemini Model: {GEMINI_MODEL_TO_USE} ---") # Log the model being used

try:
    genai.configure(api_key=api_key)
except Exception as e:
    raise ValueError(f"Failed to configure Google Gemini API: {e}")

# Create necessary directories if they don't exist
try:
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(GENERATED_FOLDER, exist_ok=True)
except OSError as e:
    raise OSError(f"Could not create necessary directories: {e}")


# --- Helper Functions ---
def allowed_file(filename):
    """Checks if the file extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def clean_json_string(raw_string):
    """
    Attempts to extract a valid JSON string from Gemini's response.
    Handles potential markdown code fences (```json ... ```) and searches
    for the first '{' and last '}' as a fallback.
    Returns the cleaned string or None if no likely JSON is found.
    """
    if not isinstance(raw_string, str):
        print("Warning: Input to clean_json_string is not a string.")
        return None

    text = raw_string.strip()
    print(f"DEBUG: clean_json_string received input of length {len(text)}")

    # 1. Check for JSON within ```json ... ```
    json_block_start = text.find("```json")
    if json_block_start != -1:
        start_index = json_block_start + len("```json")
        end_index = text.rfind("```")
        if end_index > start_index:
            potential_json = text[start_index:end_index].strip()
            if potential_json.startswith(("{", "[")):
                print("DEBUG: Found JSON within ```json block.")
                return potential_json
            else:
                 print("DEBUG: Found ```json block, but content doesn't start with { or [.")

    # 2. Check for JSON within ``` ... ``` (no language specified)
    generic_block_start = text.find("```")
    if generic_block_start != -1:
        end_index = text.find("```", generic_block_start + 3)
        if end_index > generic_block_start:
            potential_json = text[generic_block_start + 3:end_index].strip()
            if potential_json.startswith(("{", "[")):
                 print("DEBUG: Found JSON within generic ``` block.")
                 return potential_json
            else:
                print("DEBUG: Found generic ``` block, but content doesn't start with { or [.")


    # 3. Find the first '{' or '[' and the last '}' or ']'
    first_bracket = -1
    first_curly = text.find('{')
    first_square = text.find('[')

    if first_curly != -1 and first_square != -1:
        first_bracket = min(first_curly, first_square)
    elif first_curly != -1:
        first_bracket = first_curly
    elif first_square != -1:
        first_bracket = first_square
    else:
        print("DEBUG: No starting { or [ found.")


    if first_bracket != -1:
        last_curly = text.rfind('}')
        last_square = text.rfind(']')
        last_bracket = max(last_curly, last_square)

        if last_bracket > first_bracket:
            potential_json = text[first_bracket : last_bracket + 1]
            # Attempt a quick parse to see if it's likely JSON
            try:
                json.loads(potential_json)
                print("DEBUG: Found JSON by locating first/last brackets/curlies and validating.")
                return potential_json
            except json.JSONDecodeError:
                print("DEBUG: String between first/last brackets wasn't valid JSON, continuing search.")
                pass # It might be part of surrounding text
        else:
            print("DEBUG: Found starting bracket, but no corresponding ending bracket found later.")


    # 4. If the entire string starts with { or [, assume it might be JSON
    if text.startswith(("{", "[")) and text.endswith(("}", "]")):
         # Add a validation check here too
         try:
            json.loads(text)
            print("DEBUG: Assuming the entire response might be JSON and it validated.")
            return text
         except json.JSONDecodeError:
            print("DEBUG: Entire response starts/ends like JSON but failed validation.")


    # 5. If nothing else worked, return None
    print("Warning: Could not confidently extract JSON from the response.")
    return None

def delete_gemini_file_safely(file_object):
    """Attempts to delete a file uploaded to Gemini and prints status."""
    print(f"DEBUG: Entering delete_gemini_file_safely for: {file_object.name if file_object and hasattr(file_object, 'name') else 'None'}")
    if file_object and hasattr(file_object, 'name'):
        try:
            print(f"Attempting to delete temporary Gemini file: {file_object.name}")
            # Add a timeout? The client library might handle this internally.
            genai.delete_file(file_object.name)
            print(f"Successfully deleted temporary Gemini file: {file_object.name}")
            print("DEBUG: Exiting delete_gemini_file_safely (Success)")
            return True
        except Exception as delete_err:
            print(f"Warning: Could not delete temporary Gemini file {file_object.name}: {delete_err}")
            traceback.print_exc() # Print stack trace for deletion errors
            print("DEBUG: Exiting delete_gemini_file_safely (Failure)")
            return False
    else:
        print("Info: No valid Gemini file object provided for deletion (might not have been created or already handled).")
        print("DEBUG: Exiting delete_gemini_file_safely (No object)")
        return False


# --- Routes ---
@app.route('/', methods=['GET'])
def index():
    """Renders the main upload form."""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_and_process():
    """Handles file upload, sends data to Gemini, and provides download."""
    print("\n--- NEW REQUEST START ---")

    # --- Input Validation ---
    if 'file' not in request.files:
        flash('No file part selected.', 'error')
        return redirect(url_for('index'))

    file = request.files['file']
    prompt = request.form.get('prompt', '').strip()

    if file.filename == '':
        flash('No file selected.', 'error')
        return redirect(url_for('index'))

    if not file or not allowed_file(file.filename):
        flash('Invalid file type. Only PDF files are allowed.', 'error')
        return redirect(url_for('index'))

    if not prompt:
        flash('Please provide a prompt describing what JSON structure to extract.', 'error')
        return redirect(url_for('index'))

    # --- File Handling ---
    original_filename = secure_filename(file.filename)
    unique_id = uuid.uuid4().hex[:8]
    temp_pdf_filename = f"{unique_id}_{original_filename}"
    pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], temp_pdf_filename)
    print(f"DEBUG: Generated local PDF path: {pdf_path}")

    gemini_file_object = None # Initialize

    try:
        # 1. Save uploaded PDF temporarily
        print(f"Saving uploaded file to: {pdf_path}")
        file.save(pdf_path)
        print("File saved locally.")

        # 2. Upload PDF to Gemini
        print(f"Uploading file to Gemini: {pdf_path}")
        try:
            gemini_file_object = genai.upload_file(
                path=pdf_path,
                display_name=original_filename,
                mime_type='application/pdf' # Explicitly set MIME type
            )
            print(f"File uploaded successfully to Gemini: {gemini_file_object.name}")
        except Exception as upload_err:
            print(f"ERROR: Gemini file upload failed: {upload_err}")
            traceback.print_exc()
            flash(f"Error uploading file to Gemini: {upload_err}", "error")
            return redirect(url_for('index')) # Cleanup local PDF happens in finally

        # 3. Prepare Prompt and Call Gemini API
        print(f"Initializing Gemini model: {GEMINI_MODEL_TO_USE}")
        model = genai.GenerativeModel(model_name=GEMINI_MODEL_TO_USE)

        full_gemini_prompt = f"""
        **Task:** Analyze the attached PDF file ('{original_filename}') and extract information based on the user's request, formatting the output *strictly* as a valid JSON object.

        **User Request:**
        {prompt}

        **CRITICAL Instructions:**
        1. Carefully read the user's request to understand the desired JSON structure (keys and values).
        2. Extract the relevant data ONLY from the provided PDF content. Do not add information not present in the document.
        3. Format the extracted data STRICTLY as a single, valid JSON object.
        4. **Your entire response MUST be ONLY the JSON object.**
        5. **DO NOT include any introductory text, explanations, apologies, markdown formatting (like ```json or ```), or concluding remarks.** Just the raw JSON structure.
        6. If you cannot fulfill the request or find the necessary information, return a valid JSON object indicating the issue, for example: {{ "error": "Could not find the requested information in the document." }}
        """

        print("\nSending request to Gemini...")
        print("-" * 20)
        # print(f"Full Prompt Sent:\n{full_gemini_prompt}") # Uncomment for debugging prompt
        print("-" * 20)

        response = model.generate_content(
            [full_gemini_prompt, gemini_file_object],
             request_options={"timeout": 600} # 10 min timeout
        )
        print("Received response from Gemini.")
        print("DEBUG: Got response object.")

        # 4. Process Response and Extract JSON
        print("-" * 20)
        print("RAW GEMINI RESPONSE:")
        raw_response_text = "" # Initialize
        try:
             if not response.parts:
                 print("WARNING: Gemini response has no parts.")
                 if hasattr(response, 'prompt_feedback') and response.prompt_feedback and response.prompt_feedback.block_reason:
                     reason = response.prompt_feedback.block_reason
                     msg = f"Gemini response blocked (no parts returned). Reason: {reason}. Check safety ratings."
                     print(f"ERROR: {msg}")
                     flash(msg, "error")
                     delete_gemini_file_safely(gemini_file_object)
                     return redirect(url_for('index'))
                 else:
                    raise ValueError("Gemini returned an empty or incomplete response (no parts).")

             # Check finish reason - might indicate issues even if parts exist
             finish_reason = "UNKNOWN"
             safety_ratings = "N/A"
             if hasattr(response, 'candidates') and response.candidates:
                 candidate = response.candidates[0]
                 finish_reason = getattr(candidate, 'finish_reason', 'UNSPECIFIED')
                 safety_ratings = getattr(candidate, 'safety_ratings', 'N/A')
                 print(f"DEBUG: Candidate Finish Reason: {finish_reason}, Safety Ratings: {safety_ratings}")

                 if finish_reason not in ("STOP", "MAX_TOKENS"):
                     msg = f"Gemini generation finished unexpectedly. Reason: {finish_reason}. Safety Ratings: {safety_ratings}"
                     print(f"WARNING: {msg}")
                     if finish_reason in ("SAFETY", "RECITATION", "OTHER"):
                         flash(f"Gemini stopped processing due to {finish_reason}. Please check the content or prompt.", "error")
                         delete_gemini_file_safely(gemini_file_object)
                         return redirect(url_for('index'))
                     # If MAX_TOKENS, we might still have partial JSON, continue processing

             # Access response text only after checks
             raw_response_text = response.text
             print("DEBUG: Accessed response.text")
             print(raw_response_text)

        except ValueError as ve: # Specific error like empty response
            print(f"ERROR: Issue processing Gemini response structure: {ve}")
            traceback.print_exc()
            feedback = getattr(response, 'prompt_feedback', 'N/A')
            flash(f"Gemini request failed or response incomplete. Reason: {ve}. Feedback: {feedback}", "error")
            delete_gemini_file_safely(gemini_file_object)
            return redirect(url_for('index'))
        except AttributeError as ae: # Missing expected attribute
             print(f"ERROR: Could not access expected attribute in Gemini response: {ae}")
             traceback.print_exc()
             print(f"Full response object: {response}")
             flash(f"Error processing Gemini's response structure: {ae}", "error")
             delete_gemini_file_safely(gemini_file_object)
             return redirect(url_for('index'))
        except Exception as resp_err: # Other errors accessing response
            print(f"DEBUG: Failed inside response access block: {resp_err}")
            print(f"ERROR: Could not access or process response object: {resp_err}")
            traceback.print_exc()
            print(f"Full response object: {response}")
            flash(f"Error processing Gemini's response: {resp_err}", "error")
            delete_gemini_file_safely(gemini_file_object)
            return redirect(url_for('index'))
        print("-" * 20)

        # --- JSON Cleaning ---
        print("DEBUG: Calling clean_json_string")
        cleaned_json_string = clean_json_string(raw_response_text)
        print(f"DEBUG: clean_json_string returned: {type(cleaned_json_string)}") # Check type
        print(f"Cleaned JSON String Attempt:\n{cleaned_json_string}")
        print("-" * 20)

        if not cleaned_json_string:
            print("DEBUG: cleaned_json_string is None or empty.")
            print("ERROR: clean_json_string function could not extract potential JSON.")
            flash("Error: Could not extract a JSON structure from Gemini's response. It might have included extra text, been empty, or failed the request.", "error")
            delete_gemini_file_safely(gemini_file_object)
            return redirect(url_for('index'))

        # 5. Validate and Save JSON
        json_path = None # Initialize for finally block
        try:
            print("DEBUG: Attempting json.loads")
            json_data = json.loads(cleaned_json_string)
            print("DEBUG: json.loads successful")
            pretty_json_string = json.dumps(json_data, indent=4, ensure_ascii=False)
            print("DEBUG: json.dumps successful")

            # --- File Saving ---
            base_filename = os.path.splitext(original_filename)[0]
            json_filename = f"{unique_id}_{base_filename}.json"
            json_path = os.path.join(app.config['GENERATED_FOLDER'], json_filename)
            print(f"DEBUG: JSON path defined as: {json_path}")

            print("DEBUG: Attempting to open and write JSON file")
            with open(json_path, 'w', encoding='utf-8') as f:
                f.write(pretty_json_string)
            print("DEBUG: JSON file write successful")
            print("JSON file saved successfully.")

        except json.JSONDecodeError as json_err:
            print(f"DEBUG: Failed inside json.loads block: {json_err}")
            print(f"ERROR: Failed to decode JSON string: {json_err}")
            print(f"Problematic String causing error:\n>>>\n{cleaned_json_string}\n<<<")
            flash(f"Error: Gemini's response looked like JSON but could not be correctly parsed. Issue: '{json_err}'", 'error')
            delete_gemini_file_safely(gemini_file_object)
            return redirect(url_for('index'))
        except IOError as io_err:
            print(f"DEBUG: Failed inside file write block: {io_err}")
            print(f"ERROR: Could not write JSON file to disk: {io_err}")
            traceback.print_exc()
            flash(f"Error saving the generated JSON file: {io_err}", 'error')
            delete_gemini_file_safely(gemini_file_object)
            return redirect(url_for('index'))
        except Exception as e: # Catch other errors during this block
             print(f"DEBUG: Error during JSON parsing or file writing block: {e}")
             traceback.print_exc()
             flash(f"An unexpected error occurred while processing or saving JSON: {e}", 'error')
             delete_gemini_file_safely(gemini_file_object)
             return redirect(url_for('index'))


        # 6. Clean up temporary Gemini file AFTER successful processing AND file saving
        delete_gemini_file_safely(gemini_file_object) # Now delete the file from Gemini cloud storage


        # 7. Provide Download Link/Trigger Download
        print(f"DEBUG: Preparing to call send_file for path: {json_path}")
        if not json_path or not os.path.exists(json_path):
            print("ERROR: json_path is not set or file does not exist before send_file!")
            flash("Internal Server Error: Generated JSON file is missing.", 'error')
            # No need to delete Gemini file here, already done or failed earlier.
            # Local PDF cleanup happens in finally.
            return redirect(url_for('index'))

        print(f"DEBUG: Does file exist just before send_file? {os.path.exists(json_path)}")
        try:
            print(f"Attempting to send file for download: {json_path}")
            # --- STANDARD SEND_FILE ---
            response = send_file(
                json_path,
                as_attachment=True,
                download_name=f"{base_filename}_extracted.json",
                mimetype='application/json'
            )
            print(f"DEBUG: send_file call completed. Returning response: {response}")
            return response

            # --- TEMPORARY TEST (Uncomment below, comment above to test) ---
            # print("DEBUG: Running temporary send_file test (no attachment)")
            # response = send_file(
            #      json_path,
            #      mimetype='application/json'
            #      # as_attachment=True, # Temporarily commented out
            #      # download_name=f"{base_filename}_extracted.json" # Temporarily commented out
            #  )
            # print(f"DEBUG: send_file (test) call completed. Returning response: {response}")
            # return response
            # --- END TEMPORARY TEST ---


        except Exception as send_err:
            print(f"DEBUG: Failed inside send_file block: {send_err}")
            print(f"ERROR: Failed to send file: {send_err}")
            traceback.print_exc()
            flash(f"Could not send the generated file for download: {send_err}", 'error')
            # No need to delete Gemini file here, already done.
            return redirect(url_for('index'))

    # Specific exception for blocked prompts (can happen before generation starts)
    except genai.types.generation_types.BlockedPromptException as e:
         print(f"ERROR: Gemini Error: Prompt blocked - {e}")
         # Attempt to access feedback safely
         feedback = "N/A"
         try:
             feedback = e.response.prompt_feedback
         except AttributeError:
             pass # No response attribute or feedback nested
         print(f"Prompt Feedback: {feedback}")
         flash(f"Request blocked by Gemini's safety filters. Please modify your prompt. Details: {e}", "error")
         delete_gemini_file_safely(gemini_file_object) # Attempt cleanup
         return redirect(url_for('index'))
    # Catch-all for unexpected errors during the main process flow
    except Exception as e:
        print(f"ERROR: An unexpected error occurred in /upload: {e}")
        traceback.print_exc() # Print detailed traceback to console
        flash(f"An unexpected server error occurred: {str(e)}", 'error')
        delete_gemini_file_safely(gemini_file_object) # Attempt cleanup
        return redirect(url_for('index'))

    finally:
        # --- Clean up uploaded PDF (always attempt this) ---
        print("DEBUG: Entering finally block for local PDF cleanup.")
        # Check if pdf_path was defined in the first place (it should be unless error happened before)
        if 'pdf_path' in locals() and pdf_path and os.path.exists(pdf_path):
            try:
                os.remove(pdf_path)
                print(f"Temporary PDF deleted: {pdf_path}")
            except OSError as e:
                print(f"Error deleting temporary PDF {pdf_path}: {e}")
        else:
            print(f"DEBUG: Local PDF path '{pdf_path if 'pdf_path' in locals() else 'undefined'}' not found or doesn't exist for cleanup.")
        print("--- REQUEST END ---")


# --- Run the App ---
if __name__ == '__main__':
    print("Starting Flask development server...")
    # Set debug=False for production!
    # Use host='0.0.0.0' to be accessible on your network, or '127.0.0.1' for local only.
    app.run(debug=True, host='0.0.0.0', port=5001)