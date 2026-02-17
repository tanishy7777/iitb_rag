from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from digital_brain.sql_dump import rows_for_table


class SqlDumpParsingTest(unittest.TestCase):
    def test_parse_insert_block(self) -> None:
        sql = """
        CREATE TABLE `demo` (`id` int, `name` text, `notes` text);
        INSERT INTO `demo` (`id`, `name`, `notes`) VALUES
        (1, 'alpha', 'line1\\nline2'),
        (2, 'beta', 'value with comma, inside');
        """

        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "demo.sql"
            path.write_text(sql, encoding="utf-8")

            cols, rows = rows_for_table(path, "demo")

        self.assertEqual(cols, ["id", "name", "notes"])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][0], 1)
        self.assertEqual(rows[0][2], "line1\nline2")
        self.assertEqual(rows[1][2], "value with comma, inside")


if __name__ == "__main__":
    unittest.main()
