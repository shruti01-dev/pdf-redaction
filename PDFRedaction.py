"""
==============================================================================
                            Pdf Redaction App
==============================================================================
A secure, fully-offline PDF redaction tool.

Security model
--------------
Every page selected for export is rendered to a raster image, solid black
rectangles are painted on top of the pixels at the redacted regions, and a
NEW PDF is built in which each page is the redacted image. The original
text/vector content is completely discarded — there is no underlying layer
to "un-redact". Document metadata is also stripped.

Run it
------
From source:  python PDFRedaction.py
Windows app:  run PDF-Redaction-Setup.exe (see build-installer.bat)

The first source run will auto-install PyQt5, PyMuPDF, and Pillow if they
are missing. The packaged desktop app needs no Python install.
==============================================================================
"""

# ===========================================================================
#                            AUTO-INSTALLER
# ===========================================================================
import sys
import subprocess
import importlib


def _ensure(module_name: str, pip_name: str = None) -> None:
    """Import a module, installing it via pip if missing.

    Skip when frozen as a desktop .exe — dependencies are already bundled.
    """
    if getattr(sys, "frozen", False):
        return
    pip_name = pip_name or module_name
    try:
        importlib.import_module(module_name)
    except ImportError:
        print(f"[Pdf Redaction App] Installing missing package: {pip_name} ...")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "--quiet", pip_name]
            )
        except subprocess.CalledProcessError as e:
            print(f"[Pdf Redaction App] Failed to install {pip_name}: {e}")
            print("Please install it manually with:")
            print(f"    {sys.executable} -m pip install {pip_name}")
            sys.exit(1)


# These must succeed before the rest of the file imports anything else.
_ensure("PyQt5", "PyQt5")
_ensure("fitz", "PyMuPDF")
_ensure("PIL", "Pillow")


# ===========================================================================
#                          STANDARD & 3RD-PARTY IMPORTS
# ===========================================================================
import os
import io
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import fitz  # PyMuPDF
from PIL import Image, ImageDraw

from PyQt5.QtCore import Qt, QRectF, QPointF
from PyQt5.QtGui import (
    QPixmap, QImage, QPainter, QPen, QBrush, QColor, QKeySequence, QIcon,
)
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QMessageBox, QGraphicsView,
    QGraphicsScene, QGraphicsRectItem, QLineEdit, QSpinBox, QStatusBar,
    QProgressDialog, QFrame, QShortcut,
)


APP_NAME = "PDF Redaction"
APP_VERSION = "1.0"


def _app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def _app_icon_path() -> Path:
    return _app_base_dir() / "assets" / "app.ico"


def _apply_window_icon(target) -> None:
    icon_path = _app_icon_path()
    if icon_path.is_file():
        target.setWindowIcon(QIcon(str(icon_path)))


# ===========================================================================
#                              DATA MODEL
# ===========================================================================
@dataclass
class Redaction:
    """A redaction rectangle stored in PDF coordinate space (points, 72/inch)."""
    page: int
    x0: float
    y0: float
    x1: float
    y1: float

    def normalized(self) -> "Redaction":
        x0, x1 = sorted([self.x0, self.x1])
        y0, y1 = sorted([self.y0, self.y1])
        return Redaction(self.page, x0, y0, x1, y1)


