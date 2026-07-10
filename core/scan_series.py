"""
core/scan_series.py

Data model for a set of CV files of the SAME sample at DIFFERENT scan
rates - the basis for Dunn's b-value analysis and Trasatti analysis,
neither of which is possible from a single file.
"""

from dataclasses import dataclass, field
import numpy as np

from core.importers.base import CVData


@dataclass
class ScanRateEntry:
    filepath: str
    cv_data: CVData
    scan_rate: float
    selected_segments: list  # segment numbers to use for this file

    def default_segments(self) -> list:
        """Last two segments = one steady-state forward+reverse cycle."""
        all_segments = sorted(self.cv_data.df["segment"].unique())
        return all_segments[-2:] if len(all_segments) >= 2 else all_segments

    def filtered_df(self):
        df = self.cv_data.df
        return df[df["segment"].isin(self.selected_segments)]


@dataclass
class ScanRateSeries:
    entries: list = field(default_factory=list)

    def add(self, filepath: str, cv_data: CVData, scan_rate: float | None = None):
        rate = scan_rate if scan_rate is not None else cv_data.metadata.scan_rate
        if rate is None:
            raise ValueError(
                f"No scan rate found in {filepath} and none provided manually. "
                f"Please enter it before adding this file to the series."
            )
        entry = ScanRateEntry(filepath=filepath, cv_data=cv_data, scan_rate=rate, selected_segments=[])
        entry.selected_segments = entry.default_segments()
        self.entries.append(entry)
        self.entries.sort(key=lambda e: e.scan_rate)
        return entry

    def scan_rates(self) -> np.ndarray:
        return np.array([e.scan_rate for e in self.entries])

    def is_valid(self) -> tuple:
        """Basic sanity checks before running kinetics analysis."""
        if len(self.entries) < 3:
            return False, "Need at least 3 different scan rates for meaningful kinetics analysis."
        rates = self.scan_rates()
        if len(set(rates)) != len(rates):
            return False, "Duplicate scan rates found - each file should have a distinct scan rate."
        return True, ""
