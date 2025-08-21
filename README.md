# KoboFix Font Processor

## Overview

`kobofix.py` is a Python script designed to process TTF and OTF fonts for Kobo e-readers. 

It generates a renamed font, fixes PANOSE information based on the filename, adjusts the baseline with the `font-line` utility, and adds a legacy `kern` table which allows the `kepub` engine for improved rendering of kerned pairs.

## Requirements

* **Python 3.8+**
* **FontTools**

```bash
pip3 install fonttools
```
* **font-line** utility

```bash
pip3 install font-line
```

## Usage

1. Open a terminal and navigate to the directory containing your font files.
2. Run the script with a glob pattern to include all TTF/OTF files:

   ```bash
   python3 kobofix.py *.ttf
   ```
3. The script will:

   * Validate filenames.
   * Process each font.
   * Apply kerning, rename, PANOSE adjustments, and baseline shift.
   * Save output as `KC_<original_filename>`.

Example:

```
Original: Lora-BoldItalic.ttf
Processed: KC_Lora-BoldItalic.ttf
```