# ===========================================================================
#                            PDF VIEW WIDGET
# ===========================================================================
class PdfView(QGraphicsView):
    """A zoomable, scrollable view of a single PDF page with rectangle selection."""

    DISPLAY_DPI = 120  # on-screen rendering resolution

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene_obj = QGraphicsScene(self)
        self.setScene(self.scene_obj)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setBackgroundBrush(QBrush(QColor(30, 35, 48)))
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)

        self._pixmap_item = None
        self._scale = 1.0

        self._drawing = False
        self._start_pos: Optional[QPointF] = None
        self._current_rect_item: Optional[QGraphicsRectItem] = None

        # Callback hook: (x0, y0, x1, y1) in PDF coordinates
        self.on_redaction_drawn = None

    # -------- public API --------
    def load_pixmap(self, pixmap: QPixmap) -> None:
        self.scene_obj.clear()
        self._pixmap_item = self.scene_obj.addPixmap(pixmap)
        self.scene_obj.setSceneRect(QRectF(pixmap.rect()))
        self._current_rect_item = None
        self._drawing = False

    def draw_redactions(self, redactions: List[Redaction]) -> None:
        if self._pixmap_item is None:
            return
        # Remove existing overlay items
        for item in list(self.scene_obj.items()):
            if item is not self._pixmap_item:
                self.scene_obj.removeItem(item)
        scale = self.DISPLAY_DPI / 72.0
        pen = QPen(QColor(239, 68, 68), 2)
        brush = QBrush(QColor(239, 68, 68, 110))
        for r in redactions:
            x = r.x0 * scale
            y = r.y0 * scale
            w = (r.x1 - r.x0) * scale
            h = (r.y1 - r.y0) * scale
            item = QGraphicsRectItem(x, y, w, h)
            item.setPen(pen)
            item.setBrush(brush)
            self.scene_obj.addItem(item)

    def set_zoom(self, factor: float) -> None:
        self.resetTransform()
        self._scale = factor
        self.scale(factor, factor)

    # -------- mouse handling --------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._pixmap_item is not None:
            scene_pos = self.mapToScene(event.pos())
            if self._pixmap_item.boundingRect().contains(scene_pos):
                self._drawing = True
                self._start_pos = scene_pos
                pen = QPen(QColor(34, 197, 94), 2, Qt.DashLine)
                brush = QBrush(QColor(34, 197, 94, 80))
                self._current_rect_item = QGraphicsRectItem(
                    scene_pos.x(), scene_pos.y(), 0, 0
                )
                self._current_rect_item.setPen(pen)
                self._current_rect_item.setBrush(brush)
                self.scene_obj.addItem(self._current_rect_item)
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drawing and self._current_rect_item is not None:
            scene_pos = self.mapToScene(event.pos())
            x = min(self._start_pos.x(), scene_pos.x())
            y = min(self._start_pos.y(), scene_pos.y())
            w = abs(scene_pos.x() - self._start_pos.x())
            h = abs(scene_pos.y() - self._start_pos.y())
            self._current_rect_item.setRect(x, y, w, h)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drawing and event.button() == Qt.LeftButton:
            self._drawing = False
            if self._current_rect_item is not None:
                rect = self._current_rect_item.rect()
                self.scene_obj.removeItem(self._current_rect_item)
                self._current_rect_item = None
                if rect.width() > 3 and rect.height() > 3:
                    scale = self.DISPLAY_DPI / 72.0
                    x0 = rect.x() / scale
                    y0 = rect.y() / scale
                    x1 = (rect.x() + rect.width()) / scale
                    y1 = (rect.y() + rect.height()) / scale
                    if self.on_redaction_drawn:
                        self.on_redaction_drawn(x0, y0, x1, y1)
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        # Ctrl + scroll = zoom
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            factor = 1.15 if delta > 0 else 1 / 1.15
            new_scale = max(0.2, min(5.0, self._scale * factor))
            self.set_zoom(new_scale)
            if hasattr(self.window(), "zoom_label"):
                self.window().zoom_label.setText(f"{int(new_scale * 100)}%")
            return
        super().wheelEvent(event)


