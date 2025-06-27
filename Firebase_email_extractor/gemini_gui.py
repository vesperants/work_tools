import tkinter as tk
from tkinter import filedialog, messagebox, ttk, scrolledtext
import threading
from gemini_api import GeminiPDFProcessor, BatchPDFProcessor
import os
import sys
from datetime import datetime

class GeminiGUI:
    """
    Simple GUI for the Gemini PDF Processor.
    Provides an easy-to-use interface for processing PDFs with progress logging.
    Supports both single file and batch processing with threading.
    """
    
    def __init__(self, root):
        """Initialize the GUI components."""
        self.root = root
        self.root.title("Gemini PDF Processor - Najir Extractor (Batch Mode)")
        self.root.geometry("900x800")
        
        # Initialize variables
        self.selected_files = []
        self.processing_active = False
        
        # Initialize processor
        try:
            # Create a custom processor that logs to our GUI
            self.processor = None
            self.models = []
            self.log_to_gui("🔑 Initializing Gemini API...")
            self.processor = GeminiPDFProcessor(verbose=False)  # We'll handle logging ourselves
            self.models = self.processor.get_available_models()
            self.recommended_model = self.processor.get_recommended_free_model()
            self.log_to_gui("✅ Gemini API initialized successfully")
            self.log_to_gui(f"📋 Found {len(self.models)} available models")
            self.log_to_gui(f"⭐ Recommended free model: {self.recommended_model}")
        except Exception as e:
            self.log_to_gui(f"❌ Failed to initialize Gemini API: {e}")
            messagebox.showerror("Error", f"Failed to initialize Gemini API: {e}")
            self.processor = None
            self.models = []
            self.recommended_model = 'models/gemini-1.5-flash'
        
        self.setup_ui()
    
    def log_to_gui(self, message):
        """Add a log message to the GUI log area."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {message}\n"
        
        # If log_text exists, add to it
        if hasattr(self, 'log_text'):
            self.log_text.insert(tk.END, log_message)
            self.log_text.see(tk.END)  # Auto-scroll to bottom
        else:
            # Store messages until log_text is created
            if not hasattr(self, '_pending_logs'):
                self._pending_logs = []
            self._pending_logs.append(log_message)
    
    def format_model_name(self, model):
        """Format model name with indicators for free vs paid."""
        if model == self.recommended_model:
            return f"{model} ⭐ (Recommended Free)"
        elif 'flash' in model.lower() or '1.5' in model:
            return f"{model} 🆓 (Free)"
        else:
            return f"{model} 💰 (Paid)"
    
    def setup_ui(self):
        """Set up the user interface components."""
        # Create main container with scrollable frame
        main_container = ttk.Frame(self.root)
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Title
        title_label = ttk.Label(main_container, text="Gemini PDF Processor - Batch Mode", 
                               font=("Arial", 16, "bold"))
        title_label.pack(pady=(0, 20))
        
        # Create notebook for tabs
        notebook = ttk.Notebook(main_container)
        notebook.pack(fill=tk.BOTH, expand=True)
        
        # Main processing tab
        main_tab = ttk.Frame(notebook)
        notebook.add(main_tab, text="Batch Processing")
        
        # Queue tab
        queue_tab = ttk.Frame(notebook)
        notebook.add(queue_tab, text="File Queue")
        
        # Log tab
        log_tab = ttk.Frame(notebook)
        notebook.add(log_tab, text="Progress Log")
        
        # Setup tabs
        self.setup_main_tab(main_tab)
        self.setup_queue_tab(queue_tab)
        self.setup_log_tab(log_tab)
        
        # Add any pending log messages
        if hasattr(self, '_pending_logs'):
            for log_msg in self._pending_logs:
                self.log_text.insert(tk.END, log_msg)
            delattr(self, '_pending_logs')
    
    def setup_main_tab(self, parent):
        """Set up the main processing tab."""
        # Create scrollable frame
        canvas = tk.Canvas(parent)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # PDF file selection
        file_section = ttk.LabelFrame(scrollable_frame, text="PDF File Selection (Multiple Files)", padding=10)
        file_section.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(file_section, text="Select PDF Files (hold Ctrl/Cmd for multiple):").pack(anchor=tk.W, pady=(0, 5))
        
        file_frame = ttk.Frame(file_section)
        file_frame.pack(fill=tk.X)
        
        ttk.Button(file_frame, text="📁 Select Multiple PDFs", command=self.browse_multiple_files).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(file_frame, text="🗑️ Clear Selection", command=self.clear_file_selection).pack(side=tk.LEFT)
        
        # Selected files display
        self.files_label = ttk.Label(file_section, text="No files selected", foreground="gray")
        self.files_label.pack(anchor=tk.W, pady=(10, 0))
        
        # Threading configuration
        thread_section = ttk.LabelFrame(scrollable_frame, text="Threading Configuration", padding=10)
        thread_section.pack(fill=tk.X, pady=(0, 10))
        
        thread_frame = ttk.Frame(thread_section)
        thread_frame.pack(fill=tk.X)
        
        ttk.Label(thread_frame, text="Number of concurrent threads:").pack(side=tk.LEFT)
        
        self.thread_var = tk.StringVar(value="3")
        thread_spinbox = ttk.Spinbox(thread_frame, from_=1, to=10, width=5, textvariable=self.thread_var)
        thread_spinbox.pack(side=tk.LEFT, padx=(10, 0))
        
        ttk.Label(thread_frame, text="(1-10 threads, 3 recommended)", font=("Arial", 9), foreground="gray").pack(side=tk.LEFT, padx=(10, 0))
        
        # Model selection
        model_section = ttk.LabelFrame(scrollable_frame, text="Model Configuration", padding=10)
        model_section.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(model_section, text="Select Model (⭐ = Recommended, 🆓 = Free, 💰 = Paid):").pack(anchor=tk.W, pady=(0, 5))
        
        self.model_var = tk.StringVar()
        
        # Format model names with indicators
        formatted_models = [self.format_model_name(model) for model in self.models]
        
        model_combo = ttk.Combobox(model_section, textvariable=self.model_var, 
                                  values=formatted_models, state="readonly")
        model_combo.pack(fill=tk.X, pady=(0, 5))
        
        # Set default to recommended free model
        if self.recommended_model in self.models:
            default_formatted = self.format_model_name(self.recommended_model)
            model_combo.set(default_formatted)
        elif self.models:
            model_combo.set(formatted_models[0])
        
        # Add info label about free models
        info_label = ttk.Label(model_section, 
                              text="💡 Tip: Use free models (🆓) to avoid billing charges", 
                              font=("Arial", 9), 
                              foreground="blue")
        info_label.pack(anchor=tk.W, pady=(5, 0))
        
        # Custom prompt section
        prompt_section = ttk.LabelFrame(scrollable_frame, text="Custom Prompt (Optional)", padding=10)
        prompt_section.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(prompt_section, text="Leave empty to use default najir extraction prompt:").pack(anchor=tk.W, pady=(0, 5))
        
        self.prompt_text = tk.Text(prompt_section, height=4, wrap=tk.WORD)
        self.prompt_text.pack(fill=tk.X)
        
        # Output section
        output_section = ttk.LabelFrame(scrollable_frame, text="Output Configuration", padding=10)
        output_section.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(output_section, text="Output Directory (optional - current directory if empty):").pack(anchor=tk.W, pady=(0, 5))
        
        output_frame = ttk.Frame(output_section)
        output_frame.pack(fill=tk.X)
        
        self.output_path_var = tk.StringVar()
        self.output_entry = ttk.Entry(output_frame, textvariable=self.output_path_var)
        self.output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        ttk.Button(output_frame, text="Browse", command=self.browse_output_dir).pack(side=tk.RIGHT)
        
        # Control section
        control_section = ttk.Frame(scrollable_frame)
        control_section.pack(fill=tk.X, pady=20)
        
        # Process button
        self.process_button = ttk.Button(control_section, text="🚀 Start Batch Processing", 
                                        command=self.process_batch)
        self.process_button.pack(pady=10)
        
        # Progress bar
        self.progress = ttk.Progressbar(control_section, mode='determinate')
        self.progress.pack(fill=tk.X, pady=5)
        
        # Status label
        self.status_var = tk.StringVar(value="Ready to process PDF files")
        self.status_label = ttk.Label(control_section, textvariable=self.status_var)
        self.status_label.pack(pady=5)
        
        # Pack canvas and scrollbar
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
    
    def setup_queue_tab(self, parent):
        """Set up the queue tab showing file processing status."""
        queue_frame = ttk.Frame(parent)
        queue_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        ttk.Label(queue_frame, text="File Processing Queue:", font=("Arial", 12, "bold")).pack(anchor=tk.W, pady=(0, 10))
        
        # Create treeview for queue display
        columns = ("File", "Status", "Progress", "Thread")
        self.queue_tree = ttk.Treeview(queue_frame, columns=columns, show="headings", height=15)
        
        # Define column headings and widths
        self.queue_tree.heading("File", text="PDF File")
        self.queue_tree.heading("Status", text="Status")
        self.queue_tree.heading("Progress", text="Progress")
        self.queue_tree.heading("Thread", text="Thread ID")
        
        self.queue_tree.column("File", width=300)
        self.queue_tree.column("Status", width=150)
        self.queue_tree.column("Progress", width=100)
        self.queue_tree.column("Thread", width=100)
        
        # Add scrollbar for treeview
        queue_scrollbar = ttk.Scrollbar(queue_frame, orient="vertical", command=self.queue_tree.yview)
        self.queue_tree.configure(yscrollcommand=queue_scrollbar.set)
        
        self.queue_tree.pack(side="left", fill="both", expand=True)
        queue_scrollbar.pack(side="right", fill="y")
        
        # Queue statistics
        stats_frame = ttk.Frame(queue_frame)
        stats_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.queue_stats_var = tk.StringVar(value="Queue: 0 files | Processing: 0 | Completed: 0 | Failed: 0")
        ttk.Label(stats_frame, textvariable=self.queue_stats_var, font=("Arial", 10)).pack()
    
    def setup_log_tab(self, parent):
        """Set up the log tab with progress information."""
        log_frame = ttk.Frame(parent)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        ttk.Label(log_frame, text="Processing Progress Log:", font=("Arial", 12, "bold")).pack(anchor=tk.W, pady=(0, 10))
        
        # Create scrolled text widget for logs
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=25)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Add clear button
        button_frame = ttk.Frame(log_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(button_frame, text="Clear Log", command=self.clear_log).pack(side=tk.RIGHT)
    
    def clear_log(self):
        """Clear the log text area."""
        self.log_text.delete(1.0, tk.END)
        self.log_to_gui("📝 Log cleared")
    
    def browse_multiple_files(self):
        """Open file dialog to select multiple PDF files."""
        file_paths = filedialog.askopenfilenames(
            title="Select PDF Files",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")]
        )
        if file_paths:
            self.selected_files = list(file_paths)
            self.update_file_display()
            self.update_queue_display()
            self.log_to_gui(f"📄 Selected {len(self.selected_files)} PDF files")
    
    def clear_file_selection(self):
        """Clear the selected files."""
        self.selected_files = []
        self.update_file_display()
        self.update_queue_display()
        self.log_to_gui("🗑️ File selection cleared")
    
    def update_file_display(self):
        """Update the display of selected files."""
        if not self.selected_files:
            self.files_label.config(text="No files selected", foreground="gray")
        else:
            file_names = [os.path.basename(f) for f in self.selected_files]
            if len(file_names) <= 3:
                display_text = ", ".join(file_names)
            else:
                display_text = f"{', '.join(file_names[:3])} ... and {len(file_names)-3} more"
            
            self.files_label.config(text=f"{len(self.selected_files)} files: {display_text}", foreground="black")
    
    def update_queue_display(self):
        """Update the queue display with current files."""
        # Clear existing items
        for item in self.queue_tree.get_children():
            self.queue_tree.delete(item)
        
        # Add selected files to queue display
        for i, file_path in enumerate(self.selected_files):
            filename = os.path.basename(file_path)
            self.queue_tree.insert("", "end", iid=f"file_{i}", 
                                 values=(filename, "Queued", "0%", "-"))
        
        self.update_queue_stats()
    
    def update_queue_stats(self):
        """Update queue statistics display."""
        total = len(self.selected_files)
        queued = len([item for item in self.queue_tree.get_children() 
                     if self.queue_tree.item(item)['values'][1] == "Queued"])
        processing = len([item for item in self.queue_tree.get_children() 
                         if self.queue_tree.item(item)['values'][1] == "Processing"])
        completed = len([item for item in self.queue_tree.get_children() 
                        if self.queue_tree.item(item)['values'][1] == "Completed"])
        failed = len([item for item in self.queue_tree.get_children() 
                     if self.queue_tree.item(item)['values'][1] == "Failed"])
        
        self.queue_stats_var.set(f"Queue: {total} files | Queued: {queued} | Processing: {processing} | Completed: {completed} | Failed: {failed}")
    
    def browse_output_dir(self):
        """Open directory dialog to select output directory."""
        dir_path = filedialog.askdirectory(title="Select Output Directory")
        if dir_path:
            self.output_path_var.set(dir_path)
            self.log_to_gui(f"📁 Output directory set: {dir_path}")
    
    def extract_model_name(self, formatted_model):
        """Extract the actual model name from the formatted display name."""
        # Remove the indicators and get just the model name
        model_name = formatted_model.split(' ⭐')[0].split(' 🆓')[0].split(' 💰')[0]
        return model_name
    
    def update_file_status(self, filename, status, progress="", thread_id=""):
        """Update the status of a file in the queue display."""
        for item in self.queue_tree.get_children():
            values = self.queue_tree.item(item)['values']
            if values[0] == filename:
                self.queue_tree.item(item, values=(filename, status, progress, thread_id))
                break
        
        self.update_queue_stats()
        
        # Update progress bar
        if self.selected_files:
            completed = len([item for item in self.queue_tree.get_children() 
                           if self.queue_tree.item(item)['values'][1] in ["Completed", "Failed"]])
            progress_percent = (completed / len(self.selected_files)) * 100
            self.progress['value'] = progress_percent
    
    def process_batch(self):
        """Process the selected PDF files in batch mode."""
        # Validate inputs
        if not self.selected_files:
            messagebox.showerror("Error", "Please select PDF files")
            return
        
        if not self.model_var.get():
            messagebox.showerror("Error", "Please select a model")
            return
        
        if not self.processor:
            messagebox.showerror("Error", "Gemini API not initialized")
            return
        
        if self.processing_active:
            messagebox.showwarning("Warning", "Processing is already active")
            return
        
        # Get configuration
        try:
            max_threads = int(self.thread_var.get())
            if max_threads < 1 or max_threads > 10:
                raise ValueError("Thread count must be between 1 and 10")
        except ValueError as e:
            messagebox.showerror("Error", f"Invalid thread count: {e}")
            return
        
        # Switch to queue tab to show progress
        notebook = self.root.children['!frame'].children['!notebook']
        notebook.select(1)  # Select queue tab
        
        # Disable button and start progress
        self.process_button.config(state="disabled", text="Processing...")
        self.progress['value'] = 0
        self.processing_active = True
        self.status_var.set(f"Processing {len(self.selected_files)} files with {max_threads} threads...")
        
        self.log_to_gui("=" * 60)
        self.log_to_gui("🎯 Starting batch processing...")
        
        # Run processing in separate thread to avoid freezing GUI
        thread = threading.Thread(target=self._process_batch_thread)
        thread.daemon = True
        thread.start()
    
    def _process_batch_thread(self):
        """Process batch in a separate thread with detailed logging."""
        try:
            # Get inputs
            formatted_model = self.model_var.get()
            model_name = self.extract_model_name(formatted_model)
            custom_prompt = self.prompt_text.get("1.0", tk.END).strip()
            custom_prompt = custom_prompt if custom_prompt else None
            output_dir = self.output_path_var.get().strip()
            output_dir = output_dir if output_dir else None
            max_threads = int(self.thread_var.get())
            
            # Log processing details
            self.log_to_gui(f"📄 Processing {len(self.selected_files)} files")
            self.log_to_gui(f"🧵 Using {max_threads} concurrent threads")
            self.log_to_gui(f"🤖 Model: {model_name}")
            if custom_prompt:
                self.log_to_gui("📝 Using custom prompt")
            else:
                self.log_to_gui("📝 Using default najir extraction prompt")
            
            # Create batch processor with GUI callback
            batch_processor = BatchPDFProcessor(max_threads=max_threads, verbose=False)
            batch_processor.set_progress_callback(self.batch_progress_callback)
            
            # Process the batch
            results = batch_processor.process_batch(
                pdf_files=self.selected_files,
                model_name=model_name,
                custom_prompt=custom_prompt,
                output_dir=output_dir
            )
            
            # Update UI on main thread
            self.root.after(0, self._processing_complete, results)
            
        except Exception as e:
            # Update UI on main thread with error
            self.root.after(0, self._processing_error, str(e))
    
    def batch_progress_callback(self, message):
        """Callback function for batch processing progress updates."""
        # Update GUI from batch processor
        self.root.after(0, self.log_to_gui, message)
        
        # Parse message to update queue display
        if "Thread" in message and "Starting" in message:
            # Extract filename and thread ID
            parts = message.split(": Starting ")
            if len(parts) == 2:
                thread_part = parts[0].split("Thread ")[-1]
                filename = parts[1]
                self.root.after(0, self.update_file_status, filename, "Processing", "0%", thread_part)
        
        elif "Thread" in message and "Completed" in message:
            # Extract filename
            parts = message.split(": Completed ")
            if len(parts) == 2:
                filename = parts[1]
                self.root.after(0, self.update_file_status, filename, "Completed", "100%", "")
        
        elif "Thread" in message and "Error processing" in message:
            # Extract filename
            parts = message.split(": Error processing ")
            if len(parts) == 2:
                filename = parts[1].split(":")[0]
                self.root.after(0, self.update_file_status, filename, "Failed", "0%", "")
    
    def _processing_complete(self, results):
        """Called when batch processing is complete."""
        self.progress['value'] = 100
        self.process_button.config(state="normal", text="🚀 Start Batch Processing")
        self.processing_active = False
        
        success_rate = results['success_rate']
        total_time = results['total_time']
        
        self.status_var.set(f"Batch complete! Success rate: {success_rate:.1f}% in {total_time:.1f}s")
        
        self.log_to_gui("=" * 60)
        self.log_to_gui("🎉 BATCH PROCESSING COMPLETED!")
        self.log_to_gui(f"📊 Success rate: {success_rate:.1f}%")
        self.log_to_gui(f"⏱️  Total time: {total_time:.1f} seconds")
        self.log_to_gui("=" * 60)
        
        # Show completion dialog
        successful_count = len(results['successful'])
        failed_count = len(results['failed'])
        
        message = f"Batch processing completed!\n\n"
        message += f"✅ Successful: {successful_count}\n"
        message += f"❌ Failed: {failed_count}\n"
        message += f"📊 Success rate: {success_rate:.1f}%\n"
        message += f"⏱️ Total time: {total_time:.1f} seconds"
        
        messagebox.showinfo("Batch Complete", message)
    
    def _processing_error(self, error_message):
        """Called when batch processing encounters an error."""
        self.progress['value'] = 0
        self.process_button.config(state="normal", text="🚀 Start Batch Processing")
        self.processing_active = False
        self.status_var.set("Error occurred during batch processing")
        
        self.log_to_gui(f"❌ Batch Error: {error_message}")
        self.log_to_gui("=" * 60)
        
        # Provide helpful tips for common errors
        error_dialog_msg = f"Failed to process batch:\n\n{error_message}"
        if "free quota tier" in error_message.lower():
            error_dialog_msg += "\n\n💡 Tip: Try selecting a free model (🆓) from the dropdown"
        
        messagebox.showerror("Batch Error", error_dialog_msg)

class CustomGUIProcessor(GeminiPDFProcessor):
    """Custom processor that logs to GUI instead of console."""
    
    def __init__(self, log_callback):
        """Initialize with a callback function for logging."""
        self.log_callback = log_callback
        super().__init__(verbose=False)  # Don't use console logging
    
    def log(self, message):
        """Override log method to use GUI callback."""
        self.log_callback(message)

def main():
    """Run the GUI application."""
    root = tk.Tk()
    app = GeminiGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main() 