import os
from pypdf import PdfReader, PdfWriter
from pathlib import Path
import argparse # For command-line arguments (optional but good practice)

def split_pdf(input_pdf_path: str, ranges: list[tuple[int, int]], output_dir: str = "."):
    """
    Splits a PDF file into multiple PDFs based on specified page ranges.

    Args:
        input_pdf_path (str): The path to the input PDF file.
        ranges (list[tuple[int, int]]): A list of tuples, where each tuple
                                        represents a page range (start_page, end_page).
                                        Page numbers are 1-based and inclusive.
        output_dir (str): The directory where the split PDFs will be saved.
                          Defaults to the current directory.
    """
    input_path = Path(input_pdf_path)
    output_path = Path(output_dir)

    # --- Input Validation ---
    if not input_path.is_file():
        print(f"Error: Input PDF file not found at '{input_pdf_path}'")
        return

    if not input_path.suffix.lower() == ".pdf":
        print(f"Error: Input file '{input_pdf_path}' does not seem to be a PDF.")
        return

    # Create output directory if it doesn't exist
    output_path.mkdir(parents=True, exist_ok=True)

    try:
        reader = PdfReader(input_pdf_path)
        total_pages = len(reader.pages)
        print(f"Input PDF '{input_path.name}' has {total_pages} pages.")

        # --- Range Validation ---
        valid_ranges = []
        for i, (start_page, end_page) in enumerate(ranges):
            if not isinstance(start_page, int) or not isinstance(end_page, int):
                print(f"Warning: Skipping invalid range #{i+1}: {start_page}-{end_page}. Pages must be integers.")
                continue
            if start_page < 1:
                print(f"Warning: Adjusting start page for range #{i+1} from {start_page} to 1.")
                start_page = 1
            if end_page > total_pages:
                print(f"Warning: Adjusting end page for range #{i+1} from {end_page} to {total_pages} (total pages).")
                end_page = total_pages
            if start_page > end_page:
                print(f"Warning: Skipping invalid range #{i+1}: Start page {start_page} > End page {end_page}.")
                continue
            valid_ranges.append((start_page, end_page))

        if not valid_ranges:
            print("Error: No valid page ranges were provided or derived.")
            return

        # --- Splitting Process ---
        for i, (start_page, end_page) in enumerate(valid_ranges):
            writer = PdfWriter()
            output_filename = output_path / f"{input_path.stem}_pages_{start_page}-{end_page}{input_path.suffix}"

            print(f"Processing range: Pages {start_page} to {end_page} -> '{output_filename.name}'")

            # Remember: PyPDF uses 0-based indexing, user provides 1-based
            # Loop from start_page-1 up to end_page-1 (inclusive)
            for page_num in range(start_page - 1, end_page):
                try:
                    writer.add_page(reader.pages[page_num])
                except IndexError:
                    # This shouldn't happen with the validation above, but good to have
                    print(f"  Error: Page index {page_num} (User page {page_num+1}) out of bounds. Skipping page.")
                    continue

            # Save the new PDF
            try:
                with open(output_filename, "wb") as output_pdf_file:
                    writer.write(output_pdf_file)
                print(f"  Successfully created '{output_filename.name}'")
            except Exception as e:
                print(f"  Error writing file '{output_filename.name}': {e}")

    except Exception as e:
        print(f"An error occurred while processing the PDF: {e}")

def main():
    """Handles command-line argument parsing."""
    parser = argparse.ArgumentParser(description="Split a PDF into multiple files based on page ranges.")
    parser.add_argument("input_pdf", help="Path to the input PDF file.")
    parser.add_argument("-r", "--range",
                        action='append',  # Allows specifying --range multiple times
                        nargs=2,          # Expects two arguments (start, end)
                        metavar=('START', 'END'),
                        help="Page range to extract (e.g., --range 1 40). Repeat for multiple ranges.")
    parser.add_argument("-o", "--output-dir",
                        default=".",
                        help="Directory to save the split PDF files (default: current directory).")

    args = parser.parse_args()

    if not args.range:
        parser.error("At least one --range must be specified (e.g., --range 1 40).")
        return

    # Convert string ranges from argparse to integer tuples
    page_ranges = []
    for r in args.range:
        try:
            start = int(r[0])
            end = int(r[1])
            page_ranges.append((start, end))
        except ValueError:
            print(f"Error: Invalid page numbers in range '{r[0]}-{r[1]}'. Both must be integers.")
            return

    split_pdf(args.input_pdf, page_ranges, args.output_dir)

if __name__ == "__main__":
    main()