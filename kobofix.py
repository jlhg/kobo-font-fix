import sys
import os
import subprocess
import argparse
from collections import defaultdict
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables._k_e_r_n import KernTable_format_0

# ------------------------------------------------------------
# Kerning extraction
# ------------------------------------------------------------

def _pair_value_to_kern(v1, v2):
    """Compute a legacy kerning value from a GPOS PairValue (Value1/Value2).
    Prefer XAdvance adjustments; if none, fall back to XPlacement.
    Returns an int (may be negative). """
    val = 0
    if v1 is not None:
        val += getattr(v1, "XAdvance", 0) or 0
    if v2 is not None:
        val += getattr(v2, "XAdvance", 0) or 0
    if val == 0:
        # Some fonts encode kerning via placements only
        if v1 is not None:
            val += getattr(v1, "XPlacement", 0) or 0
        if v2 is not None:
            val += getattr(v2, "XPlacement", 0) or 0
    return int(val or 0)


def extract_kern_pairs(font):
    """Extract kerning pairs from GPOS PairPos lookups (Format 1 & 2).

    Returns:
        dict[(leftGlyphName, rightGlyphName)] -> int kerning value
    Safe against missing GPOS or unexpected structures.
    """
    pairs = defaultdict(int)

    if "GPOS" not in font:
        return {}

    gpos = font["GPOS"].table
    lookup_list = getattr(gpos, "LookupList", None)
    if not lookup_list or not lookup_list.Lookup:
        return {}

    for lookup in lookup_list.Lookup:
        if getattr(lookup, "LookupType", None) != 2:  # Pair Adjustment
            continue
        for subtable in getattr(lookup, "SubTable", []):
            fmt = getattr(subtable, "Format", None)
            # -------- PairPos Format 1: per-glyph PairSets --------
            if fmt == 1:
                coverage = getattr(subtable, "Coverage", None)
                pair_sets = getattr(subtable, "PairSet", [])
                if not coverage or not hasattr(coverage, "glyphs"):
                    continue
                cov_glyphs = coverage.glyphs
                for i, left in enumerate(cov_glyphs):
                    if i >= len(pair_sets):
                        break
                    for rec in getattr(pair_sets[i], "PairValueRecord", []):
                        right = rec.SecondGlyph
                        k = _pair_value_to_kern(rec.Value1, rec.Value2)
                        if k:
                            pairs[(left, right)] += k
            # -------- PairPos Format 2: class-based --------
            elif fmt == 2:
                coverage = getattr(subtable, "Coverage", None)
                class_def1 = getattr(subtable, "ClassDef1", None)
                class_def2 = getattr(subtable, "ClassDef2", None)
                class1_records = getattr(subtable, "Class1Record", [])

                if not coverage or not hasattr(coverage, "glyphs"):
                    continue
                cov_glyphs = coverage.glyphs

                # Build glyph lists per class for the left side, limited to covered glyphs
                class1_map = getattr(class_def1, "classDefs", {}) if class_def1 else {}
                left_by_class = defaultdict(list)
                for g in cov_glyphs:
                    c = class1_map.get(g, 0)
                    left_by_class[c].append(g)

                # Build glyph lists per class for the right side from explicit definitions only
                class2_map = getattr(class_def2, "classDefs", {}) if class_def2 else {}
                right_by_class = defaultdict(list)
                for g, c in class2_map.items():
                    right_by_class[c].append(g)

                for c1, c1rec in enumerate(class1_records):
                    lefts = left_by_class.get(c1, [])
                    if not lefts:
                        continue
                    for c2, c2rec in enumerate(c1rec.Class2Record):
                        rights = right_by_class.get(c2, [])
                        if not rights:
                            continue
                        k = _pair_value_to_kern(c2rec.Value1, c2rec.Value2)
                        if not k:
                            continue
                        for L in lefts:
                            for R in rights:
                                pairs[(L, R)] += k
            else:
                # Other formats not handled
                continue

    return dict(pairs)


# ------------------------------------------------------------
# Legacy 'kern' table builder
# ------------------------------------------------------------

def add_legacy_kern(font, kern_pairs):
    """Create/replace a legacy 'kern' table with the supplied pairs.
    """
    if not kern_pairs:
        # Remove existing legacy 'kern' if present? We'll leave as-is.
        return 0

    kern_table = newTable("kern")
    kern_table.version = 0
    kern_table.kernTables = []

    subtable = KernTable_format_0()
    subtable.version = 0
    subtable.length = None  # recalculated by fontTools
    subtable.coverage = 1  # horizontal kerning, format 0
    # Ensure ints and glyph-name tuple keys
    subtable.kernTable = {tuple(k): int(v) for k, v in kern_pairs.items() if v}

    kern_table.kernTables.append(subtable)
    font["kern"] = kern_table
    return len(subtable.kernTable)


