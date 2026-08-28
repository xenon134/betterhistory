import os
import sqlite3
import tempfile
import unittest

from core import (
    HistoryEntry,
    build_table_rows,
    chrome_timestamp_to_datetime,
    display_date_only,
    display_time_only,
    fetch_history,
)


class CoreTests(unittest.TestCase):
    def _create_history_db(self) -> str:
        fd, path = tempfile.mkstemp(suffix=".sqlite")
        os.close(fd)
        conn = sqlite3.connect(path)
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE urls ("
            "url TEXT, title TEXT, visit_count INTEGER, last_visit_time INTEGER)"
        )
        cursor.executemany(
            "INSERT INTO urls (url, title, visit_count, last_visit_time) VALUES (?, ?, ?, ?)",
            [
                ("https://example.com/a", "A", 3, 13390000000000000),
                ("https://example.com/b", "B", 5, 13380000000000000),
            ],
        )
        conn.commit()
        conn.close()
        return path

    def test_chrome_timestamp_zero_returns_none(self) -> None:
        self.assertIsNone(chrome_timestamp_to_datetime(0))

    def test_fetch_history_returns_sorted_entries(self) -> None:
        db_path = self._create_history_db()
        try:
            rows = fetch_history(db_path)
        finally:
            os.unlink(db_path)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].title, "A")
        self.assertEqual(rows[1].title, "B")

    def test_build_table_rows_formats_defaults(self) -> None:
        rows = build_table_rows(
            [HistoryEntry(url="https://example.com", title="", visit_count=1, last_visit_time=0)]
        )
        self.assertEqual(rows[0][1], "(no title)")
        self.assertEqual(rows[0][0], "UNKNOWN")
        self.assertEqual(rows[0][2], "1")
        self.assertEqual(rows[0][4], "UNKNOWN")
        self.assertEqual(rows[0][5], "UNKNOWN")

    def test_time_only_format(self) -> None:
        self.assertEqual(display_time_only(0), "UNKNOWN")

    def test_date_only_format(self) -> None:
        self.assertEqual(display_date_only(0), "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
