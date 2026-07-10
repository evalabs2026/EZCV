"""
gui/scan_series_panel.py

Persistent tab for multi-scan-rate analysis. Keeps loaded files and segment
selections in place - no re-importing everything just to tweak one file's
segment range. Dunn's and Trasatti results render inline below the table.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTableWidget,
    QTableWidgetItem, QFileDialog, QMessageBox, QSpinBox, QScrollArea
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT

from core.importers import registry
from core.scan_series import ScanRateSeries
from core.reporting import plots as report_plots
from core.reporting import series_report


class ScanSeriesPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.series = ScanRateSeries()

        # Track which analyses have been run - figures are regenerated fresh
        # at export time rather than cached, since a matplotlib Figure that
        # was ever embedded in a Qt canvas becomes unusable once that canvas
        # is destroyed (even for non-GUI operations like savefig()).
        self._dunn_has_run = False
        self._trasatti_has_run = False

        layout = QVBoxLayout(self)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add Files...")
        add_btn.clicked.connect(self._add_files)
        remove_btn = QPushButton("Remove Selected")
        remove_btn.clicked.connect(self._remove_selected)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(remove_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Placeholder hint - only visible when no files are loaded yet
        self.placeholder_label = QLabel(
            "No files added yet.\n\n"
            "Import several CV files of the SAME sample at DIFFERENT scan rates. "
            "Each file defaults to its last two segments (one steady-state cycle) - "
            "adjust Start/End if a file needs different segments."
        )
        self.placeholder_label.setWordWrap(True)
        self.placeholder_label.setStyleSheet("color: gray; font-style: italic; font-size: 11px;")
        layout.addWidget(self.placeholder_label)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["File", "Scan rate (V/s)", "Start segment", "End segment"])
        self.table.setMaximumHeight(220)
        layout.addWidget(self.table)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        run_row = QHBoxLayout()
        dunn_btn = QPushButton("Run Dunn's b-value Analysis")
        dunn_btn.clicked.connect(self._run_dunn)
        trasatti_btn = QPushButton("Run Trasatti Analysis")
        trasatti_btn.clicked.connect(self._run_trasatti)
        export_btn = QPushButton("Export Report (PDF)")
        export_btn.clicked.connect(self._export_report)
        run_row.addWidget(dunn_btn)
        run_row.addWidget(trasatti_btn)
        run_row.addWidget(export_btn)
        run_row.addStretch()
        layout.addLayout(run_row)

        self.results_scroll = QScrollArea()
        self.results_scroll.setWidgetResizable(True)
        self.results_placeholder = QLabel(
            "Results will appear here after you run an analysis."
        )
        self.results_placeholder.setStyleSheet("color: gray; font-style: italic;")
        self.results_scroll.setWidget(self.results_placeholder)
        layout.addWidget(self.results_scroll, stretch=1)

        self._update_placeholder_visibility()

    # ------------------------------------------------------------------

    def _update_placeholder_visibility(self):
        self.placeholder_label.setVisible(len(self.series.entries) == 0)

    def _add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select CV files at different scan rates", "",
            "Text/Data files (*.txt *.csv);;All files (*.*)"
        )
        if not paths:
            return

        skipped = []
        for path in paths:
            try:
                cv_data, preview = registry.identify_and_parse(path)
                if cv_data is None:
                    skipped.append(f"{path} (unrecognized format - use single-file Import + generic wizard first)")
                    continue
                self.series.add(path, cv_data)
            except Exception as e:
                skipped.append(f"{path} ({e})")

        # series.add() re-sorts entries by scan rate internally - rebuild the
        # table from scratch so row order always matches entries order exactly.
        self._rebuild_table()
        self.status_label.setText("Skipped:\n" + "\n".join(skipped) if skipped else "")

    def _rebuild_table(self):
        self.table.setRowCount(0)
        for entry in self.series.entries:
            self._add_row(entry)
        self._update_placeholder_visibility()
        # Underlying series changed - any previous analysis results are now stale
        self._dunn_has_run = False
        self._trasatti_has_run = False

    def _add_row(self, entry):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(entry.filepath.split("/")[-1].split("\\")[-1]))
        self.table.setItem(row, 1, QTableWidgetItem(str(entry.scan_rate)))

        all_segments = sorted(entry.cv_data.df["segment"].unique())
        seg_min, seg_max = int(all_segments[0]), int(all_segments[-1])

        start_spin = QSpinBox()
        start_spin.setRange(seg_min, seg_max)
        start_spin.setValue(int(entry.selected_segments[0]))
        end_spin = QSpinBox()
        end_spin.setRange(seg_min, seg_max)
        end_spin.setValue(int(entry.selected_segments[-1]))

        start_spin.valueChanged.connect(lambda _val, r=row: self._sync_segment_range(r))
        end_spin.valueChanged.connect(lambda _val, r=row: self._sync_segment_range(r))

        self.table.setCellWidget(row, 2, start_spin)
        self.table.setCellWidget(row, 3, end_spin)
        self.table.resizeColumnsToContents()

    def _sync_segment_range(self, row):
        """Applies immediately - no OK button needed, edits stick right away."""
        if row >= len(self.series.entries):
            return
        entry = self.series.entries[row]
        start_spin = self.table.cellWidget(row, 2)
        end_spin = self.table.cellWidget(row, 3)
        start, end = start_spin.value(), end_spin.value()
        if start > end:
            start, end = end, start
        all_segments = sorted(entry.cv_data.df["segment"].unique())
        entry.selected_segments = [s for s in all_segments if start <= s <= end]

    def _remove_selected(self):
        rows = sorted(set(idx.row() for idx in self.table.selectedIndexes()), reverse=True)
        for row in rows:
            if row < len(self.series.entries):
                del self.series.entries[row]
        self._rebuild_table()

    def _show_result_widget(self, widget):
        old = self.results_scroll.takeWidget()
        if old is not None:
            old.deleteLater()
        self.results_scroll.setWidget(widget)

    def _clear_results_area(self):
        old = self.results_scroll.takeWidget()
        if old is not None:
            old.deleteLater()
        self.results_scroll.setWidget(self.results_placeholder)

    def _run_dunn(self):
        valid, msg = self.series.is_valid()
        if not valid:
            QMessageBox.warning(self, "Cannot run analysis", msg)
            return
        try:
            figure, grid, b_values = report_plots.build_dunn_figure(self.series)
        except Exception as e:
            QMessageBox.critical(self, "Analysis failed", str(e))
            return

        self._dunn_has_run = True
        self._show_result_widget(self._wrap_figure_widget(
            figure,
            "b \u2248 1: surface-capacitive process at that potential.  "
            "b \u2248 0.5: diffusion-controlled process.  "
            "Points near the potential-window edges are less reliable (low current, unstable fit)."
        ))

    def _run_trasatti(self):
        valid, msg = self.series.is_valid()
        if not valid:
            QMessageBox.warning(self, "Cannot run analysis", msg)
            return
        try:
            figure, result = report_plots.build_trasatti_figure(self.series)
        except Exception as e:
            QMessageBox.critical(self, "Analysis failed", str(e))
            return

        self._trasatti_has_run = True

        summary = (
            f"q_total (total charge) = {result['q_total']:.4e} C\n"
            f"q_outer (fast, easily accessible) = {result['q_outer']:.4e} C\n"
            f"q_inner (diffusion-limited) = {result['q_inner']:.4e} C\n\n"
            f"\u2248 EDLC / fast surface contribution: {result['percent_outer']:.1f}%\n"
            f"\u2248 Pseudocapacitive / diffusion-limited contribution: {result['percent_inner']:.1f}%\n\n"
            f"R\u00b2 (outer fit): {result['r2_outer']:.4f}   R\u00b2 (total fit): {result['r2_total']:.4f}\n\n"
            f"Note: this outer/inner split is the standard Trasatti proxy for EDLC vs. "
            f"pseudocapacitive contribution - a widely used approximation, not a strict "
            f"physical separation. R\u00b2 below ~0.95 suggests the extrapolation may not be "
            f"very reliable over this scan-rate range."
        )
        self._show_result_widget(self._wrap_figure_widget(figure, summary, bold_first_lines=6))

    def _wrap_figure_widget(self, figure, note_text, bold_first_lines=0):
        widget = QWidget()
        w_layout = QVBoxLayout(widget)
        canvas = FigureCanvasQTAgg(figure)
        toolbar = NavigationToolbar2QT(canvas, widget)
        w_layout.addWidget(toolbar)
        w_layout.addWidget(canvas)
        note = QLabel(note_text)
        note.setWordWrap(True)
        if bold_first_lines:
            note.setStyleSheet("font-weight: bold;")
        else:
            note.setStyleSheet("color: gray; font-style: italic;")
        w_layout.addWidget(note)
        return widget

    def _export_report(self):
        if not self._dunn_has_run and not self._trasatti_has_run:
            QMessageBox.warning(
                self, "Nothing to export",
                "Run Dunn's b-value and/or Trasatti analysis first, then export."
            )
            return

        path, _ = QFileDialog.getSaveFileName(self, "Export Report", "", "PDF files (*.pdf)")
        if not path:
            return
        if not path.endswith(".pdf"):
            path += ".pdf"

        import tempfile, os
        dunn_image_path = None
        trasatti_image_path = None
        trasatti_result = None
        try:
            # Regenerate figures fresh here (never attached to any Qt widget)
            # rather than reusing ones shown in the GUI, to avoid the figure
            # becoming unusable once its on-screen canvas gets destroyed.
            if self._dunn_has_run:
                dunn_figure, _grid, _b = report_plots.build_dunn_figure(self.series)
                dunn_image_path = os.path.join(tempfile.gettempdir(), "ezcv_dunn_export.png")
                dunn_figure.savefig(dunn_image_path, dpi=150)

            if self._trasatti_has_run:
                trasatti_figure, trasatti_result = report_plots.build_trasatti_figure(self.series)
                trasatti_image_path = os.path.join(tempfile.gettempdir(), "ezcv_trasatti_export.png")
                trasatti_figure.savefig(trasatti_image_path, dpi=150)

            series_report.build_series_report(
                path, self.series,
                dunn_image_path=dunn_image_path,
                trasatti_image_path=trasatti_image_path,
                trasatti_result=trasatti_result,
            )
            QMessageBox.information(self, "Report exported", f"Report saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))
        finally:
            for p in (dunn_image_path, trasatti_image_path):
                if p and os.path.exists(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass

    # --- Save/load project support ---

    def get_state(self):
        return {"scan_series": self.series}

    def set_state(self, state):
        series = state.get("scan_series")
        self.series = series if series is not None else ScanRateSeries()
        self._rebuild_table()
        self._clear_results_area()

    def has_series(self):
        return len(self.series.entries) > 0

    def clear_all(self):
        self.series = ScanRateSeries()
        self._rebuild_table()
        self.status_label.setText("")
        self._clear_results_area()
        self._dunn_has_run = False
        self._trasatti_has_run = False
