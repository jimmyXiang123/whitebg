# 参与贡献

欢迎提 issue 和 PR。改这个项目只需要记住几条规矩，剩下的交给工具。

## 一、环境搭建

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -e . --no-deps     # 以可编辑方式装本包，改代码不用重装
```

只跑单元测试的话不用装 `rembg`——测试只覆盖包结构和参数解析，几十毫秒结束：

```bash
python -m unittest discover -s tests -v
```

## 二、代码约定

- 4 空格缩进，行宽 100（见 `.editorconfig` / `pyproject.toml` 的 `[tool.ruff]`）
- **重依赖延迟导入**：`PIL`、`rembg`、`onnxruntime`、`numpy` 一律在函数内部导入。
  这样 `import whitebg` 是毫秒级，测试和 PyInstaller 分析都不会被拖慢
- 注释和用户可见文案用中文，变量名 / 函数名用英文
- 面向用户的日志统一走 `engine.log()`，别直接 `print`（打包成窗口程序后 stdout 是空的）

## 三、改动涉及这些地方时请一起更新

| 改了什么 | 顺手更新 |
|---|---|
| 新增命令行参数 | `engine.build_parser()` + **两份 README** 的参数表 + `tests/test_engine.py` |
| 新增模型 | `MODEL_NOTES` + **两份 README** 的模型表 + GUI 的 `MODELS` 列表 |
| 调整配色 / 间距 / 字号 | 只改 `whitebg/theme.py`，并复核 `docs/ui.md` 的对比度表 |
| 调整依赖 | `requirements.txt` 与 `pyproject.toml` 的 `dependencies` 保持一致 |
| 影响打包 | `packaging/*.spec`，并实测一次 `pyinstaller` |

> **两份 README 必须同步**：`README.md` 是英文版（GitHub 默认展示、也是 `pyproject.toml` 的 readme），
> `README.zh-CN.md` 是中文版。改功能、改参数、改截图时两边都要动，否则切换语言后会看到过期内容。
> 两份的章节顺序刻意保持一致，方便对照着改。

## 四、提交

- 一个 PR 只做一件事；提交信息用「动词 + 对象」写清楚做了什么
- 提 PR 前请在本地跑一遍：

```bash
python -m unittest discover -s tests -v
ruff check .
```

## 五、打包成 exe 之前

`pymatting` 的 `cache=True` 必须先改成 `cache=False`，否则冻结后 numba 会崩。
完整步骤见 [docs/build.md](docs/build.md)。
