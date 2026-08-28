import argparse
import datetime
import os
import shutil
import sqlite3
import sys
import tempfile
from dataclasses import dataclass
from functools import partial
from typing import Iterable, List

DEFAULT_HISTORY_FILE = (
    r"C:\Users\deep\AppData\Local\BraveSoftware\Brave-Browser\User Data\Default\History"
)
CHROME_EPOCH_OFFSET_SECONDS = 11644473600


@dataclass(frozen=True)
class HistoryEntry:
    url: str
    title: str
    visit_count: int
    last_visit_time: int


def chrome_timestamp_to_datetime(chrome_timestamp: int) -> datetime.datetime | None:
    if not chrome_timestamp:
        return None
    unix_seconds = chrome_timestamp / 1e6 - CHROME_EPOCH_OFFSET_SECONDS
    return datetime.datetime.fromtimestamp(unix_seconds)


def display_timestamp(chrome_timestamp: int) -> str:
    timestamp = chrome_timestamp_to_datetime(chrome_timestamp)
    if timestamp is None:
        return "UNKNOWN"
    return timestamp.strftime("%Y-%m-%d %H:%M:%S")


def display_time_only(chrome_timestamp: int) -> str:
    timestamp = chrome_timestamp_to_datetime(chrome_timestamp)
    if timestamp is None:
        return "UNKNOWN"
    return timestamp.strftime("%I:%M %p")


def display_date_only(chrome_timestamp: int) -> str:
    timestamp = chrome_timestamp_to_datetime(chrome_timestamp)
    if timestamp is None:
        return "UNKNOWN"
    return timestamp.strftime("%Y-%m-%d")


def _copy_history_to_temp(history_file: str) -> str:
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_path = temp_file.name
    shutil.copyfile(history_file, temp_path)
    return temp_path


def fetch_history(history_file: str) -> List[HistoryEntry]:
    temp_copy = _copy_history_to_temp(history_file)
    try:
        conn = sqlite3.connect(temp_copy)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT url, title, visit_count, last_visit_time "
            "FROM urls ORDER BY last_visit_time DESC"
        )
        rows = cursor.fetchall()
        conn.close()
        return [HistoryEntry(*row) for row in rows]
    finally:
        os.unlink(temp_copy)


def build_table_rows(
    entries: Iterable[HistoryEntry],
) -> List[tuple[str, str, str, str, str, str]]:
    return [
        (
            display_time_only(entry.last_visit_time),
            entry.title or "(no title)",
            str(entry.visit_count),
            entry.url,
            display_timestamp(entry.last_visit_time),
            display_date_only(entry.last_visit_time),
        )
        for entry in entries
    ]


class TitleLabel:  # runtime Qt subclass built in run_gui after Qt imports
    pass


