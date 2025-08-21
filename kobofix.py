#!/usr/bin/env python3
"""
Font processing utility for Kobo e-readers.

This script processes TrueType/OpenType fonts to improve compatibility with
Kobo e-readers by:
- Adding a custom prefix to font names
- Extracting GPOS kerning data and creating legacy 'kern' tables
- Validating and correcting PANOSE metadata
- Adjusting font metrics for better line spacing

Requirements:
- fontTools (pip install fonttools)
- font-line utility (https://github.com/source-foundry/font-line)
"""

import sys
import os
import subprocess
import argparse
import logging
from pathlib import Path
from collections import defaultdict
from typing import Dict, Tuple, Optional, List

from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables._k_e_r_n import KernTable_format_0

# Constants
DEFAULT_PREFIX = "KF"
DEFAULT_LINE_PERCENT = 20
VALID_SUFFIXES = ("-Regular", "-Bold", "-Italic", "-BoldItalic")
SUPPORTED_EXTENSIONS = (".ttf", ".otf")

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


class FontProcessor:
    """Main font processing class."""
    
    def __init__(self, prefix: str = DEFAULT_PREFIX, line_percent: int = DEFAULT_LINE_PERCENT):
        """
        Initialize the font processor.
        
        Args:
            prefix: Prefix to add to font names
            line_percent: Percentage for baseline adjustment
        """
        self.prefix = prefix
        self.line_percent = line_percent
    
    # ============================================================
    # Kerning extraction methods
    # ============================================================
    
    @staticmethod
    def _pair_value_to_kern(value1, value2) -> int:
        """
        Compute a legacy kerning value from GPOS PairValue records.
        
        Args:
            value1: First value record
            value2: Second value record
            
        Returns:
            Integer kerning value (may be negative)
        """
        kern_value = 0
        
        # Prefer XAdvance adjustments
        if value1 is not None:
            kern_value += getattr(value1, "XAdvance", 0) or 0
        if value2 is not None:
            kern_value += getattr(value2, "XAdvance", 0) or 0
        
        # Fall back to XPlacement if no XAdvance
        if kern_value == 0:
            if value1 is not None:
                kern_value += getattr(value1, "XPlacement", 0) or 0
            if value2 is not None:
                kern_value += getattr(value2, "XPlacement", 0) or 0
        
        return int(kern_value)
    
    def _extract_format1_pairs(self, subtable) -> Dict[Tuple[str, str], int]:
        """Extract kerning pairs from PairPos Format 1 (per-glyph PairSets)."""
        pairs = defaultdict(int)
        
        coverage = getattr(subtable, "Coverage", None)
        pair_sets = getattr(subtable, "PairSet", [])
        
        if not coverage or not hasattr(coverage, "glyphs"):
            return pairs
        
        for idx, left_glyph in enumerate(coverage.glyphs):
            if idx >= len(pair_sets):
                break
            
            for record in getattr(pair_sets[idx], "PairValueRecord", []):
                right_glyph = record.SecondGlyph
                kern_value = self._pair_value_to_kern(record.Value1, record.Value2)
                if kern_value:
                    pairs[(left_glyph, right_glyph)] += kern_value
        
        return pairs
    
    def _extract_format2_pairs(self, subtable) -> Dict[Tuple[str, str], int]:
        """Extract kerning pairs from PairPos Format 2 (class-based)."""
        pairs = defaultdict(int)
        
        coverage = getattr(subtable, "Coverage", None)
        class_def1 = getattr(subtable, "ClassDef1", None)
        class_def2 = getattr(subtable, "ClassDef2", None)
        class1_records = getattr(subtable, "Class1Record", [])
        
        if not coverage or not hasattr(coverage, "glyphs"):
            return pairs
        
        # Build left-side glyph lists per class
        class1_map = getattr(class_def1, "classDefs", {}) if class_def1 else {}
        left_by_class = defaultdict(list)
        for glyph in coverage.glyphs:
            class_idx = class1_map.get(glyph, 0)
            left_by_class[class_idx].append(glyph)
        
        # Build right-side glyph lists per class
        class2_map = getattr(class_def2, "classDefs", {}) if class_def2 else {}
        right_by_class = defaultdict(list)
        for glyph, class_idx in class2_map.items():
            right_by_class[class_idx].append(glyph)
        
        # Extract kerning values
        for class1_idx, class1_record in enumerate(class1_records):
            left_glyphs = left_by_class.get(class1_idx, [])
            if not left_glyphs:
                continue
            
            for class2_idx, class2_record in enumerate(class1_record.Class2Record):
                right_glyphs = right_by_class.get(class2_idx, [])
                if not right_glyphs:
                    continue
                
                kern_value = self._pair_value_to_kern(
                    class2_record.Value1, 
                    class2_record.Value2
                )
                if not kern_value:
                    continue
                
                for left in left_glyphs:
                    for right in right_glyphs:
                        pairs[(left, right)] += kern_value
        
        return pairs
    
    def extract_kern_pairs(self, font: TTFont) -> Dict[Tuple[str, str], int]:
        """
        Extract all kerning pairs from GPOS PairPos lookups.
        
        Args:
            font: Font object to extract kerning from
            
        Returns:
            Dictionary mapping glyph pairs to kerning values
        """
        pairs = defaultdict(int)
        
        if "GPOS" not in font:
            return {}
        
        gpos = font["GPOS"].table
        lookup_list = getattr(gpos, "LookupList", None)
        
        if not lookup_list or not lookup_list.Lookup:
            return {}
        
        for lookup in lookup_list.Lookup:
            # Only process Pair Adjustment lookups (type 2)
            if getattr(lookup, "LookupType", None) != 2:
                continue
            
            for subtable in getattr(lookup, "SubTable", []):
                fmt = getattr(subtable, "Format", None)
                
                if fmt == 1:
                    format1_pairs = self._extract_format1_pairs(subtable)
                    for key, value in format1_pairs.items():
                        pairs[key] += value
                elif fmt == 2:
                    format2_pairs = self._extract_format2_pairs(subtable)
                    for key, value in format2_pairs.items():
                        pairs[key] += value
        
        return dict(pairs)
    
    # ============================================================
    # Legacy kern table methods
    # ============================================================
    
    @staticmethod
    def add_legacy_kern(font: TTFont, kern_pairs: Dict[Tuple[str, str], int]) -> int:
        """
        Create or replace a legacy 'kern' table with the supplied pairs.
        
        Args:
            font: Font object to modify
            kern_pairs: Dictionary of kerning pairs
            
        Returns:
            Number of kern pairs written
        """
        if not kern_pairs:
            return 0
        
        kern_table = newTable("kern")
        kern_table.version = 0
        kern_table.kernTables = []
        
        subtable = KernTable_format_0()
        subtable.version = 0
        subtable.length = None  # Recalculated by fontTools
        subtable.coverage = 1  # Horizontal kerning, format 0
        
        # Ensure proper types for kern table
        subtable.kernTable = {
            tuple(k): int(v) 
            for k, v in kern_pairs.items() 
            if v  # Only include non-zero values
        }
        
        kern_table.kernTables.append(subtable)
        font["kern"] = kern_table
        
        return len(subtable.kernTable)
    
    # ============================================================
    # Name table methods
    # ============================================================
    
    def rename_font(self, font: TTFont, new_name: Optional[str] = None) -> None:
        """
        Prefix the font's family and full names.
        
        Args:
            font: Font object to modify
            new_name: Optional override for the font name
        """
        if "name" not in font:
            return
        
        name_table = font["name"]
        # Name IDs: 1=Family, 4=Full Name, 16=Typographic Family
        ids_to_update = {1, 4, 16}
        
        for record in name_table.names:
            if record.nameID in ids_to_update:
                try:
                    base_name = new_name if new_name else record.toUnicode()
                    new_record_name = f"{self.prefix} {base_name}"
                    record.string = new_record_name.encode(record.getEncoding())
                except Exception:
                    # Fallback to UTF-16 BE encoding
                    try:
                        record.string = new_record_name.encode("utf_16_be")
                    except Exception:
                        logger.warning(f"Failed to update name ID {record.nameID}")
    
    def update_unique_id(self, font: TTFont, new_name: Optional[str] = None) -> None:
        """
        Update the font's Unique ID (nameID 3) with prefix.
        
        Args:
            font: Font object to modify
            new_name: Optional override for the font name
        """
        if "name" not in font:
            return
        
        for record in font["name"].names:
            if record.nameID == 3:  # Unique ID
                try:
                    current_unique = record.toUnicode()
                    # Preserve version info if present
                    parts = current_unique.split("Version")
                    version_info = f"Version{parts[1]}" if len(parts) == 2 else "Version 1.000"
                    base_name = new_name if new_name else parts[0].strip()
                    new_unique_id = f"{self.prefix} {base_name}:{version_info}"
                    record.string = new_unique_id.encode(record.getEncoding())
                except Exception:
                    try:
                        record.string = new_unique_id.encode("utf_16_be")
                    except Exception:
                        logger.warning("Failed to update Unique ID")
    
    # ============================================================
    # PANOSE methods
    # ============================================================
    
    @staticmethod
    def check_and_fix_panose(font: TTFont, filename: str) -> None:
        """
        Check and adjust PANOSE values based on filename suffix.
        
        Args:
            font: Font object to modify
            filename: Font filename to check suffix
        """
        # PANOSE expected values for each style
        style_specs = {
            "-BoldItalic": {"weight": 8, "letterform": 3},
            "-Bold": {"weight": 8, "letterform": 2},
            "-Italic": {"weight": 5, "letterform": 3},
            "-Regular": {"weight": 5, "letterform": 2},
        }
        
        if "OS/2" not in font:
            logger.warning("  No OS/2 table found; skipping PANOSE check")
            return
        
        if not hasattr(font["OS/2"], "panose") or font["OS/2"].panose is None:
            logger.warning("  No PANOSE information; skipping PANOSE check")
            return
        
        panose = font["OS/2"].panose
        base_filename = os.path.basename(filename)
        
        # Find matching style
        matched_style = None
        for style, specs in style_specs.items():
            if style in base_filename:
                matched_style = style
                expected = specs
                break
        
        if not matched_style:
            logger.warning(
                f"  Filename doesn't match expected patterns {list(style_specs.keys())}. "
                "PANOSE check skipped"
            )
            return
        
        # Check and fix values
        changes = []
        current_weight = getattr(panose, "bWeight", None)
        current_letterform = getattr(panose, "bLetterForm", None)
        
        if current_weight != expected["weight"]:
            panose.bWeight = expected["weight"]
            changes.append(f"bWeight {current_weight}->{expected['weight']}")
        
        if current_letterform != expected["letterform"]:
            panose.bLetterForm = expected["letterform"]
            changes.append(f"bLetterForm {current_letterform}->{expected['letterform']}")
        
        if changes:
            logger.info(f"  PANOSE corrected for {matched_style}: {', '.join(changes)}")
        else:
            logger.info(f"  PANOSE check passed for {matched_style}")
    
    # ============================================================
    # Line adjustment methods
    # ============================================================
    
    def apply_line_adjustment(self, font_path: str) -> bool:
        """
        Apply font-line baseline adjustment to the font.
        
        Args:
            font_path: Path to the font file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Check if font-line is available
            result = subprocess.run(
                ["which", "font-line"], 
                capture_output=True, 
                text=True
            )
            if result.returncode != 0:
                logger.error("  font-line utility not found. Please install it first")
                logger.error("  See: https://github.com/source-foundry/font-line")
                return False
            
            # Apply font-line adjustment
            subprocess.run(
                ["font-line", "percent", str(self.line_percent), font_path],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE
            )
            
            # Handle the renamed output file
            base, ext = os.path.splitext(font_path)
            linegap_file = f"{base}-linegap{self.line_percent}{ext}"
            
            if os.path.exists(linegap_file):
                os.remove(font_path)
                os.rename(linegap_file, font_path)
                logger.info(f"  Line spacing adjusted ({self.line_percent}% baseline shift)")
                return True
            else:
                logger.warning(f"  Expected font-line output '{linegap_file}' not found")
                return False
                
        except subprocess.CalledProcessError as e:
            logger.warning(f"  font-line failed: {e}")
            return False
        except Exception as e:
            logger.warning(f"  Unexpected error during line adjustment: {e}")
            return False
    
    # ============================================================
    # Main processing method
    # ============================================================
    
    def process_font(self, font_path: str, new_name: Optional[str] = None) -> bool:
        """
        Process a single font file.
        
        Args:
            font_path: Path to the font file
            new_name: Optional new family name
            
        Returns:
            True if successful, False otherwise
        """
        logger.info(f"\nProcessing: {font_path}")
        
        # Load font
        try:
            font = TTFont(font_path)
        except Exception as e:
            logger.error(f"  Failed to open font: {e}")
            return False
        
        # Process font
        try:
            # Update names
            self.rename_font(font, new_name)
            self.update_unique_id(font, new_name)
            
            # Fix PANOSE
            self.check_and_fix_panose(font, font_path)
            
            # Handle kerning
            kern_pairs = self.extract_kern_pairs(font)
            if kern_pairs:
                written = self.add_legacy_kern(font, kern_pairs)
                logger.info(
                    f"  Kerning: extracted {len(kern_pairs)} pairs; "
                    f"wrote {written} to legacy 'kern' table"
                )
            else:
                logger.info("  Kerning: no GPOS kerning found")
            
            # Generate output filename
            output_path = self._generate_output_path(font_path, new_name)
            
            # Save modified font
            font.save(output_path)
            logger.info(f"  Saved: {output_path}")
            
            # Apply line adjustments
            self.apply_line_adjustment(output_path)
            
            return True
            
        except Exception as e:
            logger.error(f"  Processing failed: {e}")
            return False
    
    def _generate_output_path(self, original_path: str, new_name: Optional[str]) -> str:
        """Generate the output path for the processed font."""
        dirname = os.path.dirname(original_path)
        original_name, ext = os.path.splitext(os.path.basename(original_path))
        
        # Detect style suffix
        suffix = ""
        for valid_suffix in VALID_SUFFIXES:
            if original_name.endswith(valid_suffix):
                suffix = valid_suffix
                break
        
        # Build new filename
        if new_name:
            base_name = f"{self.prefix}_{new_name.replace(' ', '_')}{suffix}"
        else:
            base_name = f"{self.prefix}_{original_name}"
        
        return os.path.join(dirname, f"{base_name}{ext.lower()}")


def validate_font_files(font_paths: List[str]) -> Tuple[List[str], List[str]]:
    """
    Validate font files for processing.
    
    Args:
        font_paths: List of font file paths
        
    Returns:
        Tuple of (valid_files, invalid_files)
    """
    valid_files = []
    invalid_files = []
    
    for path in font_paths:
        if not os.path.isfile(path):
            logger.warning(f"File not found: {path}")
            continue
        
        if not path.lower().endswith(SUPPORTED_EXTENSIONS):
            logger.warning(f"Unsupported file type: {path}")
            continue
        
        # Check for valid suffix
        basename = os.path.basename(path)
        has_valid_suffix = any(
            suffix in basename for suffix in VALID_SUFFIXES
        )
        
        if has_valid_suffix:
            valid_files.append(path)
        else:
            invalid_files.append(basename)
    
    return valid_files, invalid_files


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Process fonts for Kobo e-readers: add prefix, kern table, "
                   "PANOSE validation, and line adjustments.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s font-Regular.ttf font-Bold.ttf
  %(prog)s --name "My Font" *.ttf
  %(prog)s --prefix KOBO --line-percent 25 font.ttf
        """
    )
    
    parser.add_argument(
        "fonts", 
        nargs="+", 
        help="Font files to process (*.ttf, *.otf)"
    )
    parser.add_argument(
        "--name", 
        type=str, 
        help="Optional new family name for all fonts"
    )
    parser.add_argument(
        "--prefix", 
        type=str, 
        default=DEFAULT_PREFIX,
        help=f"Prefix to add to font names (default: {DEFAULT_PREFIX})"
    )
    parser.add_argument(
        "--line-percent", 
        type=int, 
        default=DEFAULT_LINE_PERCENT,
        help=f"Line spacing adjustment percentage (default: {DEFAULT_LINE_PERCENT})"
    )
    parser.add_argument(
        "--verbose", 
        action="store_true",
        help="Enable verbose output"
    )
    
    args = parser.parse_args()
    
    # Configure logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Validate files
    valid_files, invalid_files = validate_font_files(args.fonts)
    
    if invalid_files:
        logger.error("\nERROR: The following fonts have invalid filenames:")
        logger.error("(Must end with -Regular, -Bold, -Italic, or -BoldItalic)")
        for filename in invalid_files:
            logger.error(f"  {filename}")
        
        if not valid_files:
            sys.exit(1)
        
        response = input("\nContinue with valid files only? [y/N]: ")
        if response.lower() != 'y':
            sys.exit(1)
    
    if not valid_files:
        logger.error("No valid font files to process")
        sys.exit(1)
    
    # Process fonts
    processor = FontProcessor(
        prefix=args.prefix,
        line_percent=args.line_percent
    )
    
    success_count = 0
    for font_path in valid_files:
        if processor.process_font(
            font_path, 
            args.name, 
        ):
            success_count += 1
    
    # Summary
    logger.info(f"\n{'='*50}")
    logger.info(f"Processed {success_count}/{len(valid_files)} fonts successfully")
    
    if success_count < len(valid_files):
        sys.exit(1)


if __name__ == "__main__":
    main()