"""
gui/import_wizard.py

The import wizard dialog: pick a manufacturer (or auto-detect), pick a file,
and - only when the format isn't confidently recognized - confirm/correct
column roles before anything is parsed for real.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QFileDialog, QTableWidget, QTableWidgetItem, QMessageBox, QDialogButtonBox
)
from PySide6.QtCore import Qt

from core.importers import registry, generic_csv
from core.importers.chi import CHIImporter

ROLE_OPTIONS = ["(ignore)", "potential", "current", "time", "charge"]


class ImportWizard(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import CV Data")
        self.setMinimumWidth(520)

        self.cv_data = None      # populated on success
        self.filepath = None
        self._preview = None
        self._role_combos = []

        layout = QVBoxLayout(self)

        # --- Manufacturer + file selection ---
        row = QHBoxLayout()
        row.addWidget(QLabel("Manufacturer:"))
        self.manufacturer_combo = QComboBox()
        self.manufacturer_combo.addItems(["Auto-detect", "CHI", "Gamry", "Biologic/EC-Lab"])
        row.addWidget(self.manufacturer_combo)
        layout.addLayout(row)

        file_row = QHBoxLayout()
        self.file_label = QLabel("No file selected")
        self.file_label.setWordWrap(True)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_file)
        file_row.addWidget(self.file_label, stretch=1)
        file_row.addWidget(browse_btn)
        layout.addLayout(file_row)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        # --- Column confirmation table (hidden until needed) ---
        self.column_table = QTableWidget()
        self.column_table.setColumnCount(4)
        self.column_table.setHorizontalHeaderLabels(["Column", "Sample values", "Suggested role", "Confirm role"])
        self.column_table.setVisible(False)
        layout.addWidget(self.column_table)

        # --- Buttons ---
        self.button_box = QDialogButtonBox()
        self.import_btn = self.button_box.addButton("Import", QDialogButtonBox.AcceptRole)
        self.cancel_btn = self.button_box.addButton("Cancel", QDialogButtonBox.RejectRole)
        self.import_btn.clicked.connect(self._do_import)
        self.cancel_btn.clicked.connect(self.reject)
        self.import_btn.setEnabled(False)
        layout.addWidget(self.button_box)

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select CV data file", "", "Text/Data files (*.txt *.csv *.dta *.mpt);;All files (*.*)"
        )
        if not path:
            return
        self.filepath = path
        self.file_label.setText(path)
        self._analyze_file()

    def _analyze_file(self):
        """Run detection immediately on selection so the user sees what will happen."""
        manufacturer = self.manufacturer_combo.currentText()
        self.column_table.setVisible(False)
        self._preview = None

        try:
            if manufacturer == "CHI":
                importer = CHIImporter()
                with open(self.filepath, "r", encoding="utf-8", errors="replace") as f:
                    lines = [ln.rstrip("\r\n") for ln in f.readlines()]
                if importer.sniff(lines) < 0.5:
                    self.status_label.setText(
                        "This file doesn't look like a CHI export. You can still try importing it, "
                        "or switch to 'Auto-detect'."
                    )
                self.cv_data = None
                self.import_btn.setEnabled(True)
                self.status_label.setText("CHI format selected. Click Import to parse.")
                return

            if manufacturer in ("Gamry", "Biologic/EC-Lab"):
                self.status_label.setText(
                    f"{manufacturer} support is coming in a future update. "
                    f"Please use 'Auto-detect' for now."
                )
                self.import_btn.setEnabled(False)
                return

            # Auto-detect
            cv_data, preview = registry.identify_and_parse(self.filepath)
            if cv_data is not None:
                self.cv_data = cv_data
                self.status_label.setText(
                    f"Recognized format: {cv_data.metadata.source_format.upper()}. "
                    f"Click Import to load."
                )
                self.import_btn.setEnabled(True)
            else:
                self._preview = preview
                self._show_column_confirmation(preview)
                self.status_label.setText(
                    "Format not automatically recognized. Please confirm the column roles below."
                )
                self.import_btn.setEnabled(True)

        except Exception as e:
            self.status_label.setText(f"Could not read this file: {e}")
            self.import_btn.setEnabled(False)

    def _show_column_confirmation(self, preview):
        self.column_table.setVisible(True)
        self.column_table.setRowCount(len(preview.columns))
        self._role_combos = []
        for row_idx, col in enumerate(preview.columns):
            self.column_table.setItem(row_idx, 0, QTableWidgetItem(col.header_label))
            sample_text = ", ".join(f"{v:.4g}" for v in col.sample_values[:3])
            self.column_table.setItem(row_idx, 1, QTableWidgetItem(sample_text))
            confidence_text = f"{col.suggested_role or '(none)'}  ({col.confidence:.0%} confidence)"
            self.column_table.setItem(row_idx, 2, QTableWidgetItem(confidence_text))

            combo = QComboBox()
            combo.addItems(ROLE_OPTIONS)
            if col.suggested_role in ROLE_OPTIONS:
                combo.setCurrentText(col.suggested_role)
            self.column_table.setCellWidget(row_idx, 3, combo)
            self._role_combos.append(combo)
        self.column_table.resizeColumnsToContents()

    def _do_import(self):
        try:
            if self.cv_data is None and self._preview is not None:
                confirmed_roles = {}
                for idx, combo in enumerate(self._role_combos):
                    role = combo.currentText()
                    if role != "(ignore)":
                        confirmed_roles[idx] = role
                if "potential" not in confirmed_roles.values() or "current" not in confirmed_roles.values():
                    QMessageBox.warning(self, "Missing columns",
                                         "Please assign both a Potential and a Current column.")
                    return
                self.cv_data = generic_csv.finalize_parse(self._preview, confirmed_roles)

            elif self.cv_data is None and self.manufacturer_combo.currentText() == "CHI":
                importer = CHIImporter()
                self.cv_data = importer.parse(self.filepath)

            if self.cv_data is None:
                QMessageBox.warning(self, "No data", "No data has been parsed yet.")
                return

            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "Import failed", str(e))
