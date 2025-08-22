#!/usr/bin/env python3

import sys
from fontTools.ttLib import TTFont

def analyze_kern_table(font_path):
    """
    Loads a font and analyzes its 'kern' table, if present.
    """
    try:
        font = TTFont(font_path)
    except Exception as e:
        print(f"Error: Could not open font file at {font_path}. Reason: {e}")
        return

    print(f"--- Analyzing 'kern' table in: {font_path} ---")

    if 'kern' not in font:
        print("No 'kern' table found.")
        return

    kern_table = font['kern']
    print(f"  > Table version: {kern_table.version}")
    
    if not hasattr(kern_table, 'kernTables') or not kern_table.kernTables:
        print("  > No subtables found.")
        return

    print(f"  > Number of subtables: {len(kern_table.kernTables)}")
    
    for i, subtable in enumerate(kern_table.kernTables):
        print(f"\n  --- Subtable {i+1} ---")
        if hasattr(subtable, 'coverage'):
            print(f"  > Coverage flags (as integer): {subtable.coverage}")
            # A more detailed breakdown of flags
            coverage_int = int(subtable.coverage)
            print(f"  > Coverage flags breakdown:")
            print(f"    - Horizontal Kerning: {'Yes' if coverage_int & 1 else 'No'} (bit 0)")
            print(f"    - Minimum Values: {'Yes' if coverage_int & 2 else 'No'} (bit 1)")
            print(f"    - Cross-stream Kerning: {'Yes' if coverage_int & 4 else 'No'} (bit 2)")
            print(f"    - Variation Kerning: {'Yes' if coverage_int & 8 else 'No'} (bit 3)")
        
        if hasattr(subtable, 'kernTable'):
            print(f"  > Found {len(subtable.kernTable)} kerning pairs.")
            # Print the first 20 kerning pairs and values for inspection
            print("  > Sample of kerning pairs (glyph1, glyph2) -> value:")
            for pair, value in list(subtable.kernTable.items())[:20]:
                print(f" - ({pair[0]}, {pair[1]}) -> {value}")
        else:
            print("  > Subtable has no 'kernTable' attribute.")

def main():
    """
    Main function to compare two fonts.
    """
    # Replace these with the actual paths to your font files
    working_font = "./KC_Garamond-Regular.ttf"
    broken_font = "./KF_Garamond-Regular.ttf"

    analyze_kern_table(working_font)
    print("\n" + "="*50 + "\n")
    analyze_kern_table(broken_font)

if __name__ == "__main__":
    main()