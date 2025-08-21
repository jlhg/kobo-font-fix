#!/usr/bin/env python3

# ttfconv.py

# This script converts OTF fonts to TTF fonts using the font-tools library.
# It processes a list of font files provided as command-line arguments.

# The font-tools library must be installed: `pip install fonttools`.

from fontTools.ttLib import TTFont
import os
import sys

def convert_font(input_file_path):
    """
    Converts a font file to a TTF font file.
    This function currently assumes the input is OTF and the output is TTF.

    Args:
        input_file_path (str): The path to the input font file.
    """
    if not os.path.exists(input_file_path):
        print(f"❌ Error: The file '{input_file_path}' was not found.")
        return

    try:
        output_file_path = os.path.splitext(input_file_path)[0] + ".ttf"
        font = TTFont(input_file_path)
        font.save(output_file_path)

        print(f"✅ Converted: {os.path.basename(input_file_path)} -> {os.path.basename(output_file_path)}")

    except Exception as e:
        print(f"❌ An error occurred during conversion of '{os.path.basename(input_file_path)}': {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python font_converter.py <font_file1> <font_file2> ...")
        print("Example: python font_converter.py MyFont.otf AnotherFont.otf")
        print("You can also use a wildcard: python font_converter.py *.otf")
    else:
        for file_path in sys.argv[1:]:
            if file_path.lower().endswith(".otf"):
                convert_font(file_path)
            else:
                print(f"⚠️ Skipping '{file_path}': This script only converts OTF to TTF.")
                print(f"To convert other formats, please provide the correct extension.")

    print("\nProcessing complete.")