# ------------------------------------------------------------
# Name table updates
# ------------------------------------------------------------

def rename_font(font, prefix, new_name=None):
    """
    Prefix the font's family/full names with a given prefix.
    Optionally override the font name entirely using new_name.
    Updates name IDs:
      - 1: Family Name
      - 4: Full Name
      - 16: Typographic Family
    """
    if "name" not in font:
        return

    name_table = font["name"]
    ids_to_prefix = {1, 4, 16}

    for record in name_table.names:
        if record.nameID in ids_to_prefix:
            try:
                base_name = new_name if new_name else record.toUnicode()
                new_record_name = f"{prefix} {base_name}"
                record.string = new_record_name.encode(record.getEncoding())
            except Exception:
                # Fallback encoding if getEncoding fails
                try:
                    record.string = new_record_name.encode("utf_16_be")
                except Exception:
                    pass


def update_unique_id(font, prefix, new_name=None):
    """
    Automatically prefix the font's Unique ID (nameID 3) with a given prefix.
    Optionally override the font name using new_name.
    Preserves version info if present, otherwise sets a default version.
    Updates all records for all platforms/encodings.
    """
    if "name" not in font:
        return

    for record in font["name"].names:
        if record.nameID == 3:
            try:
                current_unique = record.toUnicode()
                # Preserve version info if present
                parts = current_unique.split("Version")
                version_info = "Version" + parts[1] if len(parts) == 2 else "Version 1.000"
                base_name = new_name if new_name else parts[0].strip()
                new_unique_id = f"{prefix} {base_name}:{version_info}"
                record.string = new_unique_id.encode(record.getEncoding())
            except Exception:
                # Fallback encoding
                try:
                    record.string = new_unique_id.encode("utf_16_be")
                except Exception:
                    pass


# ------------------------------------------------------------
# PANOSE check & fix
# ------------------------------------------------------------

def check_and_fix_panose(font, filename):
    """Check and adjust PANOSE based on filename suffix.

    Expected suffixes: -Regular, -Bold, -Italic, -BoldItalic
    Adjusts bWeight for Bold/Regular and bLetterForm for Italic/Regular.
    Prints status and corrections performed.
    """
    # Order matters: test BoldItalic before Bold/Italic
    expected_styles = (
        ("-BoldItalic", {"weight": 8, "letterform": 3}),
        ("-Bold", {"weight": 8, "letterform": 2}),
        ("-Italic", {"weight": 5, "letterform": 3}),
        ("-Regular", {"weight": 5, "letterform": 2}),
    )

    base = os.path.basename(filename)
    matched = False

    if "OS/2" not in font:
        print("  WARNING: No OS/2 table found; skipping PANOSE check.")
        return

    if not hasattr(font["OS/2"], "panose") or font["OS/2"].panose is None:
        print("  WARNING: Font has no PANOSE information; skipping PANOSE check.")
        return

    panose = font["OS/2"].panose

    for suffix, expected in expected_styles:
        if base.endswith(suffix + ".ttf") or base.endswith(suffix + ".otf"):
            matched = True
            exp_w = expected["weight"]
            exp_lf = expected["letterform"]
            cur_w = getattr(panose, "bWeight", None)
            cur_lf = getattr(panose, "bLetterForm", None)

            changes = []
            if cur_w != exp_w and exp_w is not None:
                panose.bWeight = exp_w
                changes.append(f"bWeight {cur_w}→{exp_w}")
            if cur_lf != exp_lf and exp_lf is not None:
                panose.bLetterForm = exp_lf
                changes.append(f"bLetterForm {cur_lf}→{exp_lf}")

            if changes:
                print(f"  PANOSE corrected for {suffix}: " + ", ".join(changes))
            else:
                print(f"  PANOSE check passed for {suffix}.")
            break

    if not matched:
        print(
            "  WARNING: Filename does not end with expected suffix "
            "(-Regular, -Bold, -Italic, -BoldItalic). PANOSE check skipped."
        )


# ------------------------------------------------------------
# Orchestration per font
# ------------------------------------------------------------

