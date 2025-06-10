# Example usage within another script
from pdf_clipper import split_pdf # Assuming you saved the above code as your_script_name.py

input_file = "2079_najir.pdf"
output_folder = "split_pdfs"
ranges_to_split = [
    (1,50),
    (50,100),
    (100,150),
    (150,200),
    (200,250),
    (250,300),
    (300,350),
    (350,400),
    (400,415)
    # (1, 30),
    # (30,60),
    # (60,90),
    # (90,120),
    # (120,150),
    # (150,180),
    # (180,210),
    # (210,240),
    # (240,270),
    # (270,300),
    # (300,330),
    # (330,360),
    # (360,390),
    # (30, 60),   # Note: Page 40 will be included in both the first and second output files
    # (40, 60),  # Page 84 included here too
    # (60, 80), # Page 152 included here too
    # (80, 100),  # Page 180 included here too
    # (100, 120),  # Page 180 included here too
    # (120, 138),  # Page 180 included here too
    # (144, 211),  # Page 180 included here too
    # (180, 210),  # Page 180 included here too
    # (210, 240),  # Page 180 included here too
    # (240, 252),  # Page 180 included here too

]

split_pdf(input_file, ranges_to_split, output_folder)
print("Splitting process finished.")