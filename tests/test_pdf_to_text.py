"""Paper ids must not depend on where the run folder sits."""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from pdf_to_text import paper_id_for  # noqa: E402


class PaperIdTest(unittest.TestCase):
    def test_same_pdf_keeps_its_id_when_the_folder_moves(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp, 'a', 'Paper.pdf')
            first.parent.mkdir()
            first.write_bytes(b'%PDF-1.4 one')
            moved = Path(shutil.copytree(first.parent, Path(tmp, 'b')), 'Paper.pdf')
            self.assertEqual(paper_id_for(first), paper_id_for(moved))
            moved.write_bytes(b'%PDF-1.4 two')
            self.assertNotEqual(paper_id_for(first), paper_id_for(moved))


if __name__ == '__main__':
    unittest.main()
