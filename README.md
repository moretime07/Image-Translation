# Image Translation

本项目是一个本地桌面图片翻译工具，用于批量翻译图片中的文字，并尽量保持原图布局、颜色、字号和视觉风格不变。适合游戏素材、广告图、运营海报等多语言本地化场景。

## 功能

- 支持批量读取图片文件夹中的图片。
- 支持多语言翻译：英语、西班牙语、阿拉伯语、葡萄牙语、印地语、法语、德语、日语、韩语、俄语、意大利语、荷兰语、波兰语、瑞典语、土耳其语、印尼语、泰语、越南语、马来语、菲律宾语、希伯来语、波斯语、繁体中文。
- 支持自定义输入目录和输出目录。
- 支持输出格式：PNG、WebP、JPG、JPEG。
- 支持 API 地址、API Key、模型 ID、代理地址配置。
- 支持根据当前 API 地址自动推导模型列表接口，并在界面中搜索、选择模型 ID。
- 支持五种界面配色切换，默认纯白简洁：清爽浅色、暗红橙战斗、墨绿金属、纯黑高对比、纯白简洁。
- 支持 Tkinter 桌面界面、窗口缩放、鼠标滚轮滚动和实时日志。
- 支持 PyInstaller 打包为 Windows 可执行文件。

## 技术栈

- Python 3.11
- Tkinter / ttk
- urllib.request
- Pillow
- unittest
- PyInstaller

## 目录结构

```text
.
├── generate_custom_bat.py          # Tkinter 桌面界面入口
├── image_translate_openrouter.py   # 图片翻译核心逻辑和命令行入口
├── tests/                          # 单元测试
├── requirements.txt                # 运行依赖
├── requirements-dev.txt            # 开发和打包依赖
├── settings.example.json           # 脱敏配置模板
├── 开始翻译.spec                    # PyInstaller 打包配置
└── README.md
```

运行时会使用本地的 `settings.json`、`素材/`、`已完成/` 等文件或目录。这些内容默认不会提交到 Git。

## 安装

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

如果需要重新打包 exe：

```powershell
python -m pip install -r requirements-dev.txt
```

## 配置

复制配置模板：

```powershell
Copy-Item settings.example.json settings.json
```

然后在界面里填写并保存：

- API 地址
- API 密钥
- 模型 ID
- 代理地址
- 界面配色

API 地址可以填写完整的 `.../chat/completions`，也可以填写类似 `https://openrouter.ai/api/v1/` 的 base URL。翻译时程序会自动补全到 `.../chat/completions`。

填写 API 地址和 API 密钥后，可以点击界面里的“选择模型”按钮。程序会把 `.../chat/completions` 地址自动推导为 `.../models`，拉取可用模型列表，选择后自动回填模型 ID。

也可以直接编辑 `settings.json`。注意：`settings.json` 包含本地密钥，已经被 `.gitignore` 排除，不要上传到 Git。

## 运行

启动桌面界面：

```powershell
python generate_custom_bat.py
```

也可以使用命令行方式：

```powershell
python image_translate_openrouter.py --languages en --source-dir "E:\input" --output-dir "E:\output" --output-format jpeg
```

常用参数：

- `--languages en,ja,ko`：指定语言代码，多个语言用英文逗号分隔。
- `--source-dir`：输入图片文件夹。
- `--output-dir`：输出文件夹。
- `--output-format`：输出格式，支持 `png`、`webp`、`jpg`、`jpeg`。
- `--api-url`、`--api-key`、`--model-id`、`--proxy-url`：临时覆盖本地配置。

## 测试

```powershell
python -m unittest discover -s tests -v
python -m py_compile generate_custom_bat.py image_translate_openrouter.py
```

项目包含 GitHub Actions 配置，上传到 GitHub 后会在 push 和 pull request 时自动运行上述检查。

## 打包

```powershell
python -m PyInstaller --clean --noconfirm "开始翻译.spec"
```

打包结果会生成到 `dist/`。`dist/` 和 `.exe` 文件默认不会提交到 Git，建议通过 GitHub Release 发布可执行文件。

## Git 上传建议

首次提交前建议检查：

```powershell
git status --short
git add .gitignore README.md requirements.txt requirements-dev.txt settings.example.json generate_custom_bat.py image_translate_openrouter.py tests 开始翻译.spec
git commit -m "chore: prepare image translation project for git"
```

不要提交：

- `settings.json`
- `.env`
- `素材/`
- `已完成/`
- `build/`
- `dist/`
- `*.exe`
- `__pycache__/`

## 安全说明

本项目会在本地保存 API 配置。上传到公开 Git 仓库前必须确认没有提交真实 API Key。若曾经误提交密钥，应立即在服务商后台重置该密钥。
