from pathlib import Path
import tempfile
import unittest

from botw_companion.save_caption import SaveCaptionError, read_selected_caption


def jpeg_payload(marker: bytes = b"preview") -> bytes:
    return b"\xff\xd8\xff\xe0" + marker.ljust(124, b"\0") + b"\xff\xd9"


class SaveCaptionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.slot = Path(self.temporary.name) / "1"
        self.slot.mkdir()
        self.report = {"sauvegarde": {"chemin": str(self.slot)}}

    def tearDown(self):
        self.temporary.cleanup()

    def test_selected_slot_jpeg_is_returned_with_a_stable_etag(self):
        content = jpeg_payload()
        (self.slot / "caption.jpg").write_bytes(content)
        caption = read_selected_caption(self.report)
        self.assertEqual(caption.data, content)
        self.assertEqual(len(caption.etag), 64)
        self.assertEqual(caption.etag, read_selected_caption(self.report).etag)

    def test_ryujinx_fixed_size_zero_padding_is_removed(self):
        content = jpeg_payload(b"ryujinx")
        (self.slot / "caption.jpg").write_bytes(content + b"\0" * 512)
        self.assertEqual(read_selected_caption(self.report).data, content)

    def test_missing_or_invalid_preview_is_rejected(self):
        with self.assertRaisesRegex(SaveCaptionError, "indisponible"):
            read_selected_caption(self.report)
        (self.slot / "caption.jpg").write_bytes(b"not a jpeg" * 20)
        with self.assertRaisesRegex(SaveCaptionError, "JPEG"):
            read_selected_caption(self.report)

    def test_report_cannot_choose_a_filename_outside_the_selected_slot(self):
        outside = Path(self.temporary.name) / "outside.jpg"
        outside.write_bytes(jpeg_payload(b"outside"))
        link = self.slot / "caption.jpg"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("Liens symboliques indisponibles sur cette plateforme")
        with self.assertRaisesRegex(SaveCaptionError, "symbolique"):
            read_selected_caption(self.report)

    def test_caption_being_replaced_is_never_served_partially(self):
        (self.slot / "caption.jpg").write_bytes(b"\xff\xd8\xff")
        with self.assertRaisesRegex(SaveCaptionError, "Taille"):
            read_selected_caption(self.report)


if __name__ == "__main__":
    unittest.main()