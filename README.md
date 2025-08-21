# KoboFix Font Processor

## Overview

`kobofix.py` is a Python script designed to process TTF and OTF fonts for Kobo e-readers. 

It generates a renamed font, fixes PANOSE information based on the filename, adjusts the baseline with the `font-line` utility, and adds a legacy `kern` table which allows the `kepub` engine for improved rendering of kerned pairs.

You can use this to modify or fix your own, legally acquired fonts (assuming you are permitted to do so).

## Requirements

Python 3, FontTools, `font-line`.

You can install them like so:


```bash
pip3 install fonttools
pip3 install font-line
```

On macOS, if you're using the built-in version of Python (via Xcode), you may need to first add a folder to your `PATH` to make `font-line` available, like:

```bash
echo 'export PATH="$HOME/Library/Python/3.9/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

## Usage

1. Open a terminal and navigate to the directory containing your font files.
2. Run the script with a glob pattern to include all TTF/OTF files:

   ```bash
   python3 kobofix.py *.ttf
   ```
3. The script will:

   * Validate filenames.
   * Process each font (e.g. "Lora" becomes "KF Lora").
   * Apply kerning, rename, PANOSE adjustments, and baseline shift.
   * Save output as `KF_<original_filename>`.

Example:

```
Original: Lora-BoldItalic.ttf
Processed: KF_Lora-BoldItalic.ttf
```
