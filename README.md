# Kobo Font Fix

## Overview

`kobofix.py` is a Python script designed to process TTF fonts for Kobo e-readers. 

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
2. Run the script with a glob pattern to include all TTF files:

   ```bash
   python3 kobofix.py *.ttf
   ```
3. The default script will:

   * Validate the file names (must end with `-Regular`, `-Bold`, `-Italic` or `-BoldItalic` so they're valid for Kobo devices).
   * Process each font (e.g. "Lora" becomes "KF Lora").
   * Apply kerning, rename, PANOSE adjustments, and baseline shift.
   * Save output as `KF_<original_filename>`.

You can customize what the script does.

## Customization

### Generating KF fonts

This applies the KF prefix, applies 20 percent line spacing and adds a Kobo `kern` table. Ideal if you have an existing TrueType font and you want it on your Kobo device.

The `--name` parameter is used to change the name of the font family.

```bash
./kobofix.py --prefix KF --name="Fonty" --line-percent 20 *.ttf
```

To process fonts from my [ebook-fonts](https://github.com/nicoverbruggen/ebook-fonts) collection which are prefixed with "NV", you can replace the prefix and make adjustments in bulk. 

To process all fonts with the "Kobo Fix" preset, simply run:

```bash
./kobofix.py --prefix KF --remove-prefix="NV" --line-percent 0 *.ttf
```

(In this case, we'll set --line-percent to 0 so the line height changes aren't made, because the fonts in the NV Collection should already have those changes applied.)

### Generating NV fonts

Tight spacing, with a custom font family name:

```bash
./kobofix.py --prefix NV --name="Fonty" --line-percent 20 --skip-kobo-kern *.ttf
```

Relaxed spacing, with a custom font family name:

```bash
./kobofix.py --prefix NV --name="Fonty" --line-percent 50 --skip-kobo-kern *.ttf
```

You can play around with `--line-percent` to see what works for you.
