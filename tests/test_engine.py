"""轻量单元测试：只验证包结构与参数解析，不需要模型、不需要 rembg。

跑法::

    python -m unittest discover -s tests -v

之所以能这么轻：``whitebg.engine`` 顶层只依赖标准库，PIL / rembg / onnxruntime
全部是在函数内部按需导入的。
"""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from whitebg import __version__  # noqa: E402
from whitebg.engine import (  # noqa: E402
    IMAGE_EXTS,
    build_parser,
    collect_inputs,
    validate,
)


class TestPackage(unittest.TestCase):
    def test_version_is_semver_like(self) -> None:
        parts = __version__.split(".")
        self.assertEqual(len(parts), 3)
        self.assertTrue(all(p.isdigit() for p in parts), __version__)


class TestParser(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = build_parser()

    def _expect_cli_error(self, argv: list[str]) -> None:
        """断言这组参数会被 validate 拒绝（同时吞掉 argparse 打到 stderr 的用法说明）。"""
        args = self.parser.parse_args(argv)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            validate(args, self.parser)

    def test_defaults(self) -> None:
        args = self.parser.parse_args([])
        self.assertEqual(args.model, "birefnet-general-lite")
        self.assertAlmostEqual(args.margin, 0.06)
        self.assertEqual(args.workers, 1)
        self.assertIsNone(args.square)  # None = 交给调用方决定（见 main 的默认值解析）
        self.assertFalse(args.transparent)

    def test_no_square_switch(self) -> None:
        self.assertFalse(self.parser.parse_args(["--no-square"]).square)
        self.assertTrue(self.parser.parse_args(["--square"]).square)

    def test_transparent_jpg_is_rejected(self) -> None:
        self._expect_cli_error(["--transparent", "--format", "jpg"])

    def test_shadow_with_transparent_is_rejected(self) -> None:
        self._expect_cli_error(["--transparent", "--shadow"])

    def test_negative_margin_is_rejected(self) -> None:
        self._expect_cli_error(["--margin", "-1"])

    def test_valid_combination_passes(self) -> None:
        args = self.parser.parse_args(["--transparent", "--format", "png"])
        self.assertTrue(validate(args, self.parser))


class TestCollectInputs(unittest.TestCase):
    def test_filters_by_extension(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.jpg").write_bytes(b"x")
            (root / "b.PNG").write_bytes(b"x")  # 大小写不敏感
            (root / "note.txt").write_text("x", encoding="utf-8")

            found = collect_inputs(root, recursive=False)
            self.assertEqual([p.name for p in found], ["a.jpg", "b.PNG"])

    def test_single_file_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "a.jpg"
            f.write_bytes(b"x")
            self.assertEqual(collect_inputs(f, recursive=False), [f])

    def test_non_image_file_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "a.txt"
            f.write_text("x", encoding="utf-8")
            self.assertEqual(collect_inputs(f, recursive=False), [])

    def test_recursive_switch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sub").mkdir()
            (root / "sub" / "deep.jpg").write_bytes(b"x")
            self.assertEqual(collect_inputs(root, recursive=False), [])
            self.assertEqual(len(collect_inputs(root, recursive=True)), 1)

    def test_supported_extensions(self) -> None:
        for ext in (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"):
            self.assertIn(ext, IMAGE_EXTS)


if __name__ == "__main__":
    unittest.main()
