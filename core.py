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


def build_table_rows(entries: Iterable[HistoryEntry]) -> List[tuple[str, str, str, str]]:
    return [
        (
            entry.title or "(no title)",
            entry.url,
            str(entry.visit_count),
            display_timestamp(entry.last_visit_time),
        )
        for entry in entries
    ]


def run_gui(entries: List[HistoryEntry]) -> int:
    try:
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import (
            QApplication,
            QHeaderView,
            QMainWindow,
            QTableWidget,
            QTableWidgetItem,
        )
    except ImportError:
        from PyQt5.QtCore import Qt  # type: ignore
        from PyQt5.QtWidgets import (  # type: ignore
            QApplication,
            QHeaderView,
            QMainWindow,
            QTableWidget,
            QTableWidgetItem,
        )

    app = QApplication(sys.argv)
    window = QMainWindow()
    window.setWindowTitle("Brave History Viewer")
    window.resize(1100, 700)

    table = QTableWidget()
    headers = ["Title", "URL", "Visit Count", "Last Visit Time"]
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setRowCount(len(entries))
    table.setWordWrap(False)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    table.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
    table.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)

    for row_idx, row_data in enumerate(build_table_rows(entries)):
        for col_idx, value in enumerate(row_data):
            item = QTableWidgetItem(value)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row_idx, col_idx, item)

    header = table.horizontalHeader()
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
    header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
    header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

    window.setCentralWidget(table)
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
