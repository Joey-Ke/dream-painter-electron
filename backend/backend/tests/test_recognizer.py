from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

from app.services.recognizer import (
    AutoVisionRecognizer,
    CAT_LABEL,
    LocalHeuristicRecognizer,
    TREE_LABEL,
    build_recognizer,
)


def _make_cat_like_image(path: Path) -> None:
    image = Image.new("RGB", (360, 640), (92, 74, 62))
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle((85, 120, 275, 500), radius=80, fill="white", outline="black", width=10)
    draw.polygon([(110, 180), (145, 80), (185, 170)], fill="white", outline="black")
    draw.polygon([(175, 170), (215, 80), (250, 180)], fill="white", outline="black")
    draw.ellipse((125, 205, 155, 235), fill="black")
    draw.ellipse((205, 205, 235, 235), fill="black")
    draw.ellipse((142, 255, 157, 270), fill=(255, 120, 120))
    draw.ellipse((203, 255, 218, 270), fill=(255, 120, 120))
    draw.line((95, 240, 145, 245), fill="black", width=4)
    draw.line((215, 245, 265, 240), fill="black", width=4)
    draw.ellipse((145, 410, 180, 520), fill="white", outline="black", width=8)
    draw.arc((220, 380, 320, 530), 250, 110, fill="black", width=8)
    draw.polygon([(150, 290), (180, 260), (210, 290), (180, 330)], fill=(220, 30, 30), outline="black")

    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


class RecognizerTests(unittest.TestCase):
    def test_local_heuristic_recognizes_cat_like_image(self) -> None:
        recognizer = LocalHeuristicRecognizer()

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            image_path = tmp_path / "cat.png"
            debug_dir = tmp_path / "debug"
            _make_cat_like_image(image_path)

            subject = recognizer.recognize(image_path=image_path, user_prompt="", debug_dir=debug_dir)

            self.assertEqual(subject.label, CAT_LABEL)
            self.assertNotEqual(subject.label, TREE_LABEL)

    def test_auto_recognizer_falls_back_to_local_when_remote_fails(self) -> None:
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=False):
            recognizer = AutoVisionRecognizer()

        with tempfile.TemporaryDirectory() as tmp, patch(
            "app.services.recognizer.RealQwenRecognizer.recognize",
            side_effect=RuntimeError("remote failed"),
        ):
            tmp_path = Path(tmp)
            image_path = tmp_path / "cat.png"
            debug_dir = tmp_path / "debug"
            _make_cat_like_image(image_path)

            subject = recognizer.recognize(image_path=image_path, user_prompt="", debug_dir=debug_dir)

            self.assertEqual(subject.label, CAT_LABEL)

    def test_build_recognizer_auto_is_supported(self) -> None:
        recognizer = build_recognizer("auto")
        self.assertIsInstance(recognizer, AutoVisionRecognizer)


if __name__ == "__main__":
    unittest.main()
