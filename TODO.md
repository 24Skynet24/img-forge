You are a senior Python developer. Build a complete, production-quality Windows desktop application called "ImgForge" — an image converter and compressor with a modern GUI.

## Tech stack
- Python 3.11+
- GUI: PySide6 (Qt 6)
- Image processing: Pillow (+ pillow-heif for HEIC/HEIF input, AVIF support via Pillow or pillow-avif-plugin)
- PNG lossy compression: libimagequant (via the `imagequant` package) or bundled pngquant.exe
- PNG lossless optimization: oxipng (via `pyoxipng`)
- JPEG optimization: mozjpeg (via `mozjpeg-lossless-optimization`) or Pillow with optimize=True, progressive=True
- Packaging: PyInstaller → a single portable .exe, all dependencies bundled, no installation required

## Core features

### 1. Three processing modes (user selects one)
1. **Compress only** — keep the original format, reduce file size with no visible quality loss (like tinypng.com).
2. **Convert only** — change format without extra compression (use high quality settings).
3. **Convert + Compress** — change format and optimize the result in one pass.

Supported formats:
- Input: PNG, JPEG/JPG, WebP, AVIF, GIF, BMP, TIFF, HEIC/HEIF
- Output: PNG, JPEG, WebP, AVIF, GIF, BMP, TIFF

### 2. Compression ("visually lossless")
- PNG: palette quantization with dithering (libimagequant, quality range ~65–90), then oxipng optimization. Preserve transparency.
- JPEG: mozjpeg-level encoding, quality ~80–85, progressive, optimized Huffman tables, 4:2:0 subsampling.
- WebP / AVIF: quality ~80 with method/effort set to max.
- Compression level slider: "Maximum quality" / "Balanced" (default) / "Smallest size".
- In Compress-only mode, if the result is larger than the original, keep the original file unchanged (copy it) and mark it as "already optimized".

### 3. Correct conversion handling
- Transparency → JPEG/BMP (no alpha): flatten onto a background color (default white, user-selectable).
- Animated GIF/WebP: preserve all frames and timings when the target format supports animation; otherwise take the first frame and warn the user.
- Apply EXIF orientation before processing so photos are never rotated incorrectly.
- Preserve ICC color profiles (unless metadata removal is on — then convert to sRGB first so colors stay the same).
- CMYK, 16-bit, palette and grayscale images must be handled without crashes.

### 4. Input: files AND folders
- Drag & drop onto the window, or "Add files" / "Add folder" buttons.
- Accept any mix of individual images and folders with any depth of nested subfolders.
- Recursively find all supported images; silently skip non-image files (show count of skipped files).
- Show a list/table of queued items with thumbnails, name, relative path, format, size.
- Allow removing items from the queue and clearing the queue.

### 5. Output: same structure, saved where the user chooses
- Processing happens into a temporary working directory — originals are NEVER modified or overwritten.
- After processing completes, show a "Save / Download" button. Clicking it opens the native Windows Explorer folder picker; the user chooses where to save.
- The output must mirror the input structure exactly: if the user added a folder "Photos" with nested subfolders, they get a folder "Photos" with the same subfolders and processed images inside (file extensions changed if converted). Loose individual files are saved directly into the chosen location.
- If a file/folder with the same name already exists at the destination, ask: Overwrite / Rename (add suffix like "_1") / Skip.
- After saving, offer "Open folder" button.

### 6. No limits
- No limits on number of files, file size, image resolution or folder depth.
- Disable Pillow's decompression bomb limit (Image.MAX_IMAGE_PIXELS = None).
- Process in parallel using a worker pool (ProcessPoolExecutor, number of workers = CPU cores, configurable).
- The UI must never freeze: run all processing in background workers, communicate via Qt signals.
- Handle thousands of files efficiently (lazy thumbnail loading, virtualized list).
- Overall progress bar + per-file status, elapsed time, ETA, and a Cancel button that stops safely.

### 7. Before / After comparison
- Select any processed image to open a comparison view with a draggable vertical split slider (original on the left, result on the right).
- Support zoom (mouse wheel) and pan, synchronized on both sides, including 100% pixel view.
- Show original size, new size, % saved, dimensions and format for both.

### 8. Metadata removal
- Checkbox "Remove metadata (EXIF, GPS, camera info)". Default: ON.
- When OFF, preserve EXIF and ICC where the target format supports it.

### 9. Results & errors
- Results table: file, original size, new size, saved %, status (OK / Already optimized / Error).
- Summary: total files, total size before → after, total saved (MB and %).
- A broken or unsupported file must never crash the app — mark it as an error with a readable reason and continue. Provide an "Export log" button.

### 10. UI / UX
- Clean, modern design; dark and light themes with a toggle (default: follow Windows system theme), remember the choice.
- Interface language: Russian.
- Remember last used settings (mode, output format, quality level, background color, metadata option) between launches via QSettings.
- Clear empty state: big drop zone "Перетащите фото или папки сюда".
- Keyboard shortcuts: Ctrl+O (add files), Ctrl+Shift+O (add folder), Ctrl+Enter (start), Ctrl+S (save), Delete (remove selected).

## Code quality requirements
- Clean architecture: separate the processing core (no Qt imports, fully testable) from the GUI layer.
- Suggested structure:
  imgforge/
    core/ (formats.py, compressor.py, converter.py, scanner.py, pipeline.py)
    gui/ (main_window.py, compare_view.py, widgets/, themes/)
    main.py
  tests/
  requirements.txt
  build.spec (PyInstaller)
  README.md
- Type hints everywhere, docstrings for public functions.
- Unit tests (pytest) for the core: every input→output format pair, transparency flattening, animation, EXIF orientation, nested folder structure mirroring, "result larger than original" fallback, corrupted file handling.
- README with: how to run from source, how to build the .exe, and a screenshot placeholder.

## Deliverables & workflow
1. First, briefly present the architecture and the list of files you will create.
2. Then write ALL files in full — no placeholders, no "TODO", no omitted code.
3. Finish with exact commands to install dependencies, run the app, run the tests, and build the single .exe.