def run_gui(entries: List[HistoryEntry]) -> int:
    try:
        from PyQt6.QtCore import Qt, pyqtSignal
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtWidgets import (
            QApplication,
            QHeaderView,
            QLabel,
            QMainWindow,
            QTableWidget,
            QTableWidgetItem,
            QVBoxLayout,
            QWidget,
        )
        from PyQt6.QtCore import QUrl
        pyqt6 = True
    except ImportError:
        try:
            from PyQt5.QtCore import Qt, pyqtSignal, QUrl  # type: ignore
            from PyQt5.QtGui import QDesktopServices  # type: ignore
            from PyQt5.QtWidgets import (  # type: ignore
                QApplication,
                QHeaderView,
                QLabel,
                QMainWindow,
                QTableWidget,
                QTableWidgetItem,
                QVBoxLayout,
                QWidget,
            )
            pyqt6 = False
        except ImportError:
            print("PyQt is not installed. Install PyQt6 or PyQt5 and try again.")
            return 1

    if pyqt6:
        elide_right = Qt.TextElideMode.ElideRight
        text_word_wrap = Qt.TextFlag.TextWordWrap
        tooltip_role = Qt.ItemDataRole.ToolTipRole
        pointer_cursor = Qt.CursorShape.PointingHandCursor
        no_text_interaction = Qt.TextInteractionFlag.NoTextInteraction
        scroll_bar_off = Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        align_left = Qt.AlignmentFlag.AlignLeft
        align_vcenter = Qt.AlignmentFlag.AlignVCenter
        no_edit_triggers = QTableWidget.EditTrigger.NoEditTriggers
        select_rows = QTableWidget.SelectionBehavior.SelectRows
        single_selection = QTableWidget.SelectionMode.SingleSelection
        stretch_mode = QHeaderView.ResizeMode.Stretch
        resize_to_contents_mode = QHeaderView.ResizeMode.ResizeToContents
        per_pixel_mode = QTableWidget.ScrollMode.ScrollPerPixel
    else:
        elide_right = Qt.ElideRight
        text_word_wrap = Qt.TextWordWrap
        tooltip_role = Qt.ToolTipRole
        pointer_cursor = Qt.PointingHandCursor
        no_text_interaction = Qt.NoTextInteraction
        scroll_bar_off = Qt.ScrollBarAlwaysOff
        align_left = Qt.AlignLeft
        align_vcenter = Qt.AlignVCenter
        no_edit_triggers = QTableWidget.NoEditTriggers
        select_rows = QTableWidget.SelectRows
        single_selection = QTableWidget.SingleSelection
        stretch_mode = QHeaderView.Stretch
        resize_to_contents_mode = QHeaderView.ResizeToContents
        per_pixel_mode = QTableWidget.ScrollPerPixel

    class ClickableTitleLabel(QLabel):
        clicked = pyqtSignal()

        def __init__(self, full_text: str):
            super().__init__()
            self.full_text = full_text
            self.expanded = False
            self.setToolTip(full_text)
            self.setCursor(pointer_cursor)
            self.setTextInteractionFlags(no_text_interaction)
            self.setAlignment(align_left | align_vcenter)
            self._render_text()

        def set_expanded(self, expanded: bool) -> None:
            self.expanded = expanded
            self._render_text()

        def _render_text(self) -> None:
            if self.expanded:
                self.setWordWrap(True)
                self.setText(self.full_text)
                return
            self.setWordWrap(False)
            text_width = max(10, self.width() - 8)
            self.setText(self.fontMetrics().elidedText(self.full_text, elide_right, text_width))

        def resizeEvent(self, event) -> None:  # type: ignore[override]
            super().resizeEvent(event)
            self._render_text()

        def mousePressEvent(self, event) -> None:  # type: ignore[override]
            self.clicked.emit()
            super().mousePressEvent(event)

    class HistoryWindow(QMainWindow):
        collapsed_row_height = 28

        def __init__(self, history_entries: List[HistoryEntry]):
            super().__init__()
            self.entries = history_entries
            self.expanded_row = -1
            self.setWindowTitle("Brave History Viewer")
            self.resize(1100, 700)

            root = QWidget()
            layout = QVBoxLayout(root)
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(6)

            self.top_date_label = QLabel("Date: UNKNOWN")
            self.top_date_label.setStyleSheet("font-weight: 600;")
            layout.addWidget(self.top_date_label)

            self.table = QTableWidget()
            self.table.setColumnCount(3)
            self.table.setHorizontalHeaderLabels(["Last Visit Time", "Title", "Visit Count"])
            self.table.setRowCount(len(self.entries))
            self.table.setAlternatingRowColors(True)
            self.table.verticalHeader().setVisible(False)
            self.table.setEditTriggers(no_edit_triggers)
            self.table.setSelectionBehavior(select_rows)
            self.table.setSelectionMode(single_selection)
            self.table.setHorizontalScrollBarPolicy(scroll_bar_off)
            self.table.setHorizontalScrollMode(per_pixel_mode)
            self.table.setVerticalScrollMode(per_pixel_mode)
            layout.addWidget(self.table)
            self.setCentralWidget(root)

            self._populate_table()
            self._configure_columns()
            self._connect_signals()
            self._update_top_date_header()

        def _populate_table(self) -> None:
            for row_idx, row_data in enumerate(build_table_rows(self.entries)):
                time_short, title, visit_count, url, time_full, _ = row_data

                time_item = QTableWidgetItem(time_short)
                time_item.setData(tooltip_role, time_full)
                self.table.setItem(row_idx, 0, time_item)

                title_label = ClickableTitleLabel(title)
                title_label.setToolTip(f"{title}\n{url}")
                title_label.clicked.connect(partial(self._open_row_url, row_idx))
                self.table.setCellWidget(row_idx, 1, title_label)

                count_item = QTableWidgetItem(visit_count)
                self.table.setItem(row_idx, 2, count_item)
                self.table.setRowHeight(row_idx, self.collapsed_row_height)

        def _configure_columns(self) -> None:
            header = self.table.horizontalHeader()
            header.setSectionResizeMode(0, resize_to_contents_mode)
            header.setSectionResizeMode(1, stretch_mode)
            header.setSectionResizeMode(2, resize_to_contents_mode)
            self.table.setColumnWidth(0, max(self.table.columnWidth(0), 120))
            self.table.setColumnWidth(2, max(self.table.columnWidth(2), 90))

        def _connect_signals(self) -> None:
            self.table.cellClicked.connect(self._toggle_row)
            self.table.horizontalHeader().sectionResized.connect(self._on_column_resize)
            self.table.verticalScrollBar().valueChanged.connect(
                lambda _: self._update_top_date_header()
            )

        def _toggle_row(self, row: int, _: int) -> None:
            if row == self.expanded_row:
                self._set_row_expanded(row, False)
                self.expanded_row = -1
                return

            if self.expanded_row >= 0:
                self._set_row_expanded(self.expanded_row, False)
            self.expanded_row = row
            self._set_row_expanded(row, True)

        def _set_row_expanded(self, row: int, expanded: bool) -> None:
            title_label = self.table.cellWidget(row, 1)
            if title_label is None:
                return
            title_label.set_expanded(expanded)
            if expanded:
                column_width = max(40, self.table.columnWidth(1) - 14)
                text = title_label.full_text
                rect = title_label.fontMetrics().boundingRect(
                    0, 0, column_width, 10000, text_word_wrap, text
                )
                self.table.setRowHeight(row, max(self.collapsed_row_height, rect.height() + 12))
            else:
                self.table.setRowHeight(row, self.collapsed_row_height)

        def _on_column_resize(self, logical_index: int, *_args) -> None:
            if logical_index != 1:
                return
            for row in range(self.table.rowCount()):
                label = self.table.cellWidget(row, 1)
                if label is not None:
                    label._render_text()
            if self.expanded_row >= 0:
                self._set_row_expanded(self.expanded_row, True)

        def _open_row_url(self, row: int) -> None:
            url = self.entries[row].url
            if url:
                QDesktopServices.openUrl(QUrl(url))

        def _update_top_date_header(self) -> None:
            row = self.table.rowAt(0)
            if row < 0 or row >= len(self.entries):
                self.top_date_label.setText("Date: UNKNOWN")
                return
            self.top_date_label.setText(
                f"Date: {display_date_only(self.entries[row].last_visit_time)}"
            )

    app = QApplication(sys.argv)
    window = HistoryWindow(entries)
    window.show()
    return app.exec()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Open Brave history in a scrollable GUI table."
    )
    parser.add_argument(
        "--history-file",
        default=os.environ.get("BRAVE_HISTORY_FILE", DEFAULT_HISTORY_FILE),
        help="Path to the Brave History SQLite file.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if not os.path.exists(args.history_file):
        print(f"History file not found: {args.history_file}")
        return 1

    entries = fetch_history(args.history_file)
    print(f"Loaded {len(entries)} history entries.")
    return run_gui(entries)


if __name__ == "__main__":
    raise SystemExit(main())
