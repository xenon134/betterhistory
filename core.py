import argparse
import datetime
import os
import shutil
import sqlite3
import sys
import tempfile
from collections import OrderedDict
from typing import List, Optional, Tuple

DEFAULT_HISTORY_FILE = (
    r"C:\Users\deep\AppData\Local\BraveSoftware\Brave-Browser\User Data\Default\History"
)
CHROME_EPOCH_OFFSET_SECONDS = 11644473600

VisitRow = Tuple[int, str, str]  # (chrome visit_time, url, title)


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


def count_visits(history_file: str) -> int:
    conn = sqlite3.connect(history_file)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM visits")
        return int(cursor.fetchone()[0])
    finally:
        conn.close()


def fetch_visit_chunk(history_file: str, offset: int, limit: int) -> List[VisitRow]:
    """Fetch a page of visits (most recent first) joined with their URL/title."""
    conn = sqlite3.connect(history_file)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT v.visit_time, u.url, COALESCE(u.title, '') "
            "FROM visits v JOIN urls u ON u.id = v.url "
            "ORDER BY v.visit_time DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return [(row[0], row[1], row[2]) for row in cursor.fetchall()]
    finally:
        conn.close()


def run_gui(history_file: str) -> int:
    try:
        from PyQt6.QtCore import QAbstractTableModel, QEvent, QModelIndex, Qt
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtWidgets import (
            QApplication,
            QHeaderView,
            QLabel,
            QMainWindow,
            QStyledItemDelegate,
            QTableView,
            QVBoxLayout,
            QWidget,
        )
        from PyQt6.QtCore import QUrl
        pyqt6 = True
    except ImportError:
        try:
            from PyQt5.QtCore import QAbstractTableModel, QEvent, QModelIndex, Qt, QUrl  # type: ignore
            from PyQt5.QtGui import QDesktopServices  # type: ignore
            from PyQt5.QtWidgets import (  # type: ignore
                QApplication,
                QHeaderView,
                QLabel,
                QMainWindow,
                QStyledItemDelegate,  # type: ignore
                QTableView,  # type: ignore
                QVBoxLayout,
                QWidget,
            )
            pyqt6 = False
        except ImportError:
            print("PyQt is not installed. Install PyQt6 or PyQt5 and try again.")
            return 1

    if pyqt6:
        tooltip_role = Qt.ItemDataRole.ToolTipRole
        stretch_mode = QHeaderView.ResizeMode.Stretch
        resize_to_contents_mode = QHeaderView.ResizeMode.ResizeToContents
        fixed_mode = QHeaderView.ResizeMode.Fixed
        per_pixel_mode = QTableView.ScrollMode.ScrollPerPixel
    else:
        tooltip_role = Qt.ToolTipRole
        stretch_mode = QHeaderView.Stretch
        resize_to_contents_mode = QHeaderView.ResizeToContents
        fixed_mode = QHeaderView.Fixed
        per_pixel_mode = QTableView.ScrollPerPixel

    url_role = Qt.ItemDataRole.UserRole if pyqt6 else Qt.UserRole
    display_role = Qt.ItemDataRole.DisplayRole if pyqt6 else Qt.DisplayRole

    class LazyVisitModel(QAbstractTableModel):
        page_size = 2000
        max_cached_rows = 200_000

        def __init__(self, db_path: str) -> None:
            super().__init__()
            self._db_path = db_path
            self._total = count_visits(db_path)
            self._max_pages = max(1, self.max_cached_rows // self.page_size)
            self._cache: OrderedDict[int, List[VisitRow]] = OrderedDict()

        # -- Qt model interface ------------------------------------------------
        def rowCount(self, parent=QModelIndex()):  # type: ignore[override]
            if parent.isValid():
                return 0
            return self._total

        def columnCount(self, parent=QModelIndex()):  # type: ignore[override]
            return 2

        def headerData(self, section, orientation, role=display_role):  # type: ignore[override]
            if (
                orientation == (Qt.Orientation.Horizontal if pyqt6 else Qt.Horizontal)
                and role == display_role
            ):
                return ["Last Visit Time", "Title"][section]
            return None

        def data(self, index, role=display_role):  # type: ignore[override]
            if not index.isValid() or index.row() >= self._total:
                return None
            row = self._row(index.row())
            chrome_time, url, title = row
            col = index.column()
            if role == display_role:
                if col == 0:
                    return display_time_only(chrome_time)
                return title or "(no title)"
            if role == tooltip_role:
                if col == 0:
                    return display_timestamp(chrome_time)
                return f"{title}\n{url}" if title else url
            if role == url_role and col == 1:
                return url
            return None

        # -- helpers -----------------------------------------------------------
        def _row(self, row: int) -> VisitRow:
            page_idx, offset = divmod(row, self.page_size)
            page = self._cache.get(page_idx)
            if page is None:
                page = self._load_page(page_idx)
            return page[offset]

        def _load_page(self, page_idx: int) -> List[VisitRow]:
            offset = page_idx * self.page_size
            page = fetch_visit_chunk(self._db_path, offset, self.page_size)
            self._cache[page_idx] = page
            while len(self._cache) > self._max_pages:
                self._cache.popitem(last=False)
            return page

        def datetime_for_row(self, row: int) -> Optional[datetime.datetime]:
            if not 0 <= row < self._total:
                return None
            return chrome_timestamp_to_datetime(self._row(row)[0])

        def total_rows(self) -> int:
            return self._total

    class TitleDelegate(QStyledItemDelegate):
        def paint(self, painter, option, index) -> None:  # type: ignore[override]
            super().paint(painter, option, index)

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

        def __init__(self, model: LazyVisitModel):
            super().__init__()
            self.model = model
            self.setWindowTitle("Brave History Viewer")
            self.resize(1100, 700)

            root = QWidget()
            layout = QVBoxLayout(root)
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(6)

            self.top_date_label = QLabel("Date: UNKNOWN")
            self.top_date_label.setStyleSheet("font-weight: 600;")
            layout.addWidget(self.top_date_label)

            self.table = QTableView()
            self.table.setModel(model)
            self.table.setAlternatingRowColors(True)
            self.table.verticalHeader().setVisible(False)
            self.table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
            self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
            self.table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
            self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.table.setHorizontalScrollMode(per_pixel_mode)
            self.table.setVerticalScrollMode(per_pixel_mode)
            self.table.verticalHeader().setDefaultSectionSize(self.collapsed_row_height)
            self.table.verticalHeader().setSectionResizeMode(fixed_mode)
            layout.addWidget(self.table)
            self.setCentralWidget(root)

            self.title_delegate = TitleDelegate(self.table)
            self.table.setItemDelegateForColumn(1, self.title_delegate)
            self._configure_columns()
            self._connect_signals()
            self._update_top_date_header()

        def _configure_columns(self) -> None:
            header = self.table.horizontalHeader()
            header.setSectionResizeMode(0, resize_to_contents_mode)
            header.setSectionResizeMode(1, stretch_mode)
            self.table.setColumnWidth(0, max(self.table.columnWidth(0), 120))

        def _connect_signals(self) -> None:
            self.table.verticalScrollBar().valueChanged.connect(
                lambda _: self._update_top_date_header()
            )

        def _update_top_date_header(self) -> None:
            row = self.table.rowAt(0)
            dt = self.model.datetime_for_row(row) if row >= 0 else None
            if dt is None:
                self.top_date_label.setText("Date: UNKNOWN")
                return
            self.top_date_label.setText(f"Date: {dt.strftime('%Y-%m-%d')}")

    temp_path = _copy_history_to_temp(history_file)
    app = QApplication(sys.argv)
    model = LazyVisitModel(temp_path)
    window = HistoryWindow(model)
    window.show()
    try:
        return app.exec()
    finally:
        del model
        os.unlink(temp_path)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Open Brave visit history in a scrollable GUI table."
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

    if args.profile:
        import cProfile
        import pstats

        profiler = cProfile.Profile()
        profiler.enable()
        code = run_gui(args.history_file)
        profiler.disable()
        stats = pstats.Stats(profiler)
        stats.sort_stats("cumulative").print_stats(30)
        return code
    return run_gui(args.history_file)


if __name__ == "__main__":
    raise SystemExit(main())
