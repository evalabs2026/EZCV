"""
gui/single_analysis_tab.py

The single-file CV analysis workspace: plot, segment selector, sample info,
calculate, and results. Lives as one persistent tab so its state (loaded
file, segment selection, results) never disappears when switching to the
scan-rate series tab.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QCheckBox,
    QGroupBox, QFormLayout, QLineEdit, QDialog, QDialogButtonBox,
    QMessageBox, QTextEdit, QFileDialog,
    QComboBox
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure

from gui.import_wizard import ImportWizard
from core.calculations import capacitance, peaks
from core.reporting import single_report


class SampleInfoDialog(QDialog):
    def __init__(self, parent=None, existing=None):
        super().__init__(parent)
        self.setWindowTitle("Sample Information")
        layout = QFormLayout(self)

        existing = existing or {}
        self.mass_edit = QLineEdit(str(existing.get("mass_g", "")))
        self.area_edit = QLineEdit(str(existing.get("area_cm2", "")))
        self.v0_edit = QLineEdit(str(existing.get("v0", "")))
        self.v1_edit = QLineEdit(str(existing.get("v1", "")))

        layout.addRow("Mass (g):", self.mass_edit)
        layout.addRow("Electrode area (cm²):", self.area_edit)
        layout.addRow("Potential window V0 (V):", self.v0_edit)
        layout.addRow("Potential window V1 (V):", self.v1_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self):
        def parse_float(text):
            try:
                return float(text)
            except ValueError:
                return None
        return {
            "mass_g": parse_float(self.mass_edit.text()),
            "area_cm2": parse_float(self.area_edit.text()),
            "v0": parse_float(self.v0_edit.text()),
            "v1": parse_float(self.v1_edit.text()),
        }


class CalculateDialog(QDialog):
    """Checklist of available parameters. More get added here over time."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Parameters to Calculate")
        layout = QVBoxLayout(self)

        self.checkboxes = {}

        capacitance_group = QGroupBox("Capacitance")
        cap_layout = QVBoxLayout()
        for key, label in [
            ("area", "Area under curve (absolute trapezoidal)"),
            ("specific_capacitance", "Specific capacitance (F/g)"),
        ]:
            cb = QCheckBox(label)
            cb.setChecked(True)
            cap_layout.addWidget(cb)
            self.checkboxes[key] = cb
        capacitance_group.setLayout(cap_layout)
        layout.addWidget(capacitance_group)

        peaks_group = QGroupBox("Peak Analysis")
        peaks_layout = QVBoxLayout()
        for key, label in [
            ("epa", "Oxidation peak potential (Epa)"),
            ("epc", "Reduction peak potential (Epc)"),
            ("ipa", "Oxidation peak current (Ipa)"),
            ("ipc", "Reduction peak current (Ipc)"),
            ("delta_ep", "Peak potential separation (\u0394Ep)"),
            ("formal_potential", "Formal potential (E\u00b0\u2032)"),
            ("ipa_ipc_ratio", "Peak current ratio (Ipa/Ipc)"),
        ]:
            cb = QCheckBox(label)
            cb.setChecked(True)
            peaks_layout.addWidget(cb)
            self.checkboxes[key] = cb
        peaks_group.setLayout(peaks_layout)
        layout.addWidget(peaks_group)

        note = QLabel("More parameters (energy/power density, diffusion coefficient) coming soon.")
        note.setStyleSheet("color: gray; font-style: italic;")
        layout.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected(self):
        return [key for key, cb in self.checkboxes.items() if cb.isChecked()]


class SingleAnalysisTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.cv_data = None
        self.sample_info = {}
        self.results = {}
        self.start_segment_combo = None
        self.end_segment_combo = None
        self._last_imported_filename = None

        main_layout = QHBoxLayout(self)

        # --- Left: toolbar + plot + segment selector ---
        left_panel = QVBoxLayout()

        self.figure = Figure(figsize=(5, 4))
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.ax = self.figure.add_subplot(111)
        self.nav_toolbar = NavigationToolbar2QT(self.canvas, self)
        left_panel.addWidget(self.nav_toolbar)
        left_panel.addWidget(self.canvas, stretch=1)
        self._show_empty_placeholder()

        self.segment_box = QGroupBox("Segments")

        segment_layout = QHBoxLayout()

        segment_layout.addWidget(QLabel("Start Segment"))

        self.start_segment_combo = QComboBox()
        self.start_segment_combo.currentIndexChanged.connect(self._plot)
        segment_layout.addWidget(self.start_segment_combo)

        segment_layout.addSpacing(15)

        segment_layout.addWidget(QLabel("End Segment"))

        self.end_segment_combo = QComboBox()
        self.end_segment_combo.currentIndexChanged.connect(self._plot)
        segment_layout.addWidget(self.end_segment_combo)

        segment_layout.addStretch()

        self.segment_box.setLayout(segment_layout)
        left_panel.addWidget(self.segment_box)

        

        main_layout.addLayout(left_panel, stretch=3)

        # --- Right: controls + results (wrapped so it can be hidden via View menu) ---
        self.sidebar_widget = QWidget()
        right_panel = QVBoxLayout(self.sidebar_widget)

        self.import_btn = QPushButton("Import")
        self.import_btn.clicked.connect(self.open_import_wizard)
        right_panel.addWidget(self.import_btn)

        self.sample_info_btn = QPushButton("Sample Info")
        self.sample_info_btn.clicked.connect(self.open_sample_info)
        self.sample_info_btn.setEnabled(False)
        right_panel.addWidget(self.sample_info_btn)

        self.calculate_btn = QPushButton("Calculate")
        self.calculate_btn.clicked.connect(self.open_calculate_dialog)
        self.calculate_btn.setEnabled(False)
        right_panel.addWidget(self.calculate_btn)

        self.export_btn = QPushButton("Export Report (PDF)")
        self.export_btn.clicked.connect(self.export_report)
        self.export_btn.setEnabled(False)
        right_panel.addWidget(self.export_btn)

        right_panel.addWidget(QLabel("Results:"))
        self.results_view = QTextEdit()
        self.results_view.setReadOnly(True)
        self.results_view.setPlainText("No results yet.")
        right_panel.addWidget(self.results_view, stretch=1)

        main_layout.addWidget(self.sidebar_widget, stretch=1)

    # ------------------------------------------------------------------

    def _show_empty_placeholder(self):
        self.ax.clear()
        self.ax.text(
            0.5, 0.5,
            "No data loaded\n\nUse File \u2192 Import (or the Import button)\nto load a CV file",
            ha="center", va="center", transform=self.ax.transAxes,
            color="gray", fontsize=11,
        )
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        for spine in self.ax.spines.values():
            spine.set_visible(False)
        self.canvas.draw()

    def reset_plot_zoom(self):
        if self.cv_data is not None:
            self.ax.relim()
            self.ax.autoscale()
            self.canvas.draw()

    def open_import_wizard(self):
        wizard = ImportWizard(self)
        if wizard.exec() == ImportWizard.Accepted and wizard.cv_data is not None:
            self.cv_data = wizard.cv_data
            self._last_imported_filename = (wizard.filepath or "CV data file").split("/")[-1].split("\\")[-1]
            self.sample_info_btn.setEnabled(True)
            self.calculate_btn.setEnabled(True)
            self._build_segment_checkboxes()
            self._plot()

    def _build_segment_checkboxes(self):
        self.start_segment_combo.blockSignals(True)
        self.end_segment_combo.blockSignals(True)

        self.start_segment_combo.clear()
        self.end_segment_combo.clear()

        segments = sorted(self.cv_data.df["segment"].unique())

        for seg in segments:
            self.start_segment_combo.addItem(str(seg), seg)
            self.end_segment_combo.addItem(str(seg), seg)

        if len(segments) >= 2:
            self.start_segment_combo.setCurrentIndex(len(segments) - 2)
            self.end_segment_combo.setCurrentIndex(len(segments) - 1)
        elif len(segments) == 1:
            self.start_segment_combo.setCurrentIndex(0)
            self.end_segment_combo.setCurrentIndex(0)

        self.start_segment_combo.blockSignals(False)
        self.end_segment_combo.blockSignals(False)

    def _selected_segments_df(self):
        start_seg = self.start_segment_combo.currentData()
        end_seg = self.end_segment_combo.currentData()

        if start_seg is None or end_seg is None:
            return self.cv_data.df.iloc[0:0]

        if start_seg > end_seg:
            start_seg, end_seg = end_seg, start_seg

        return self.cv_data.df[
        (self.cv_data.df["segment"] >= start_seg) &
        (self.cv_data.df["segment"] <= end_seg)
    ]

    def _plot(self):
        if self.cv_data is None:
            self._show_empty_placeholder()
            return
        df = self._selected_segments_df()
        self.ax.clear()
        self.ax.set_xticks(self.ax.get_xticks())  # restore normal axes after placeholder
        for spine in self.ax.spines.values():
            spine.set_visible(True)
        for seg, group in df.groupby("segment"):
            self.ax.plot(group["potential_V"], group["current_A"], label=f"Segment {seg}")
        self.ax.set_xlabel("Potential (V)")
        self.ax.set_ylabel("Current (A)")
        self.ax.legend(fontsize=8)
        self.canvas.draw()

    def open_sample_info(self):
        dialog = SampleInfoDialog(self, existing=self.sample_info)
        if dialog.exec() == QDialog.Accepted:
            self.sample_info = dialog.values()

    def open_calculate_dialog(self):
        dialog = CalculateDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        selected = dialog.selected()
        df = self._selected_segments_df()
        if df.empty:
            QMessageBox.warning(self, "No data", "No segments selected.")
            return

        potential = df["potential_V"].to_numpy()
        current = df["current_A"].to_numpy()
        self.results = {}

        try:
            if "area" in selected or "specific_capacitance" in selected:
                area = capacitance.absolute_trapezoidal_area(potential, current)
                self.results["Area under curve"] = f"{area:.6e} (V\u00b7A)"

            if "specific_capacitance" in selected:
                mass = self.sample_info.get("mass_g")
                v0 = self.sample_info.get("v0")
                v1 = self.sample_info.get("v1")
                scan_rate = getattr(self.cv_data.metadata, "scan_rate", None)

                missing = [name for name, val in
                           [("mass", mass), ("V0", v0), ("V1", v1), ("scan rate", scan_rate)]
                           if val is None]
                if missing:
                    QMessageBox.warning(
                        self, "Missing information",
                        f"Cannot calculate specific capacitance - missing: {', '.join(missing)}.\n"
                        f"Fill these in via the 'Sample Info' button "
                        f"(scan rate comes from the file automatically when available)."
                    )
                else:
                    delta_v = abs(v1 - v0)
                    cs = capacitance.specific_capacitance(area, mass, scan_rate, delta_v)
                    self.results["Specific capacitance"] = f"{cs:.4f} F/g"

            peak_keys = {"epa", "epc", "ipa", "ipc", "delta_ep", "formal_potential", "ipa_ipc_ratio"}
            if peak_keys & set(selected):
                peak_result = peaks.analyze_peaks(df)
                if not peak_result.peaks_detected:
                    self.results["Peak analysis"] = (
                        "No distinct redox peak detected "
                    )
                else:
                    if "epa" in selected:
                        self.results["Oxidation peak potential (Epa)"] = (
                            f"{peak_result.epa:.4f} V" if peak_result.epa is not None else "Not detected"
                        )
                    if "ipa" in selected:
                        self.results["Oxidation peak current (Ipa)"] = (
                            f"{peak_result.ipa:.4e} A" if peak_result.ipa is not None else "Not detected"
                        )
                    if "epc" in selected:
                        self.results["Reduction peak potential (Epc)"] = (
                            f"{peak_result.epc:.4f} V" if peak_result.epc is not None else "Not detected"
                        )
                    if "ipc" in selected:
                        self.results["Reduction peak current (Ipc)"] = (
                            f"{peak_result.ipc:.4e} A" if peak_result.ipc is not None else "Not detected"
                        )
                    if "delta_ep" in selected:
                        self.results["Peak separation (\u0394Ep)"] = (
                            f"{peak_result.delta_ep:.4f} V" if peak_result.delta_ep is not None
                            else "Requires both Epa and Epc"
                        )
                    if "formal_potential" in selected:
                        self.results["Formal potential (E\u00b0\u2032)"] = (
                            f"{peak_result.formal_potential:.4f} V" if peak_result.formal_potential is not None
                            else "Requires both Epa and Epc"
                        )
                    if "ipa_ipc_ratio" in selected:
                        self.results["Peak current ratio (Ipa/Ipc)"] = (
                            f"{peak_result.ipa_ipc_ratio:.4f}" if peak_result.ipa_ipc_ratio is not None
                            else "Requires both Ipa and Ipc"
                        )

            self._render_results()
            self.export_btn.setEnabled(bool(self.results))

        except Exception as e:
            QMessageBox.critical(self, "Calculation error", str(e))

    def _render_results(self):
        if not self.results:
            self.results_view.setPlainText("No results yet.")
            return
        text = "\n".join(f"{k}: {v}" for k, v in self.results.items())
        self.results_view.setPlainText(text)

    def clear_all(self):
        """Used by File > New and File > Close to reset this tab to empty state."""
        self.cv_data = None
        self.sample_info = {}
        self.results = {}
        self.start_segment_combo.clear()
        self.end_segment_combo.clear()
        self.sample_info_btn.setEnabled(False)
        self.calculate_btn.setEnabled(False)
        self.export_btn.setEnabled(False)
        self._show_empty_placeholder()
        self._render_results()

    def export_report(self):
        if self.cv_data is None:
            QMessageBox.warning(self, "Nothing to export", "Import a file first.")
            return
        if not self.results:
            QMessageBox.warning(self, "Nothing to export", "Run Calculate first, then export.")
            return

        path, _ = QFileDialog.getSaveFileName(self, "Export Report", "", "PDF files (*.pdf)")
        if not path:
            return
        if not path.endswith(".pdf"):
            path += ".pdf"

        import tempfile, os
        plot_image_path = os.path.join(tempfile.gettempdir(), "ezcv_single_export.png")
        try:
            self.figure.savefig(plot_image_path, dpi=150)

            meta = self.cv_data.metadata
            metadata_dict = {
                "instrument_model": getattr(meta, "instrument_model", None),
                "scan_rate": getattr(meta, "scan_rate", None),
                "init_e": getattr(meta, "init_e", None),
                "high_e": getattr(meta, "high_e", None),
                "low_e": getattr(meta, "low_e", None),
            }
            selected_segments = list(
            range(
                self.start_segment_combo.currentData(),
                self.end_segment_combo.currentData() + 1
                 )
            )

            filename = getattr(self, "_last_imported_filename", "CV data file")

            single_report.build_single_report(
                path, filename, metadata_dict, self.sample_info, self.results,
                plot_image_path, selected_segments
            )
            QMessageBox.information(self, "Report exported", f"Report saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))
        finally:
            if os.path.exists(plot_image_path):
                try:
                    os.remove(plot_image_path)
                except OSError:
                    pass

    # --- Save/load project support ---

    def get_state(self):
        selected_segments = [
            self.start_segment_combo.currentData(),
            self.end_segment_combo.currentData(),
            ]
        return {
            "cv_data": self.cv_data,
            "selected_segments": selected_segments,
            "sample_info": self.sample_info,
            "results": self.results,
        }

    def set_state(self, state):
        self.cv_data = state.get("cv_data")
        self.sample_info = state.get("sample_info", {})
        self.results = state.get("results", {})

        if self.cv_data is not None:
            self.sample_info_btn.setEnabled(True)
            self.calculate_btn.setEnabled(True)
            self._build_segment_checkboxes()
            selected_segments = state.get("selected_segments", [])

            if selected_segments:
                start_seg = min(selected_segments)
                end_seg = max(selected_segments)

                start_index = self.start_segment_combo.findData(start_seg)
                end_index = self.end_segment_combo.findData(end_seg)

            if start_index != -1:
                self.start_segment_combo.setCurrentIndex(start_index)

            if end_index != -1:
                self.end_segment_combo.setCurrentIndex(end_index)

        self._render_results()
        self.export_btn.setEnabled(bool(self.results))
