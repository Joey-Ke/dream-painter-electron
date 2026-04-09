from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
from PIL import Image, ImageDraw

from app.schemas import RecognizedSubject
from app.services.ai_step_generator import generate_steps_ai
from app.services.lineart_generator import RealSeedreamGenerator
from app.services.step_builder import StepBuilder
from app.utils.image_io import normalize_generated_lineart


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, content: str) -> None:
        self._content = content

    def create(self, **kwargs):  # noqa: ANN003
        return _FakeResponse(self._content)


class _FakeChat:
    def __init__(self, content: str) -> None:
        self.completions = _FakeCompletions(content)


class _FakeClient:
    def __init__(self, content: str) -> None:
        self.chat = _FakeChat(content)


def _make_simple_cat_lineart(path: Path) -> None:
    image = Image.new("RGB", (320, 320), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((95, 35, 225, 155), outline="black", width=6)
    draw.polygon([(110, 55), (135, 15), (155, 65)], outline="black", width=6)
    draw.polygon([(165, 65), (185, 15), (210, 55)], outline="black", width=6)
    draw.ellipse((125, 80, 145, 100), outline="black", width=4)
    draw.ellipse((175, 80, 195, 100), outline="black", width=4)
    draw.ellipse((85, 145, 235, 270), outline="black", width=6)
    draw.line((125, 205, 125, 290), fill="black", width=6)
    draw.line((195, 205, 195, 290), fill="black", width=6)
    draw.arc((205, 165, 285, 265), 260, 110, fill="black", width=6)
    image.save(path)


def _make_simple_duck_lineart(path: Path) -> None:
    image = Image.new("RGB", (320, 320), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((150, 40, 240, 120), outline="black", width=5)
    draw.polygon([(150, 72), (105, 62), (115, 84), (150, 88)], outline="black", width=5)
    draw.ellipse((182, 66, 194, 78), outline="black", width=3)
    draw.arc((138, 88, 190, 164), 180, 300, fill="black", width=5)
    draw.arc((128, 94, 214, 264), 195, 350, fill="black", width=6)
    draw.arc((110, 138, 224, 272), 10, 175, fill="black", width=6)
    draw.arc((150, 155, 208, 222), 205, 28, fill="black", width=4)
    draw.line((112, 165, 88, 154), fill="black", width=5)
    draw.line((112, 178, 84, 190), fill="black", width=5)
    draw.line((160, 246, 156, 286), fill="black", width=4)
    draw.line((188, 246, 184, 286), fill="black", width=4)
    draw.line((144, 286, 170, 286), fill="black", width=4)
    draw.line((172, 286, 198, 286), fill="black", width=4)
    image.save(path)


def _count_dark_pixels(path: Path) -> int:
    gray = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    assert gray is not None
    return int((gray < 220).sum())


def _top_band_dark_pixels(path: Path) -> int:
    gray = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    assert gray is not None
    band = gray[:40, :]
    return int((band < 220).sum())


class StepPlanningTests(unittest.TestCase):
    def test_generate_steps_ai_normalizes_cumulative_part_plan(self) -> None:
        raw_payload = {
            "subject": "duck",
            "overall_shape": "side view duck facing right",
            "parts": ["head", "beak", "body", "wing", "legs"],
            "steps": [
                {
                    "title": "Step 1",
                    "instruction": "Draw the head and beak.",
                    "new_parts": ["head", "beak"],
                    "hidden_parts": ["body", "wing", "legs"],
                },
                {
                    "title": "Step 2",
                    "instruction": "Add the body.",
                    "new_parts": ["body"],
                },
                {
                    "title": "Step 3",
                    "instruction": "Add the wing and legs.",
                    "new_parts": ["wing", "legs"],
                },
            ],
        }

        with patch(
            "app.services.ai_step_generator._get_client",
            return_value=_FakeClient(str(raw_payload).replace("'", '"')),
        ):
            plan = generate_steps_ai(subject="duck", prompt="standing pose", step_count=3)

        self.assertEqual(plan["stepCount"], 3)
        self.assertEqual(plan["steps"][0]["new_parts"], ["head", "beak"])
        self.assertEqual(plan["steps"][1]["keep_parts"], ["head", "beak"])
        self.assertEqual(plan["steps"][2]["visible_parts"], ["head", "beak", "body", "wing", "legs"])
        self.assertEqual(plan["steps"][2]["hidden_parts"], [])

    def test_step_builder_creates_cumulative_frames_from_one_lineart(self) -> None:
        step_plan = {
            "parts": ["head", "ears", "body", "front legs", "tail"],
            "steps": [
                {"instruction": "Draw the head.", "visible_parts": ["head"], "keep_parts": [], "new_parts": ["head"]},
                {
                    "instruction": "Add the ears.",
                    "visible_parts": ["head", "ears"],
                    "keep_parts": ["head"],
                    "new_parts": ["ears"],
                },
                {
                    "instruction": "Add the body and legs.",
                    "visible_parts": ["head", "ears", "body", "front legs"],
                    "keep_parts": ["head", "ears"],
                    "new_parts": ["body", "front legs"],
                },
                {
                    "instruction": "Finish the tail.",
                    "visible_parts": ["head", "ears", "body", "front legs", "tail"],
                    "keep_parts": ["head", "ears", "body", "front legs"],
                    "new_parts": ["tail"],
                },
            ],
        }

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            lineart_path = tmp_path / "lineart.png"
            frames_dir = tmp_path / "frames"
            _make_simple_cat_lineart(lineart_path)

            steps = StepBuilder().build_steps(
                lineart_path=lineart_path,
                output_dir=frames_dir,
                step_plan=step_plan,
                fps=2,
                subject_label="cat",
            )

            counts = [_count_dark_pixels(frames_dir / f"frame_{i:03d}.png") for i in range(steps["stepCount"])]
            self.assertEqual(steps["stepCount"], 4)
            self.assertTrue(counts[0] < counts[1] < counts[2] < counts[3])

    def test_step_builder_understands_chinese_part_names(self) -> None:
        step_plan = {
            "parts": ["头部轮廓", "耳朵", "眼睛", "身体", "尾巴"],
            "steps": [
                {"instruction": "先画头部轮廓", "visible_parts": ["头部轮廓"], "new_parts": ["头部轮廓"]},
                {"instruction": "再加耳朵", "visible_parts": ["头部轮廓", "耳朵"], "new_parts": ["耳朵"]},
                {"instruction": "画眼睛", "visible_parts": ["头部轮廓", "耳朵", "眼睛"], "new_parts": ["眼睛"]},
            ],
        }

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            lineart_path = tmp_path / "lineart.png"
            frames_dir = tmp_path / "frames"
            _make_simple_cat_lineart(lineart_path)

            StepBuilder().build_steps(
                lineart_path=lineart_path,
                output_dir=frames_dir,
                step_plan=step_plan,
                fps=2,
                subject_label="猫",
            )

            counts = [_count_dark_pixels(frames_dir / f"frame_{i:03d}.png") for i in range(3)]
            self.assertTrue(counts[0] < counts[1] < counts[2])

    def test_step_builder_uses_duck_lineart_instead_of_abstract_template(self) -> None:
        step_plan = {
            "parts": ["头", "喙", "眼睛", "脖子", "背部", "腹部", "翅膀", "尾巴", "腿", "脚蹼"],
            "steps": [
                {"instruction": "画头", "visible_parts": ["头"], "new_parts": ["头"]},
                {"instruction": "加嘴", "visible_parts": ["头", "喙"], "new_parts": ["喙"]},
                {"instruction": "加眼睛", "visible_parts": ["头", "喙", "眼睛"], "new_parts": ["眼睛"]},
                {
                    "instruction": "加身体",
                    "visible_parts": ["头", "喙", "眼睛", "脖子", "背部", "腹部"],
                    "new_parts": ["脖子", "背部", "腹部"],
                },
            ],
        }

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            lineart_path = tmp_path / "duck.png"
            frames_dir = tmp_path / "frames"
            _make_simple_duck_lineart(lineart_path)

            StepBuilder().build_steps(
                lineart_path=lineart_path,
                output_dir=frames_dir,
                step_plan=step_plan,
                fps=2,
                subject_label="鸭子",
            )

            counts = [_count_dark_pixels(frames_dir / f"frame_{i:03d}.png") for i in range(4)]
            self.assertTrue(counts[0] < counts[1] < counts[2] < counts[3])

            frame1 = cv2.imread(str(frames_dir / "frame_001.png"), cv2.IMREAD_GRAYSCALE)
            self.assertIsNotNone(frame1)
            beak_region = frame1[55:95, 100:155]
            self.assertGreater(int((beak_region < 220).sum()), 25)

    def test_normalize_generated_lineart_removes_top_border_noise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            raw_path = tmp_path / "raw.png"
            clean_path = tmp_path / "clean.png"

            image = Image.new("RGB", (320, 320), (245, 235, 210))
            draw = ImageDraw.Draw(image)
            draw.rectangle((10, 10, 310, 310), outline="black", width=3)
            draw.line((0, 20, 320, 20), fill="black", width=4)
            draw.ellipse((95, 35, 225, 155), outline="black", width=6)
            draw.polygon([(110, 55), (135, 15), (155, 65)], outline="black", width=6)
            draw.polygon([(165, 65), (185, 15), (210, 55)], outline="black", width=6)
            draw.ellipse((85, 145, 235, 270), outline="black", width=6)
            image.save(raw_path)

            normalize_generated_lineart(raw_path, clean_path, size=320)

            self.assertLess(_top_band_dark_pixels(clean_path), _top_band_dark_pixels(raw_path))

    def test_lineart_prompt_is_now_for_single_final_lineart(self) -> None:
        with patch.dict("os.environ", {"SEEDREAM5_API_KEY": "test-key"}, clear=False):
            generator = RealSeedreamGenerator()

        prompt = generator._build_final_lineart_prompt(
            subject=RecognizedSubject(label="duck"),
            user_prompt="",
            step_plan={
                "overall_shape": "side view duck",
                "parts": ["head", "beak", "body", "legs"],
            },
        )

        self.assertIn("one final children's drawing worksheet line art", prompt)
        self.assertIn("split into step-by-step drawing frames later", prompt)
        self.assertIn("Black outline only", prompt)
        self.assertIn("close to the reference silhouette and proportions", prompt)
        self.assertIn("Do not add a decorative border, plants, grass, water, puddles, reeds", prompt)

    def test_seedream5_defaults_use_real_endpoint_and_model(self) -> None:
        with patch.dict("os.environ", {"SEEDREAM5_API_KEY": "test-key"}, clear=False):
            generator = RealSeedreamGenerator()

        self.assertEqual(
            generator.url,
            "https://operator.las.cn-beijing.volces.com/api/v1/online/images/generations",
        )
        self.assertEqual(generator.model, "doubao-seedream-5-0-lite-260128")
        self.assertEqual(generator.request_size, "2048x2048")
        self.assertEqual(generator.response_format, "url")
        self.assertEqual(generator.output_format, "png")

    def test_seedream5_download_supports_wrapped_response(self) -> None:
        with patch.dict("os.environ", {"SEEDREAM5_API_KEY": "test-key"}, clear=False):
            generator = RealSeedreamGenerator()

        payload = {
            "code": 0,
            "data": {
                "data": [
                    {
                        "b64_json": "aGVsbG8=",
                    }
                ]
            },
        }
        self.assertEqual(generator._download_image_bytes(payload), b"hello")


if __name__ == "__main__":
    unittest.main()