def process_font(path, new_name):
    """Load, process, and save the font.

    Steps (each independent):
      1) Prefix names with prefix.
      2) Check & fix PANOSE based on filename.
      3) Extract kerning from GPOS and write a legacy 'kern' table.
      4) Save as PREFIX_<original>.<ext>
    """
    print(f"Processing: {path}")
    try:
        font = TTFont(path)
    except Exception as e:
        print(f"  ERROR: Failed to open font: {e}")
        return

    # Set up a prefix
    prefix = "KF"

    # Always run name prefix & PANOSE checks, regardless of kerning outcome
    rename_font(font, prefix, new_name)
    update_unique_id(font, prefix, new_name)
    check_and_fix_panose(font, os.path.basename(path))

    # Extract kerning (robust against missing/odd structures)
    try:
        kern_pairs = extract_kern_pairs(font)
        pair_count = len(kern_pairs)
        if pair_count:
            written = add_legacy_kern(font, kern_pairs)
            print(f"  Kerning: extracted {pair_count} pairs; wrote {written} pairs to legacy 'kern'.")
        else:
            print("  Kerning: no GPOS kerning found; skipping legacy 'kern' table.")
    except Exception as e:
        print(f"  WARNING: Failed to extract/add kerning: {e}")

    # Save the font with prefix, optional new name, and preserve style suffix
    dirname, _ = os.path.split(path)
    original_name, ext = os.path.splitext(os.path.basename(path))

    # Detect the style suffix
    valid_suffixes = ("-Regular", "-Bold", "-Italic", "-BoldItalic")
    suffix = next((s for s in valid_suffixes if original_name.endswith(s)), "")

    # Determine base name for the file
    if new_name:
        # Replace spaces with underscores for filenames
        base_name = f"{prefix}_{new_name.replace(' ', '_')}{suffix}"
    else:
        # Keep original name but add prefix
        base_name = f"{prefix}_{original_name}"

    # Construct the full output path
    out_path = os.path.join(dirname, f"{base_name}{ext.lower()}")

    
    try:
        font.save(out_path)
        print(f"  Saved: {out_path}")

        # Run font-line adjustment in-place
        try:
            subprocess.run(["font-line", "percent", "20", out_path], check=True, stdout=subprocess.DEVNULL)
            # Determine the expected linegap filename
            base, ext = os.path.splitext(out_path)
            linegap_file = f"{base}-linegap20{ext}"

            # Remove the original font
            if os.path.exists(out_path):
                os.remove(out_path)

            # Rename the linegap file back to the original output path
            if os.path.exists(linegap_file):
                os.rename(linegap_file, out_path)
                print("  font-line applied successfully (20% baseline shift).")
            else:
                print(f"  WARNING: expected font-line output '{linegap_file}' not found.")
        except FileNotFoundError:
            print("  ERROR: font-line utility not found. Please install it first (see README). Aborting.")
            sys.exit(1)
        except Exception as e:
            print(f"  WARNING: font-line failed: {e}")
    except Exception as e:
        print(f"  ERROR: Failed to save font: {e}")

# ------------------------------------------------------------
# CLI
# ------------------------------------------------------------

def main():
    import argparse

    # --------------------------
    # Parse command-line arguments
    # --------------------------
    parser = argparse.ArgumentParser(
        description="Process fonts: add KC prefix, kern table, PANOSE validation, line adjustments."
    )
    parser.add_argument(
        "fonts", nargs="+", help="Font files to process (*.ttf, *.otf)"
    )
    parser.add_argument(
        "--name", type=str, help="Optional new family name for all fonts"
    )
    args = parser.parse_args()

    # --------------------------
    # Validate filenames
    # --------------------------
    invalid_files = []
    valid_suffixes = ("-Regular", "-Bold", "-Italic", "-BoldItalic")

    for path in args.fonts:
        if os.path.isfile(path) and path.lower().endswith((".ttf", ".otf")):
            base = os.path.basename(path)
            if not base.endswith(tuple(s + ext for s in valid_suffixes for ext in (".ttf", ".otf"))):
                invalid_files.append(base)
        else:
            print(f"Skipping non-TTF/OTF file: {path}")

    if invalid_files:
        print(
            "ERROR: The following fonts have invalid filenames (must end with -Regular, -Bold, -Italic, or -BoldItalic):"
        )
        for f in invalid_files:
            print("  " + f)
        sys.exit(1)

    # --------------------------
    # Process each font
    # --------------------------
    for path in args.fonts:
        if os.path.isfile(path) and path.lower().endswith((".ttf", ".otf")):
            process_font(path, new_name=args.name)


if __name__ == "__main__":
    main()
