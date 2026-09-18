# PDF Redaction

Offline Windows desktop app to permanently redact PDFs. Marked areas are painted onto a raster page and saved in a new PDF, so the original text cannot be recovered.

## Download

### Windows (available now)

[Download PDF Redaction for Windows](https://github.com/shruti01-dev/pdf-redaction/releases/latest/download/PDF-Redaction-Setup.exe)

1. Download the Setup file
2. Run it → Next → Install (no admin password)
3. Open **PDF Redaction** from the desktop
4. Upload a PDF, mark redactions, then export

### Mac

Coming next. Not available yet.

## Run from source

```bash
pip install -r requirements.txt
python PDFRedaction.py
```

## Build Windows installer

1. Install [Inno Setup 6](https://jrsoftware.org/isinfo.php) if needed: `winget install --id JRSoftware.InnoSetup -e`
2. Double-click `build-installer.bat`

Output:

```text
installer_output/PDF-Redaction-Setup.exe
```

## What is in this repo

**Users** only need the Setup.exe from [Releases](https://github.com/shruti01-dev/pdf-redaction/releases/latest).

**Developers** need:

- `PDFRedaction.py` — app
- `requirements.txt` — PyQt5, PyMuPDF, Pillow
- `pdf_redaction.spec` — PyInstaller build
- `build-exe.bat` / `build-installer.bat` — Windows build
- `installer/pdf_redaction.iss` — Setup.exe
- `assets/` — icon
