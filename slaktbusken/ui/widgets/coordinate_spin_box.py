"""Custom QDoubleSpinBox that handles paste with period decimal separator."""

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QDoubleSpinBox


class CoordinateSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox that accepts paste with period decimal separator.

    When pasting, the text is normalized by stripping whitespace and
    replacing comma with period before parsing. Values are rounded to
    the spin box's decimal precision and validated against the range.
    Invalid pastes are silently rejected (current value is retained).
    """

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Paste):
            clipboard = QApplication.clipboard()
            text = clipboard.text().strip()
            # Normalize: accept both comma and period as decimal separator
            normalized = text.replace(",", ".")
            try:
                value = float(normalized)
                # Round to spin box decimal precision
                value = round(value, self.decimals())
                if self.minimum() <= value <= self.maximum():
                    self.setValue(value)
            except ValueError:
                pass  # Reject invalid paste, retain current value
            return
        super().keyPressEvent(event)
