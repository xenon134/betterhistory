import argparse
import datetime
import os
import shutil
import sqlite3
import sys
import tempfile
from dataclasses import dataclass
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
        from PyQt6.QtCore import QEvent, Qt
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtWidgets import (
            QApplication,
            QHeaderView,
            QLabel,
            QMainWindow,
            QStyledItemDelegate,
            QStyle,
            QStyleOptionViewItem,
            QTableWidget,
            QTableWidgetItem,
            QVBoxLayout,
            QWidget,
        )
        from PyQt6.QtCore import QUrl
        pyqt6 = True
    except ImportError:
        try:
            from PyQt5.QtCore import QEvent, Qt, QUrl  # type: ignore
            from PyQt5.QtGui import QDesktopServices  # type: ignore
            from PyQt5.QtWidgets import (  # type: ignore
                QApplication,
                QHeaderView,
                QLabel,
                QMainWindow,
                QStyledItemDelegate,  # type: ignore
                QStyle,  # type: ignore
                QStyleOptionViewItem,  # type: ignore
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
        scroll_bar_off = Qt.ScrollBarAlwaysOff
        align_left = Qt.AlignLeft
        align_vcenter = Qt.AlignVCenter
        no_edit_triggers = QTableWidget.NoEditTriggers
        select_rows = QTableWidget.SelectRows
        single_selection = QTableWidget.SingleSelection
        stretch_mode = QHeaderView.Stretch
        resize_to_contents_mode = QHeaderView.ResizeToContents
        per_pixel_mode = QTableWidget.ScrollPerPixel

    url_role = Qt.ItemDataRole.UserRole if pyqt6 else Qt.UserRole
    display_role = Qt.ItemDataRole.DisplayRole if pyqt6 else Qt.DisplayRole

    class TitleDelegate(QStyledItemDelegate):
        expanded_row = -1

        def _measure_wrap_height(self, font_metrics, text: str, width: int) -> int:
            rect = font_metrics.boundingRect(
                0, 0, width, 10000, text_word_wrap, text
            )
            return max(28, rect.height() + 10)

        def sizeHint(self, option, index):  # type: ignore[override]
            size = super().sizeHint(option, index)
            if index.row() == self.expanded_row:
                text = index.data(display_role) or ""
                width = max(40, self.parent().columnWidth(1) - 6)
                size.setHeight(
                    self._measure_wrap_height(option.fontMetrics, text, width)
                )
            return size

        def paint(self, painter, option, index) -> None:  # type: ignore[override]
            style_option = QStyleOptionViewItem(option)
            self.initStyleOption(style_option, index)
            text = index.data(display_role) or ""

            painter.save()
            painter.setClipRect(option.rect)
            if style_option.state & QStyle.StateFlag.State_Selected:
                painter.fillRect(option.rect, style_option.palette.highlight())
                painter.setPen(style_option.palette.highlightedText().color())
            else:
                painter.setPen(style_option.palette.text().color())

            if index.row() == self.expanded_row:
                painter.drawText(
                    option.rect.adjusted(4, 3, -4, -3),
                    align_left | align_vcenter | text_word_wrap,
                    text,
                )
            else:
                elided = style_option.fontMetrics.elidedText(
                    text, elide_right, max(1, option.rect.width() - 8)
                )
                painter.drawText(
                    option.rect.adjusted(4, 3, -4, -3),
                    align_left | align_vcenter,
                    elided,
                )
            painter.restore()

        def editorEvent(self, event, model, option, index):  # type: ignore[override]
            if (
                event.type() == QEvent.Type.MouseButtonPress
                and index.column() == 1
                and event.button() == Qt.MouseButton.LeftButton
            ):
                url = index.data(url_role)
                if url:
                    QDesktopServices.openUrl(QUrl(url))
                return True
            return super().editorEvent(event, model, option, index)

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

            self.title_delegate = TitleDelegate(self.table)
            self.table.setItemDelegateForColumn(1, self.title_delegate)

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

                title_item = QTableWidgetItem(title)
                title_item.setData(url_role, url)
                title_item.setData(tooltip_role, f"{title}\n{url}" if url else title)
                self.table.setItem(row_idx, 1, title_item)

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
            self.table.verticalScrollBar().valueChanged.connect(
                lambda _: self._update_top_date_header()
            )

        def _toggle_row(self, row: int, _: int) -> None:
            if row == self.expanded_row:
                self._set_row_expanded(row, False)
                self.expanded_row = -1
                self.title_delegate.expanded_row = -1
                return

            if self.expanded_row >= 0:
                self._set_row_expanded(self.expanded_row, False)
            self.expanded_row = row
            self.title_delegate.expanded_row = row
            self._set_row_expanded(row, True)

        def _set_row_expanded(self, row: int, expanded: bool) -> None:
            if expanded:
                column_width = max(40, self.table.columnWidth(1) - 6)
                text = self.table.item(row, 1).text()
                height = max(
                    self.collapsed_row_height,
                    self.title_delegate._measure_wrap_height(
                        self.table.fontMetrics(), text, column_width
                    ),
                )
                self.table.setRowHeight(row, height)
            else:
                self.table.setRowHeight(row, self.collapsed_row_height)
            self.table.viewport().update()

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
    parser.add_argument(
        "--profile",
        action="store_true",
        help="Profile the GUI under cProfile and print a sorted stats dump on exit.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if not os.path.exists(args.history_file):
        print(f"History file not found: {args.history_file}")
        return 1

    entries = fetch_history(args.history_file)
    print(f"Loaded {len(entries)} history entries.")

    if args.profile:
        import cProfile
        import pstats

        profiler = cProfile.Profile()
        profiler.enable()
        code = run_gui(entries)
        profiler.disable()
        stats = pstats.Stats(profiler)
        stats.sort_stats("cumulative").print_stats(30)
        return code
    return run_gui(entries)


if __name__ == "__main__":
    raise SystemExit(main())
