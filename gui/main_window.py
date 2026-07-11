"""
gui/main_window.py

Main application window. Two persistent tabs (Single CV Analysis,
Scan-Rate Series Analysis) so switching between workflows never loses
state. Full menu bar: File, Edit, View, Analysis, Help.
"""

from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QMessageBox, QFileDialog, QDialog, QVBoxLayout,
    QHBoxLayout, QLineEdit, QPushButton, QLabel, QApplication
)
from PySide6.QtGui import QAction, QKeySequence
import pickle

from gui.single_analysis_tab import SingleAnalysisTab
from gui.scan_series_panel import ScanSeriesPanel

APP_VERSION = "1.0.0"


class FindDialog(QDialog):
    """Simple find-in-results-panel dialog for the Single Analysis tab."""
    def __init__(self, text_edit, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Find")
        self.text_edit = text_edit

        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel("Find:"))
        self.search_box = QLineEdit()
        row.addWidget(self.search_box)
        layout.addLayout(row)

        btn_row = QHBoxLayout()
        find_btn = QPushButton("Find Next")
        find_btn.clicked.connect(self._find_next)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(find_btn)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self.search_box.returnPressed.connect(self._find_next)

    def _find_next(self):
        term = self.search_box.text()
        if not term:
            return
        found = self.text_edit.find(term)
        if not found:
            # wrap around: move cursor to start and try again
            cursor = self.text_edit.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            self.text_edit.setTextCursor(cursor)
            found = self.text_edit.find(term)
            if not found:
                QMessageBox.information(self, "Find", f'"{term}" not found.')


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EZCV - Cyclic Voltammetry Analyzer")
        self.resize(1100, 750)

        self.tabs = QTabWidget()
        self.single_tab = SingleAnalysisTab()
        self.series_tab = ScanSeriesPanel()
        self.tabs.addTab(self.single_tab, "Single CV Analysis")
        self.tabs.addTab(self.series_tab, "Scan-Rate Series Analysis")
        self.setCentralWidget(self.tabs)

        self._build_menu_bar()

    # ------------------------------------------------------------------
    # Menu bar
    # ------------------------------------------------------------------

    def _build_menu_bar(self):
        menu_bar = self.menuBar()

        # --- File ---
        file_menu = menu_bar.addMenu("&File")

        new_action = QAction("&New Project", self)
        new_action.setShortcut(QKeySequence("Ctrl+N"))
        new_action.triggered.connect(self._new_project)
        file_menu.addAction(new_action)

        close_action = QAction("&Close Project", self)
        close_action.setShortcut(QKeySequence("Ctrl+W"))
        close_action.triggered.connect(self._close_project)
        file_menu.addAction(close_action)

        file_menu.addSeparator()
        import_action = QAction("&Import...", self)
        import_action.setShortcut(QKeySequence("Ctrl+I"))
        import_action.triggered.connect(self._import_single_file)
        file_menu.addAction(import_action)

        file_menu.addSeparator()
        save_project_action = QAction("&Save Project...", self)
        save_project_action.setShortcut(QKeySequence("Ctrl+S"))
        save_project_action.triggered.connect(self._save_project)
        file_menu.addAction(save_project_action)

        open_project_action = QAction("&Open Project...", self)
        open_project_action.setShortcut(QKeySequence("Ctrl+O"))
        open_project_action.triggered.connect(self._open_project)
        file_menu.addAction(open_project_action)

        file_menu.addSeparator()
        export_action = QAction("&Export Report (PDF)...", self)
        export_action.setShortcut(QKeySequence("Ctrl+E"))
        export_action.triggered.connect(self._export_report_current_tab)
        file_menu.addAction(export_action)

        file_menu.addSeparator()
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # --- Edit ---
        edit_menu = menu_bar.addMenu("&Edit")

        cut_action = QAction("Cu&t", self)
        cut_action.setShortcut(QKeySequence.Cut)
        cut_action.triggered.connect(lambda: self._focused_widget_action("cut"))
        edit_menu.addAction(cut_action)

        copy_action = QAction("&Copy", self)
        copy_action.setShortcut(QKeySequence.Copy)
        copy_action.triggered.connect(lambda: self._focused_widget_action("copy"))
        edit_menu.addAction(copy_action)

        paste_action = QAction("&Paste", self)
        paste_action.setShortcut(QKeySequence.Paste)
        paste_action.triggered.connect(lambda: self._focused_widget_action("paste"))
        edit_menu.addAction(paste_action)

        edit_menu.addSeparator()
        find_action = QAction("&Find...", self)
        find_action.setShortcut(QKeySequence.Find)
        find_action.triggered.connect(self._open_find_dialog)
        edit_menu.addAction(find_action)

        preferences_action = QAction("&Preferences...", self)
        preferences_action.triggered.connect(self._show_preferences)
        edit_menu.addAction(preferences_action)

        # --- View ---
        view_menu = menu_bar.addMenu("&View")

        self.toggle_sidebar_action = QAction("Show &Sidebar", self)
        self.toggle_sidebar_action.setCheckable(True)
        self.toggle_sidebar_action.setChecked(True)
        self.toggle_sidebar_action.triggered.connect(self._toggle_sidebar)
        view_menu.addAction(self.toggle_sidebar_action)

        self.toggle_toolbar_action = QAction("Show &Plot Toolbar", self)
        self.toggle_toolbar_action.setCheckable(True)
        self.toggle_toolbar_action.setChecked(True)
        self.toggle_toolbar_action.triggered.connect(self._toggle_plot_toolbar)
        view_menu.addAction(self.toggle_toolbar_action)

        view_menu.addSeparator()
        reset_zoom_action = QAction("&Reset Plot Zoom", self)
        reset_zoom_action.triggered.connect(lambda: self.single_tab.reset_plot_zoom())
        view_menu.addAction(reset_zoom_action)

        # --- Analysis ---
        analysis_menu = menu_bar.addMenu("&Analysis")

        sample_info_action = QAction("&Sample Info...", self)
        sample_info_action.triggered.connect(lambda: self.single_tab.open_sample_info())
        analysis_menu.addAction(sample_info_action)

        calculate_action = QAction("&Calculate...", self)
        calculate_action.setShortcut(QKeySequence("Ctrl+R"))
        calculate_action.triggered.connect(lambda: self.single_tab.open_calculate_dialog())
        analysis_menu.addAction(calculate_action)

        analysis_menu.addSeparator()
        goto_series_action = QAction("Go to &Scan-Rate Series Tab", self)
        goto_series_action.triggered.connect(lambda: self.tabs.setCurrentWidget(self.series_tab))
        analysis_menu.addAction(goto_series_action)

        # --- Help ---
        help_menu = menu_bar.addMenu("&Help")
        about_action = QAction("&About EZCV", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    # ------------------------------------------------------------------
    # Edit menu handlers
    # ------------------------------------------------------------------

    def _focused_widget_action(self, action):
        widget = QApplication.focusWidget()
        if widget is None:
            return
        method = getattr(widget, action, None)
        if callable(method):
            method()

    def _open_find_dialog(self):
        if self.tabs.currentWidget() is not self.single_tab:
            QMessageBox.information(self, "Find", "Find currently searches the Results panel "
                                                    "in the Single CV Analysis tab.")
            self.tabs.setCurrentWidget(self.single_tab)
        dialog = FindDialog(self.single_tab.results_view, self)
        dialog.exec()

    def _show_preferences(self):
        QMessageBox.information(self, "Preferences", "Preferences are coming in a future update.")

    # ------------------------------------------------------------------
    # View menu handlers
    # ------------------------------------------------------------------

    def _toggle_sidebar(self, checked):
        self.single_tab.sidebar_widget.setVisible(checked)

    def _toggle_plot_toolbar(self, checked):
        self.single_tab.nav_toolbar.setVisible(checked)

    # ------------------------------------------------------------------
    # File menu handlers
    # ------------------------------------------------------------------

    def _new_project(self):
        if self.single_tab.cv_data is not None or self.series_tab.has_series():
            reply = QMessageBox.question(
                self, "New Project",
                "Starting a new project will clear all currently loaded data. Continue?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
        self.single_tab.clear_all()
        self.series_tab.clear_all()
        self._import_single_file()

    def _close_project(self):
        if self.single_tab.cv_data is None and not self.series_tab.has_series():
            QMessageBox.information(self, "Close Project", "There is no project currently open.")
            return
        reply = QMessageBox.question(
            self, "Close Project",
            "This will clear all currently loaded data without starting a new import. Continue?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        self.single_tab.clear_all()
        self.series_tab.clear_all()

    def _import_single_file(self):
        self.tabs.setCurrentWidget(self.single_tab)
        self.single_tab.open_import_wizard()

    def _export_report_current_tab(self):
        current = self.tabs.currentWidget()
        if current is self.single_tab:
            self.single_tab.export_report()
        elif current is self.series_tab:
            self.series_tab._export_report()

    def _show_about(self):
        QMessageBox.about(
            self, "About EZCV",
            f"<b>EZCV - Cyclic Voltammetry Analyzer</b><br>"
            f"Version {APP_VERSION}<br><br>"
            f"An open-source tool for importing, plotting, and analyzing "
            f"cyclic voltammetry data, including multi-scan-rate kinetics "
            f"analysis (Dunn's b-value, Trasatti).<br><br>"
            f"Licensed under the GNU General Public License v3.0..<br><br>"
            f"contact; evalabs2026@gmail.com"
        )

    def _save_project(self):
        if self.single_tab.cv_data is None and not self.series_tab.has_series():
            QMessageBox.warning(self, "Nothing to save", "Import some data first.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save Project", "", "EZCV Project (*.ezcv)")
        if not path:
            return
        if not path.endswith(".ezcv"):
            path += ".ezcv"

        state = {
            "version": APP_VERSION,
            "single_tab": self.single_tab.get_state(),
            "series_tab": self.series_tab.get_state(),
        }
        try:
            with open(path, "wb") as f:
                pickle.dump(state, f)
            QMessageBox.information(self, "Saved", f"Project saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))

    def _open_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Project", "", "EZCV Project (*.ezcv);;All files (*.*)")
        if not path:
            return
        try:
            with open(path, "rb") as f:
                state = pickle.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Open failed", f"Could not load this project file:\n{e}")
            return

        self.single_tab.set_state(state.get("single_tab", {}))
        self.series_tab.set_state(state.get("series_tab", {}))
        QMessageBox.information(self, "Project loaded", f"Loaded project from:\n{path}")