# ===========================================================================
#                              MAIN WINDOW
# ===========================================================================
class MainWindow(QMainWindow):
    EXPORT_DPI = 200  # resolution of the rasterized output PDF

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1280, 820)
        _apply_window_icon(self)

        self.pdf_doc: Optional[fitz.Document] = None
        self.pdf_path: Optional[str] = None
        self.current_page = 0
        self.redactions: List[Redaction] = []

        self._build_ui()
        self._apply_style()
        self._make_shortcuts()

    # ---------------------------- UI ----------------------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # -------- Header bar --------
        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(72)
        hb = QHBoxLayout(header)
        hb.setContentsMargins(20, 10, 20, 10)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("🔒  Pdf Redaction App")
        title.setObjectName("title")
        subtitle = QLabel("SECURE  •  OFFLINE  •  PERMANENT")
        subtitle.setObjectName("subtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        hb.addLayout(title_box)
        hb.addStretch()

        self.btn_open = QPushButton("📂  Upload PDF")
        self.btn_open.setObjectName("primary")
        self.btn_open.clicked.connect(self.open_pdf)
        hb.addWidget(self.btn_open)

        self.btn_export = QPushButton("💾  Export Redacted PDF")
        self.btn_export.setObjectName("success")
        self.btn_export.clicked.connect(self.export_pdf)
        hb.addWidget(self.btn_export)

        outer.addWidget(header)

        # -------- Toolbar --------
        tools = QFrame()
        tools.setObjectName("tools")
        tools.setFixedHeight(60)
        tb = QHBoxLayout(tools)
        tb.setContentsMargins(14, 10, 14, 10)
        tb.setSpacing(8)

        # Page navigation
        self.btn_prev = QPushButton("◀")
        self.btn_prev.setObjectName("nav")
        self.btn_prev.setToolTip("Previous page (←)")
        self.btn_prev.clicked.connect(self.prev_page)
        tb.addWidget(self.btn_prev)

        self.page_input = QSpinBox()
        self.page_input.setMinimum(1)
        self.page_input.setMaximum(1)
        self.page_input.setFixedWidth(70)
        self.page_input.valueChanged.connect(self._on_page_input)
        tb.addWidget(self.page_input)

        self.page_total = QLabel("/ 0")
        self.page_total.setObjectName("muted")
        tb.addWidget(self.page_total)

        self.btn_next = QPushButton("▶")
        self.btn_next.setObjectName("nav")
        self.btn_next.setToolTip("Next page (→)")
        self.btn_next.clicked.connect(self.next_page)
        tb.addWidget(self.btn_next)

        tb.addWidget(self._sep())

        # Zoom
        self.btn_zoom_out = QPushButton("➖")
        self.btn_zoom_out.setObjectName("nav")
        self.btn_zoom_out.setToolTip("Zoom out (Ctrl + -)")
        self.btn_zoom_out.clicked.connect(self.zoom_out)
        tb.addWidget(self.btn_zoom_out)

        self.zoom_label = QLabel("100%")
        self.zoom_label.setFixedWidth(56)
        self.zoom_label.setAlignment(Qt.AlignCenter)
        self.zoom_label.setObjectName("muted")
        tb.addWidget(self.zoom_label)

        self.btn_zoom_in = QPushButton("➕")
        self.btn_zoom_in.setObjectName("nav")
        self.btn_zoom_in.setToolTip("Zoom in (Ctrl + +)")
        self.btn_zoom_in.clicked.connect(self.zoom_in)
        tb.addWidget(self.btn_zoom_in)

        self.btn_zoom_fit = QPushButton("Fit")
        self.btn_zoom_fit.setObjectName("nav")
        self.btn_zoom_fit.setToolTip("Fit page to window (Ctrl + 0)")
        self.btn_zoom_fit.clicked.connect(self.zoom_fit)
        tb.addWidget(self.btn_zoom_fit)

        tb.addWidget(self._sep())

        # Find & Redact
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "🔍   Find text to redact   —   e.g. PAN, Aadhaar, email, mobile, account no."
        )
        self.search_input.returnPressed.connect(self.find_and_redact)
        tb.addWidget(self.search_input, 1)

        self.btn_find = QPushButton("Find & Redact")
        self.btn_find.setObjectName("warn")
        self.btn_find.clicked.connect(self.find_and_redact)
        tb.addWidget(self.btn_find)

        tb.addWidget(self._sep())

        # Undo / clear
        self.btn_undo = QPushButton("↶  Undo")
        self.btn_undo.setObjectName("ghost")
        self.btn_undo.setToolTip("Undo last redaction (Ctrl + Z)")
        self.btn_undo.clicked.connect(self.undo)
        tb.addWidget(self.btn_undo)

        self.btn_clear = QPushButton("🗑  Clear All")
        self.btn_clear.setObjectName("danger")
        self.btn_clear.clicked.connect(self.clear_all)
        tb.addWidget(self.btn_clear)

        outer.addWidget(tools)

        # -------- Hint banner --------
        hint = QFrame()
        hint.setObjectName("hint")
        hint.setFixedHeight(36)
        hl = QHBoxLayout(hint)
        hl.setContentsMargins(20, 6, 20, 6)
        hint_text = QLabel(
            "Tip:  Click and drag on the page to mark a redaction.  "
            "Hold Ctrl and scroll to zoom.  Marked areas will be permanently "
            "rasterized on export."
        )
        hint_text.setObjectName("hintText")
        hl.addWidget(hint_text)
        hl.addStretch()
        outer.addWidget(hint)

        # -------- Viewer --------
        self.viewer = PdfView()
        self.viewer.on_redaction_drawn = self._on_redaction_drawn
        outer.addWidget(self.viewer, 1)

        # -------- Status --------
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Ready.  Click 'Upload PDF' to begin.")
        self.redaction_count_label = QLabel("Redactions: 0")
        self.status.addPermanentWidget(self.redaction_count_label)

    def _sep(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.VLine)
        line.setObjectName("sep")
        line.setFixedHeight(28)
        return line

    def _make_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+O"), self, self.open_pdf)
        QShortcut(QKeySequence("Ctrl+S"), self, self.export_pdf)
        QShortcut(QKeySequence("Ctrl+Z"), self, self.undo)
        QShortcut(QKeySequence("Ctrl+F"), self, lambda: self.search_input.setFocus())
        QShortcut(QKeySequence(Qt.Key_Right), self, self.next_page)
        QShortcut(QKeySequence(Qt.Key_Left), self, self.prev_page)
        QShortcut(QKeySequence("Ctrl+="), self, self.zoom_in)
        QShortcut(QKeySequence("Ctrl++"), self, self.zoom_in)
        QShortcut(QKeySequence("Ctrl+-"), self, self.zoom_out)
        QShortcut(QKeySequence("Ctrl+0"), self, self.zoom_fit)

    def _apply_style(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background: #1a1f2e;
                color: #e6e9ef;
                font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
                font-size: 13px;
            }
            #header {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #6366f1, stop:0.5 #a855f7, stop:1 #ec4899);
            }
            #title {
                color: white;
                font-size: 22px;
                font-weight: 800;
                letter-spacing: 0.3px;
            }
            #subtitle {
                color: rgba(255,255,255,0.9);
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 2.5px;
            }
            #tools { background: #232a3d; border-bottom: 1px solid #2f3852; }
            #hint  { background: #1f2638; border-bottom: 1px solid #2a3148; }
            #hintText { color: #94a3b8; font-size: 12px; }
            #muted { color: #94a3b8; }
            #sep { color: #2f3852; }

            QPushButton {
                background: #2f3852;
                color: #e6e9ef;
                border: none;
                padding: 8px 14px;
                border-radius: 8px;
                font-weight: 600;
            }
            QPushButton:hover { background: #3d4869; }
            QPushButton:pressed { background: #262d44; }

            QPushButton#primary { background: #6366f1; color: white; padding: 10px 18px; font-weight: 700; }
            QPushButton#primary:hover  { background: #818cf8; }
            QPushButton#primary:pressed{ background: #4f46e5; }

            QPushButton#success { background: #10b981; color: white; padding: 10px 18px; font-weight: 700; }
            QPushButton#success:hover  { background: #34d399; }
            QPushButton#success:pressed{ background: #059669; }

            QPushButton#warn   { background: #f59e0b; color: #1a1f2e; font-weight: 700; }
            QPushButton#warn:hover  { background: #fbbf24; }
            QPushButton#warn:pressed{ background: #d97706; }

            QPushButton#danger { background: #ef4444; color: white; font-weight: 700; }
            QPushButton#danger:hover  { background: #f87171; }
            QPushButton#danger:pressed{ background: #dc2626; }

            QPushButton#nav    { background: #2f3852; min-width: 36px; padding: 8px 10px; }
            QPushButton#ghost  { background: transparent; border: 1px solid #3d4869; }
            QPushButton#ghost:hover { background: #2f3852; }

            QLineEdit, QSpinBox {
                background: #1a1f2e; color: #e6e9ef;
                border: 1px solid #3d4869;
                padding: 7px 10px; border-radius: 6px;
                selection-background-color: #6366f1;
            }
            QLineEdit:focus, QSpinBox:focus { border: 1px solid #818cf8; }

            QStatusBar { background: #232a3d; color: #cbd5e1; }
            QStatusBar::item { border: none; }

            QScrollBar:vertical { background: #232a3d; width: 12px; border: none; }
            QScrollBar::handle:vertical { background: #3d4869; border-radius: 6px; min-height: 30px; }
            QScrollBar::handle:vertical:hover { background: #6366f1; }
            QScrollBar:horizontal { background: #232a3d; height: 12px; border: none; }
            QScrollBar::handle:horizontal { background: #3d4869; border-radius: 6px; min-width: 30px; }
            QScrollBar::handle:horizontal:hover { background: #6366f1; }
            QScrollBar::add-line, QScrollBar::sub-line { background: none; border: none; }

            QMessageBox { background: #232a3d; }
            QMessageBox QLabel { color: #e6e9ef; }
        """)

    # ---------------------------- PDF management ----------------------------
    def open_pdf(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open PDF", "", "PDF Files (*.pdf);;All Files (*)"
        )
        if not path:
            return
        try:
            doc = fitz.open(path)
            if doc.needs_pass:
                doc.close()
                QMessageBox.warning(
                    self, "Password-protected PDF",
                    "This PDF is password-protected. Please remove the password and try again."
                )
                return
            if doc.page_count == 0:
                doc.close()
                raise ValueError("The PDF contains no pages.")

            if self.pdf_doc:
                self.pdf_doc.close()

            self.pdf_doc = doc
            self.pdf_path = path
            self.redactions = []
            self.current_page = 0

            self.page_input.blockSignals(True)
            self.page_input.setMaximum(doc.page_count)
            self.page_input.setValue(1)
            self.page_input.blockSignals(False)
            self.page_total.setText(f"/ {doc.page_count}")

            self.viewer.set_zoom(1.0)
            self.zoom_label.setText("100%")
            self.render_page()
            self.status.showMessage(
                f"Loaded:  {os.path.basename(path)}    •    {doc.page_count} page(s)"
            )
            self._update_counts()
        except Exception as e:
            QMessageBox.critical(self, "Cannot open PDF", f"Error: {e}")

    def render_page(self):
        if not self.pdf_doc:
            return
        try:
            page = self.pdf_doc[self.current_page]
            zoom = PdfView.DISPLAY_DPI / 72.0
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = QImage(
                pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888
            )
            # Detach from the pixmap buffer before pix is gc'd
            pixmap = QPixmap.fromImage(img.copy())
            self.viewer.load_pixmap(pixmap)
            self._refresh_overlay()
        except Exception as e:
            QMessageBox.critical(self, "Render error", f"Could not render page: {e}")

    def _refresh_overlay(self):
        page_redactions = [r for r in self.redactions if r.page == self.current_page]
        self.viewer.draw_redactions(page_redactions)

    def _update_counts(self):
        self.redaction_count_label.setText(f"Redactions: {len(self.redactions)}")

    # ---------------------------- Navigation ----------------------------
    def prev_page(self):
        if not self.pdf_doc or self.current_page <= 0:
            return
        self.current_page -= 1
        self.page_input.blockSignals(True)
        self.page_input.setValue(self.current_page + 1)
        self.page_input.blockSignals(False)
        self.render_page()

    def next_page(self):
        if not self.pdf_doc or self.current_page >= self.pdf_doc.page_count - 1:
            return
        self.current_page += 1
        self.page_input.blockSignals(True)
        self.page_input.setValue(self.current_page + 1)
        self.page_input.blockSignals(False)
        self.render_page()

    def _on_page_input(self, val: int):
        if not self.pdf_doc:
            return
        self.current_page = max(0, min(val - 1, self.pdf_doc.page_count - 1))
        self.render_page()

    # ---------------------------- Zoom ----------------------------
    def zoom_in(self):
        if not self.pdf_doc:
            return
        s = min(self.viewer._scale * 1.2, 5.0)
        self.viewer.set_zoom(s)
        self.zoom_label.setText(f"{int(s * 100)}%")

    def zoom_out(self):
        if not self.pdf_doc:
            return
        s = max(self.viewer._scale / 1.2, 0.2)
        self.viewer.set_zoom(s)
        self.zoom_label.setText(f"{int(s * 100)}%")

    def zoom_fit(self):
        if not self.pdf_doc or self.viewer._pixmap_item is None:
            return
        self.viewer.fitInView(self.viewer._pixmap_item, Qt.KeepAspectRatio)
        t = self.viewer.transform()
        self.viewer._scale = t.m11()
        self.zoom_label.setText(f"{int(self.viewer._scale * 100)}%")

    # ---------------------------- Redaction ops ----------------------------
    def _on_redaction_drawn(self, x0: float, y0: float, x1: float, y1: float):
        r = Redaction(self.current_page, x0, y0, x1, y1).normalized()
        self.redactions.append(r)
        self._refresh_overlay()
        self._update_counts()
        self.status.showMessage(
            f"Redaction added on page {self.current_page + 1}.", 3000
        )

    def find_and_redact(self):
        if not self.pdf_doc:
            QMessageBox.information(self, "No PDF", "Please upload a PDF first.")
            return
        query = self.search_input.text().strip()
        if not query:
            return
        added = 0
        try:
            for pno in range(self.pdf_doc.page_count):
                page = self.pdf_doc[pno]
                # PyMuPDF search_for is case-insensitive by default and returns fitz.Rect
                rects = page.search_for(query, quads=False)
                for rc in rects:
                    self.redactions.append(
                        Redaction(pno, rc.x0, rc.y0, rc.x1, rc.y1)
                    )
                    added += 1
            self._refresh_overlay()
            self._update_counts()
            if added == 0:
                QMessageBox.information(
                    self, "No matches",
                    f"'{query}' was not found anywhere in the document."
                )
            else:
                self.status.showMessage(
                    f"Marked {added} occurrence(s) of '{query}' for redaction.", 5000
                )
        except Exception as e:
            QMessageBox.critical(self, "Search error", f"Error during search: {e}")

    def undo(self):
        if not self.redactions:
            return
        removed = self.redactions.pop()
        if removed.page == self.current_page:
            self._refresh_overlay()
        self._update_counts()
        self.status.showMessage("Last redaction undone.", 2000)

    def clear_all(self):
        if not self.redactions:
            return
        reply = QMessageBox.question(
            self, "Clear All Redactions",
            f"Remove all {len(self.redactions)} redaction mark(s) from the document?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.redactions = []
            self._refresh_overlay()
            self._update_counts()
            self.status.showMessage("All redactions cleared.", 2000)

    # ---------------------------- Export ----------------------------
    def export_pdf(self):
        if not self.pdf_doc:
            QMessageBox.information(self, "No PDF", "Please upload a PDF first.")
            return
        if not self.redactions:
            reply = QMessageBox.question(
                self, "No redactions marked",
                "There are no redaction marks. Export anyway?\n\n"
                "(The PDF will still be rasterized — original text becomes uneditable.)",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        default_name = ""
        if self.pdf_path:
            base, _ = os.path.splitext(os.path.basename(self.pdf_path))
            default_name = base + "_redacted.pdf"

        out_path, _ = QFileDialog.getSaveFileName(
            self, "Export Redacted PDF", default_name, "PDF Files (*.pdf)"
        )
        if not out_path:
            return
        if not out_path.lower().endswith(".pdf"):
            out_path += ".pdf"

        progress = QProgressDialog(
            "Rasterizing and applying redactions…",
            "Cancel", 0, self.pdf_doc.page_count, self,
        )
        progress.setWindowTitle("Exporting")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        out_doc = None
        try:
            out_doc = fitz.open()
            scale = self.EXPORT_DPI / 72.0
            mat = fitz.Matrix(scale, scale)

            for pno in range(self.pdf_doc.page_count):
                if progress.wasCanceled():
                    out_doc.close()
                    self.status.showMessage("Export cancelled.", 3000)
                    return
                progress.setValue(pno)
                progress.setLabelText(
                    f"Rasterizing page {pno + 1} of {self.pdf_doc.page_count}…"
                )
                QApplication.processEvents()

                page = self.pdf_doc[pno]
                pix = page.get_pixmap(matrix=mat, alpha=False)

                # Convert PyMuPDF pixmap -> PIL image
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                draw = ImageDraw.Draw(img)

                # Paint solid black rectangles on the raster — original text gone
                for r in self.redactions:
                    if r.page != pno:
                        continue
                    x0 = int(r.x0 * scale)
                    y0 = int(r.y0 * scale)
                    x1 = int(r.x1 * scale)
                    y1 = int(r.y1 * scale)
                    # Clip to page bounds
                    x0 = max(0, min(pix.width, x0))
                    x1 = max(0, min(pix.width, x1))
                    y0 = max(0, min(pix.height, y0))
                    y1 = max(0, min(pix.height, y1))
                    if x1 > x0 and y1 > y0:
                        draw.rectangle([x0, y0, x1, y1], fill=(0, 0, 0))

                # Encode the redacted page image and embed as a fresh PDF page
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                buf.seek(0)
                img_bytes = buf.read()

                page_w = page.rect.width
                page_h = page.rect.height
                new_page = out_doc.new_page(width=page_w, height=page_h)
                new_page.insert_image(
                    fitz.Rect(0, 0, page_w, page_h), stream=img_bytes
                )

            progress.setValue(self.pdf_doc.page_count)

            # Strip metadata so author/title/etc. don't leak
            try:
                out_doc.set_metadata({})
            except Exception:
                pass

            out_doc.save(out_path, garbage=4, deflate=True, clean=True)
            out_doc.close()
            out_doc = None

            QMessageBox.information(
                self, "Export complete",
                f"Redacted PDF saved to:\n\n{out_path}\n\n"
                "All redacted regions have been permanently rasterized — "
                "the original text cannot be recovered."
            )
            self.status.showMessage(f"Exported:  {out_path}", 6000)
        except Exception as e:
            QMessageBox.critical(self, "Export failed", f"Error during export: {e}")
        finally:
            if out_doc is not None:
                try:
                    out_doc.close()
                except Exception:
                    pass
            progress.close()

    # ---------------------------- Cleanup ----------------------------
    def closeEvent(self, event):
        if self.pdf_doc:
            try:
                self.pdf_doc.close()
            except Exception:
                pass
        event.accept()


# ===========================================================================
#                                 ENTRY POINT
# ===========================================================================
def main():
    # High-DPI awareness for crisp rendering on modern displays
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("Sandeep Singla & Associates")
    _apply_window_icon(app)

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
