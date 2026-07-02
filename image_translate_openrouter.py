#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Batch-translate text inside images and write outputs into the 已完成 folder.
"""

import argparse
import base64
import io
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from PIL import Image


DEFAULT_API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL_ID = "google/gemini-3.1-flash-image-preview"
DEFAULT_THEME_ID = "scheme_5"
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
PROXY_URL = os.environ.get("OPENROUTER_PROXY_URL", "").strip()
MAX_CONCURRENT = 4
MAX_CONCURRENT_LIMIT = 16
TRANSLATE_MAX_ATTEMPTS = 3
RETRY_BASE_DELAY_SECONDS = 1.0
RATE_LIMIT_RETRY_DELAY_SECONDS = 3.0
DEFAULT_OUTPUT_WIDTH = 1080
DEFAULT_OUTPUT_HEIGHT = 1080
MIN_OUTPUT_DIMENSION = 64
MAX_OUTPUT_DIMENSION = 8192
OUTPUT_SIZE = f"{DEFAULT_OUTPUT_WIDTH}x{DEFAULT_OUTPUT_HEIGHT}"
DEFAULT_SELECTED_LANGUAGE_CODES = ("en",)
CANCELLED_EXIT_CODE = 2

def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BASE_DIR = get_base_dir()
SOURCE_DIR = BASE_DIR / "素材"
OUTPUT_BASE_DIR = BASE_DIR / "已完成"
SETTINGS_FILE = BASE_DIR / "settings.json"

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MODEL_ID = DEFAULT_MODEL_ID
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
DEFAULT_OUTPUT_FORMAT = "jpeg"
OUTPUT_FORMATS = {
    "png": {"label": "PNG", "extension": ".png", "pil_format": "PNG"},
    "webp": {"label": "WebP", "extension": ".webp", "pil_format": "WEBP"},
    "jpg": {"label": "JPG", "extension": ".jpg", "pil_format": "JPEG"},
    "jpeg": {"label": "JPEG", "extension": ".jpeg", "pil_format": "JPEG"},
}
DEFAULT_OVERWRITE_POLICY = "overwrite"
OVERWRITE_POLICIES = {
    "overwrite": "覆盖已有文件",
    "skip": "跳过已有文件",
    "rename": "自动重命名",
}
IMAGE_MAGIC_HEADERS = (
    b"\x89PNG\r\n\x1a\n",
    b"\xff\xd8\xff",
    b"GIF87a",
    b"GIF89a",
)
COMMON_PROXY_CANDIDATES = (
    "http://127.0.0.1:7890",
    "http://127.0.0.1:10808",
    "http://127.0.0.1:10809",
    "http://127.0.0.1:7897",
)

SETTING_KEYS = (
    "api_url",
    "api_key",
    "model_id",
    "proxy_url",
    "theme_id",
    "source_dir",
    "output_dir",
    "output_format",
    "selected_languages",
    "overwrite_policy",
    "max_concurrent",
    "output_width",
    "output_height",
)


def default_settings() -> dict:
    return {
        "api_url": DEFAULT_API_URL,
        "api_key": os.environ.get("OPENROUTER_API_KEY", "").strip(),
        "model_id": DEFAULT_MODEL_ID,
        "proxy_url": os.environ.get("OPENROUTER_PROXY_URL", "").strip(),
        "theme_id": DEFAULT_THEME_ID,
        "source_dir": str(SOURCE_DIR),
        "output_dir": str(OUTPUT_BASE_DIR / "custom_languages"),
        "output_format": DEFAULT_OUTPUT_FORMAT,
        "selected_languages": list(DEFAULT_SELECTED_LANGUAGE_CODES),
        "overwrite_policy": DEFAULT_OVERWRITE_POLICY,
        "max_concurrent": MAX_CONCURRENT,
        "output_width": DEFAULT_OUTPUT_WIDTH,
        "output_height": DEFAULT_OUTPUT_HEIGHT,
    }


def normalize_output_format(value: str = "") -> str:
    output_format = str(value or DEFAULT_OUTPUT_FORMAT).strip().lower()
    return output_format if output_format in OUTPUT_FORMATS else DEFAULT_OUTPUT_FORMAT


def normalize_overwrite_policy(value: str = "") -> str:
    policy = str(value or DEFAULT_OVERWRITE_POLICY).strip().lower()
    return policy if policy in OVERWRITE_POLICIES else DEFAULT_OVERWRITE_POLICY


def normalize_max_concurrent(value=None) -> int:
    try:
        count = int(str(value if value not in (None, "") else MAX_CONCURRENT).strip())
    except (TypeError, ValueError):
        count = MAX_CONCURRENT
    return max(1, min(count, MAX_CONCURRENT_LIMIT))


def normalize_output_dimension(value=None, default=DEFAULT_OUTPUT_WIDTH) -> int:
    try:
        dimension = int(str(value if value not in (None, "") else default).strip())
    except (TypeError, ValueError):
        dimension = default
    return max(MIN_OUTPUT_DIMENSION, min(dimension, MAX_OUTPUT_DIMENSION))


def normalize_selected_languages(value) -> list:
    if isinstance(value, str):
        raw_codes = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        raw_codes = value
    else:
        raw_codes = DEFAULT_SELECTED_LANGUAGE_CODES

    selected = []
    for raw_code in raw_codes:
        code = str(raw_code).strip().lower()
        if code in LANGUAGE_SPECS and code not in selected:
            selected.append(code)
    return selected or list(DEFAULT_SELECTED_LANGUAGE_CODES)


def output_format_label(output_format: str) -> str:
    return OUTPUT_FORMATS[normalize_output_format(output_format)]["label"]


def output_path_for_image(image_path: Path, output_dir: Path, output_format: str) -> Path:
    extension = OUTPUT_FORMATS[normalize_output_format(output_format)]["extension"]
    return output_dir / f"{image_path.stem}{extension}"


def unique_output_path(output_path: Path, reserved_paths=None) -> Path:
    reserved = {Path(path) for path in (reserved_paths or set())}
    if not output_path.exists() and output_path not in reserved:
        return output_path

    for index in range(1, 10_000):
        candidate = output_path.with_name(
            f"{output_path.stem}-{index}{output_path.suffix}"
        )
        if not candidate.exists() and candidate not in reserved:
            return candidate

    raise RuntimeError(f"无法生成不重复的输出文件名: {output_path}")


def resolve_output_path(output_path: Path, overwrite_policy: str, reserved_paths=None):
    policy = normalize_overwrite_policy(overwrite_policy)
    reserved = {Path(path) for path in (reserved_paths or set())}
    if policy == "skip" and (output_path.exists() or output_path in reserved):
        return None
    if policy == "rename":
        return unique_output_path(output_path, reserved)
    return output_path


def normalize_settings(raw_settings=None) -> dict:
    settings = default_settings()
    if isinstance(raw_settings, dict):
        for key in SETTING_KEYS:
            if key in raw_settings:
                settings[key] = raw_settings.get(key, "")

    if not settings["api_key"]:
        settings["api_key"] = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not settings["proxy_url"]:
        settings["proxy_url"] = os.environ.get("OPENROUTER_PROXY_URL", "").strip()
    settings["api_url"] = str(settings.get("api_url", "")).strip() or DEFAULT_API_URL
    settings["api_key"] = str(settings.get("api_key", "")).strip()
    settings["model_id"] = str(settings.get("model_id", "")).strip() or DEFAULT_MODEL_ID
    settings["proxy_url"] = str(settings.get("proxy_url", "")).strip()
    settings["theme_id"] = str(settings.get("theme_id", "")).strip() or DEFAULT_THEME_ID
    settings["source_dir"] = str(settings.get("source_dir", "")).strip() or str(SOURCE_DIR)
    settings["output_dir"] = str(settings.get("output_dir", "")).strip() or str(
        OUTPUT_BASE_DIR / "custom_languages"
    )
    settings["output_format"] = normalize_output_format(settings.get("output_format", ""))
    settings["selected_languages"] = normalize_selected_languages(
        settings.get("selected_languages")
    )
    settings["overwrite_policy"] = normalize_overwrite_policy(
        settings.get("overwrite_policy", "")
    )
    settings["max_concurrent"] = normalize_max_concurrent(settings.get("max_concurrent"))
    settings["output_width"] = normalize_output_dimension(
        settings.get("output_width"),
        DEFAULT_OUTPUT_WIDTH,
    )
    settings["output_height"] = normalize_output_dimension(
        settings.get("output_height"),
        DEFAULT_OUTPUT_HEIGHT,
    )
    return settings


def load_settings(settings_path=SETTINGS_FILE) -> dict:
    settings = default_settings()
    path = Path(settings_path)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        if isinstance(data, dict):
            for key in SETTING_KEYS:
                if key in data:
                    settings[key] = data.get(key, "")
    return normalize_settings(settings)


def save_settings(settings: dict, settings_path=SETTINGS_FILE) -> dict:
    cleaned = normalize_settings(settings)
    path = Path(settings_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(cleaned, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return cleaned


def validate_settings(settings: dict) -> list:
    cleaned = normalize_settings(settings)
    raw = settings if isinstance(settings, dict) else {}
    api_url = str(raw.get("api_url", cleaned["api_url"])).strip()
    api_key = str(raw.get("api_key", cleaned["api_key"])).strip()
    model_id = str(raw.get("model_id", cleaned["model_id"])).strip()
    errors = []
    parsed = urllib.parse.urlparse(api_url)

    if parsed.scheme not in ("http", "https"):
        errors.append("API 地址必须以 http:// 或 https:// 开头。")
    elif not parsed.netloc:
        errors.append("API 地址缺少主机名。")

    if not api_key:
        errors.append("API 密钥不能为空。")
    if not model_id:
        errors.append("模型 ID 不能为空。")
    return errors


def validate_model_fetch_settings(settings: dict) -> list:
    cleaned = normalize_settings(settings)
    raw = settings if isinstance(settings, dict) else {}
    api_url = str(raw.get("api_url", cleaned["api_url"])).strip()
    api_key = str(raw.get("api_key", cleaned["api_key"])).strip()
    errors = []
    parsed = urllib.parse.urlparse(api_url)

    if parsed.scheme not in ("http", "https"):
        errors.append("API 地址必须以 http:// 或 https:// 开头。")
    elif not parsed.netloc:
        errors.append("API 地址缺少主机名。")
    if not api_key:
        errors.append("API 密钥不能为空。")
    return errors


def derive_chat_completions_url(api_url: str) -> str:
    parsed = urllib.parse.urlparse(str(api_url).strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("API 地址无效，无法推导聊天补全接口。")

    path = parsed.path.rstrip("/")
    if path.endswith("/chat/completions"):
        normalized_path = path
    elif path.endswith("/models"):
        normalized_path = path[: -len("/models")] + "/chat/completions"
    else:
        normalized_path = f"{path}/chat/completions" if path else "/chat/completions"

    return urllib.parse.urlunparse(
        (parsed.scheme, parsed.netloc, normalized_path, "", "", "")
    )


def derive_models_url(api_url: str) -> str:
    parsed = urllib.parse.urlparse(str(api_url).strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("API 地址无效，无法推导模型列表接口。")

    path = parsed.path.rstrip("/")
    if path.endswith("/chat/completions"):
        path = path[: -len("/chat/completions")] + "/models"
    elif path.endswith("/completions"):
        path = path[: -len("/completions")] + "/models"
    elif not path.endswith("/models"):
        path = f"{path}/models" if path else "/models"

    return urllib.parse.urlunparse(
        (parsed.scheme, parsed.netloc, path, "", "", "")
    )


def format_token_count(value) -> str:
    if value in (None, ""):
        return ""
    try:
        count = int(value)
    except (TypeError, ValueError):
        return str(value)

    if count >= 1_000_000:
        text = f"{count / 1_000_000:.1f}".rstrip("0").rstrip(".")
        return f"{text}M"
    if count >= 1_000:
        text = f"{count / 1_000:.0f}"
        return f"{text}K"
    return str(count)


def extract_available_models(result) -> list:
    if isinstance(result, dict):
        raw_models = result.get("data")
        if raw_models is None:
            raw_models = result.get("models")
    else:
        raw_models = result

    if not isinstance(raw_models, list):
        return []

    models = []
    seen = set()
    for item in raw_models:
        if isinstance(item, str):
            model_id = item.strip()
            name = model_id
            context_length = ""
        elif isinstance(item, dict):
            model_id = str(
                item.get("id")
                or item.get("model")
                or item.get("name")
                or ""
            ).strip()
            name = str(
                item.get("name")
                or item.get("display_name")
                or model_id
            ).strip()
            context_length = format_token_count(
                item.get("context_length")
                or item.get("max_context_length")
                or item.get("input_token_limit")
                or item.get("max_tokens")
            )
        else:
            continue

        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        models.append(
            {
                "id": model_id,
                "name": name or model_id,
                "context_length": context_length,
            }
        )

    return models


def actionable_http_hint(status_code: int) -> str:
    hints = {
        400: "请求格式可能不被当前接口支持，请检查 API 地址、模型和图片格式。",
        401: "API Key 无效或未授权，请检查 API 密钥。",
        402: "账号余额或额度不足，请到服务商后台检查余额。",
        403: "当前 API Key 没有权限访问该模型，或模型不可用。",
        404: "API 地址或模型 ID 可能不正确。",
        408: "请求超时，请稍后重试或降低图片数量。",
        429: "请求过快或触发限流，请降低并发后重试。",
        500: "服务商内部错误，请稍后重试。",
        502: "服务商网关异常，请稍后重试。",
        503: "服务商暂时不可用，请稍后重试。",
        504: "服务商响应超时，请稍后重试。",
    }
    if status_code in hints:
        return hints[status_code]
    if 500 <= status_code <= 599:
        return "服务商暂时异常，请稍后重试。"
    return "请检查 API 地址、模型 ID、密钥和代理配置。"


def format_http_error(status_code: int, route_name: str, body_or_reason: str = "") -> str:
    preview = str(body_or_reason or "").strip()
    if len(preview) > 200:
        preview = preview[:200]
    hint = actionable_http_hint(status_code)
    if preview:
        return f"HTTP {status_code} via {route_name}: {hint} 原始响应: {preview}"
    return f"HTTP {status_code} via {route_name}: {hint}"


def is_retryable_http_status(status_code: int) -> bool:
    return status_code in {408, 409, 425, 429} or 500 <= status_code <= 599


def retry_delay_seconds(attempt_index: int, status_code: int = None) -> float:
    base_delay = (
        RATE_LIMIT_RETRY_DELAY_SECONDS
        if status_code == 429
        else RETRY_BASE_DELAY_SECONDS
    )
    return base_delay * max(1, attempt_index)


def http_status_from_error(error_text: str) -> int:
    if not error_text.startswith("HTTP "):
        return 0
    parts = error_text.split(maxsplit=2)
    if len(parts) < 2:
        return 0
    try:
        return int(parts[1])
    except ValueError:
        return 0


def is_retryable_translate_error(error_text: str) -> bool:
    status_code = http_status_from_error(error_text or "")
    if status_code:
        return is_retryable_http_status(status_code)
    return (
        error_text.startswith("URL Error")
        or "JSON via" in error_text
        or error_text.startswith("No image")
        or error_text.startswith("Failed to save image")
        or error_text.startswith("Model returned text instead of image")
    )


def fetch_available_models(settings: dict) -> list:
    runtime_settings = normalize_settings(settings)
    errors = validate_model_fetch_settings(runtime_settings)
    if errors:
        raise RuntimeError("\n".join(errors))

    models_url = derive_models_url(runtime_settings["api_url"])
    last_error = "Unknown error"
    for opener, route_name in build_openers(runtime_settings["proxy_url"]):
        try:
            request = urllib.request.Request(models_url, method="GET")
            request.add_header("Authorization", f"Bearer {runtime_settings['api_key']}")
            request.add_header("Accept", "application/json")
            request.add_header("User-Agent", "Mozilla/5.0 OpenClaw-Image-Translation")

            with opener.open(request, timeout=60) as response:
                body = response.read().decode("utf-8", errors="replace")
                if response.status != 200:
                    last_error = format_http_error(response.status, route_name, body)
                    continue

            models = extract_available_models(json.loads(body))
            if models:
                return models
            last_error = f"模型接口返回为空 via {route_name}"
        except urllib.error.HTTPError as exc:
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                body = ""
            last_error = format_http_error(exc.code, route_name, body or exc.reason)
        except urllib.error.URLError as exc:
            last_error = f"URL Error via {route_name}: {exc.reason}"
        except (ValueError, json.JSONDecodeError) as exc:
            last_error = f"Invalid model response via {route_name}: {exc}"
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__} via {route_name}: {exc}"

    raise RuntimeError(f"拉取模型失败：{last_error}")


def make_language_spec(name: str, target_label: str) -> dict:
    return {
        "name": name,
        "folder": name,
        "prompt": (
            f"请将这张图片中的所有文字翻译成{target_label}，保持图片的布局、样式、颜色、"
            f"字体大小等视觉效果完全不变。只翻译文字内容，不要改变任何其他元素。"
            f"请生成翻译后的图片，输出尺寸为 {OUTPUT_SIZE} 像素。"
        ),
    }


LANGUAGE_SPECS = {
    "en": make_language_spec("英语", "英语（English）"),
    "es": make_language_spec("西班牙语", "西班牙语（Español）"),
    "ar": make_language_spec("阿拉伯语", "阿拉伯语（العربية）"),
    "pt": make_language_spec("葡萄牙语", "葡萄牙语（Português）"),
    "hi": make_language_spec("印地语", "印地语（हिन्दी）"),
    "fr": make_language_spec("法语", "法语（Français）"),
    "de": make_language_spec("德语", "德语（Deutsch）"),
    "ja": make_language_spec("日语", "日语（日本語）"),
    "ko": make_language_spec("韩语", "韩语（한국어）"),
    "ru": make_language_spec("俄语", "俄语（Русский）"),
    "it": make_language_spec("意大利语", "意大利语（Italiano）"),
    "nl": make_language_spec("荷兰语", "荷兰语（Nederlands）"),
    "pl": make_language_spec("波兰语", "波兰语（Polski）"),
    "sv": make_language_spec("瑞典语", "瑞典语（Svenska）"),
    "tr": make_language_spec("土耳其语", "土耳其语（Türkçe）"),
    "id": make_language_spec("印尼语", "印尼语（Bahasa Indonesia）"),
    "th": make_language_spec("泰语", "泰语（ภาษาไทย）"),
    "vi": make_language_spec("越南语", "越南语（Tiếng Việt）"),
    "ms": make_language_spec("马来语", "马来语（Bahasa Melayu）"),
    "fil": make_language_spec("菲律宾语", "菲律宾语（Filipino/Tagalog）"),
    "he": make_language_spec("希伯来语", "希伯来语（עברית）"),
    "fa": make_language_spec("波斯语", "波斯语（فارسی）"),
    "zh_hant": make_language_spec("繁体中文", "繁体中文（台湾/香港使用的繁体字）"),
}

def output_size_label(settings: dict) -> str:
    cleaned = normalize_settings(settings)
    return f"{cleaned['output_width']}x{cleaned['output_height']}"


def prompt_with_output_size(lang_config: dict, size_label: str) -> str:
    prompt = str(lang_config.get("prompt", ""))
    if OUTPUT_SIZE in prompt:
        return prompt.replace(OUTPUT_SIZE, size_label)
    return f"{prompt}请生成翻译后的图片，输出尺寸为 {size_label} 像素。"


FOUR_LANGUAGE_CODES = ("en", "ko", "th", "vi")
ALL_LANGUAGE_CODES = tuple(LANGUAGE_SPECS.keys())


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preset", choices=("all", "four"), default="all")
    parser.add_argument("--languages", default="")
    parser.add_argument("--output-subdir", default="")
    parser.add_argument("--source-dir", default="")
    parser.add_argument("--output-dir", default="")
    parser.add_argument(
        "--output-format",
        choices=tuple(OUTPUT_FORMATS.keys()),
        default=DEFAULT_OUTPUT_FORMAT,
    )
    parser.add_argument(
        "--overwrite-policy",
        choices=tuple(OVERWRITE_POLICIES.keys()),
        default=DEFAULT_OVERWRITE_POLICY,
    )
    parser.add_argument("--max-concurrent", default="")
    parser.add_argument("--output-width", default="")
    parser.add_argument("--output-height", default="")
    parser.add_argument("--api-url", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--model-id", default="")
    parser.add_argument("--proxy-url", default="")
    return parser.parse_args()


def parse_languages_arg(raw: str):
    raw = raw.strip()
    if not raw:
        return None
    codes = []
    for part in raw.split(","):
        code = part.strip().lower()
        if not code:
            continue
        if code not in LANGUAGE_SPECS:
            raise ValueError(f"Unsupported language code: {code}")
        if code not in codes:
            codes.append(code)
    if not codes:
        return None
    return tuple(codes)


def get_active_language_codes(args):
    explicit = parse_languages_arg(args.languages)
    if explicit:
        return explicit
    if args.preset == "four":
        return FOUR_LANGUAGE_CODES
    return ALL_LANGUAGE_CODES


def get_active_languages(codes):
    return {code: LANGUAGE_SPECS[code] for code in codes}


def describe_languages(codes):
    return "、".join(LANGUAGE_SPECS[code]["name"] for code in codes)


def resolve_output_root(args) -> Path:
    output_dir = args.output_dir.strip()
    if output_dir:
        return Path(output_dir)

    subdir = args.output_subdir.strip()
    if subdir:
        return OUTPUT_BASE_DIR / subdir
    if args.languages.strip():
        return OUTPUT_BASE_DIR / "custom_languages"
    if args.preset == "four":
        return OUTPUT_BASE_DIR / "four_languages"
    return OUTPUT_BASE_DIR / "all_languages"


def encode_image_to_base64(image_path: Path) -> str:
    with open(image_path, "rb") as file_obj:
        return base64.b64encode(file_obj.read()).decode("utf-8")


def get_image_mime_type(image_path: Path) -> str:
    ext = image_path.suffix.lower()
    mime_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    return mime_types.get(ext, "image/png")


def can_connect_to_proxy(proxy_url: str) -> bool:
    cleaned = proxy_url.replace("http://", "").replace("https://", "")
    if ":" not in cleaned:
        return False
    host, port_text = cleaned.rsplit(":", 1)
    try:
        port = int(port_text)
    except ValueError:
        return False
    try:
        with socket.create_connection((host, port), timeout=0.6):
            return True
    except OSError:
        return False


def build_openers(proxy_url: str = ""):
    openers = []
    seen = set()

    def add(proxy_url: str):
        normalized = proxy_url.strip()
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        proxy_handler = urllib.request.ProxyHandler(
            {"http": normalized, "https": normalized}
        )
        openers.append((urllib.request.build_opener(proxy_handler), normalized))

    manual_proxy = proxy_url.strip() or PROXY_URL
    if manual_proxy:
        add(manual_proxy)

    for env_name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        env_value = os.environ.get(env_name, "").strip()
        if env_value:
            add(env_value)

    for proxy_url in COMMON_PROXY_CANDIDATES:
        if can_connect_to_proxy(proxy_url):
            add(proxy_url)

    openers.append((urllib.request.build_opener(), "direct"))
    return openers


def build_payload(image_path: Path, prompt: str, model_id: str = "") -> bytes:
    image_base64 = encode_image_to_base64(image_path)
    mime_type = get_image_mime_type(image_path)
    payload = {
        "model": model_id.strip() or MODEL_ID,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{image_base64}"
                        },
                    },
                ],
            }
        ],
        "max_tokens": 8192,
    }
    return json.dumps(payload).encode("utf-8")


def is_image_bytes(data: bytes) -> bool:
    if any(data.startswith(header) for header in IMAGE_MAGIC_HEADERS):
        return True
    return data.startswith(b"RIFF") and data[8:12] == b"WEBP"


def decode_base64_image(image_data: str) -> bytes:
    if not isinstance(image_data, str) or not image_data.strip():
        return b""

    cleaned = image_data.strip()
    if cleaned.startswith("data:image") and "," in cleaned:
        cleaned = cleaned.split(",", 1)[1]

    try:
        decoded = base64.b64decode(cleaned)
    except (ValueError, TypeError):
        return b""

    return decoded if is_image_bytes(decoded) else b""


def flatten_alpha_for_jpeg(image):
    if image.mode in ("RGBA", "LA"):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background

    if image.mode == "P" and "transparency" in image.info:
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background

    if image.mode != "RGB":
        return image.convert("RGB")

    return image


def convert_image_bytes(image_bytes: bytes, output_format: str) -> bytes:
    if not image_bytes or not is_image_bytes(image_bytes):
        return b""

    normalized_format = normalize_output_format(output_format)
    pil_format = OUTPUT_FORMATS[normalized_format]["pil_format"]

    with Image.open(io.BytesIO(image_bytes)) as image:
        output_buffer = io.BytesIO()
        save_kwargs = {}
        if pil_format == "JPEG":
            image = flatten_alpha_for_jpeg(image)
            save_kwargs["quality"] = 95
        elif pil_format == "WEBP":
            save_kwargs["quality"] = 95

        image.save(output_buffer, format=pil_format, **save_kwargs)
        return output_buffer.getvalue()


def save_image_bytes(image_bytes: bytes, output_path: Path, output_format: str) -> bool:
    converted = convert_image_bytes(image_bytes, output_format)
    if not converted:
        return False

    with open(output_path, "wb") as file_obj:
        file_obj.write(converted)
    return True


def save_base64_image(image_data: str, output_path: Path, output_format: str) -> bool:
    decoded = decode_base64_image(image_data)
    return save_image_bytes(decoded, output_path, output_format)


def save_image_from_url(opener, image_url: str, output_path: Path, output_format: str) -> bool:
    if image_url.startswith("data:image"):
        return save_base64_image(image_url, output_path, output_format)

    if opener is None:
        return False

    request = urllib.request.Request(image_url)
    with opener.open(request, timeout=60) as response:
        if response.status != 200:
            return False
        return save_image_bytes(response.read(), output_path, output_format)
    return True


def save_image_api_result(result: dict, opener, output_path: Path, output_format: str) -> bool:
    data_items = result.get("data", [])
    if not isinstance(data_items, list):
        return False

    for item in data_items:
        if not isinstance(item, dict):
            continue
        for key in ("b64_json", "base64", "data"):
            if save_base64_image(item.get(key, ""), output_path, output_format):
                return True
        image_url = item.get("url", "")
        if image_url and save_image_from_url(opener, image_url, output_path, output_format):
            return True

    return False


def save_image_from_audio_field(message: dict, output_path: Path, output_format: str) -> bool:
    audio = message.get("audio")
    if not isinstance(audio, dict):
        return False

    return save_base64_image(audio.get("data", ""), output_path, output_format)


def extract_and_save_image(
    result: dict,
    opener,
    output_path: Path,
    output_format: str = DEFAULT_OUTPUT_FORMAT,
) -> str:
    if save_image_api_result(result, opener, output_path, output_format):
        return ""

    choices = result.get("choices", [])
    if not choices:
        return "No choices in response"

    message = choices[0].get("message", {})
    images = message.get("images", [])
    content = message.get("content", "")

    if images:
        for image_item in images:
            if image_item.get("type") == "image_url":
                image_url = image_item.get("image_url", {}).get("url", "")
                if image_url and save_image_from_url(
                    opener,
                    image_url,
                    output_path,
                    output_format,
                ):
                    return ""
        return "No valid image in images field"

    if isinstance(content, str) and content.startswith("data:image"):
        if save_image_from_url(opener, content, output_path, output_format):
            return ""
        return "Failed to save image from content string"

    if save_image_from_audio_field(message, output_path, output_format):
        return ""

    if isinstance(content, list):
        for part in content:
            if part.get("type") == "image_url":
                image_url = part.get("image_url", {}).get("url", "")
                if image_url and save_image_from_url(
                    opener,
                    image_url,
                    output_path,
                    output_format,
                ):
                    return ""
        return "No image in response content list"

    preview = content[:200] if isinstance(content, str) else str(content)[:200]
    return f"Model returned text instead of image: {preview or 'empty'}"


def _translate_image_once(
    image_path: Path,
    output_path: Path,
    lang_config: dict,
    settings: dict = None,
) -> dict:
    start_time = time.time()
    runtime_settings = normalize_settings(settings)
    raw_settings = settings if isinstance(settings, dict) else {}
    output_format = normalize_output_format(raw_settings.get("output_format", ""))
    request_url = derive_chat_completions_url(runtime_settings["api_url"])
    openers = build_openers(runtime_settings["proxy_url"])
    prompt = prompt_with_output_size(lang_config, output_size_label(runtime_settings))
    last_error = "Unknown error"

    for opener, route_name in openers:
        try:
            data = build_payload(
                image_path,
                prompt,
                runtime_settings["model_id"],
            )
            request = urllib.request.Request(
                request_url,
                data=data,
                method="POST",
            )
            request.add_header("Authorization", f"Bearer {runtime_settings['api_key']}")
            request.add_header("Content-Type", "application/json")
            request.add_header("HTTP-Referer", "https://openclaw.ai")
            request.add_header("X-Title", "OpenClaw Image Translation")
            request.add_header("User-Agent", "Mozilla/5.0 OpenClaw-Image-Translation")

            with opener.open(request, timeout=180) as response:
                body = response.read().decode("utf-8")
                if response.status != 200:
                    last_error = format_http_error(response.status, route_name, body)
                    continue

            try:
                result = json.loads(body)
            except json.JSONDecodeError:
                preview = body[:200] if body else "empty response"
                last_error = (
                    f"接口返回不是 JSON via {route_name}: {preview} "
                    f"(请求地址: {request_url})"
                )
                continue

            error = extract_and_save_image(result, opener, output_path, output_format)
            return {
                "success": not error,
                "input": image_path.name,
                "output": output_path.name if not error else None,
                "time_ms": int((time.time() - start_time) * 1000),
                "error": error or None,
                "language": lang_config["folder"],
            }
        except urllib.error.HTTPError as exc:
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                body = ""
            last_error = format_http_error(exc.code, route_name, body or exc.reason)
        except urllib.error.URLError as exc:
            last_error = f"URL Error via {route_name}: {exc.reason}"
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__} via {route_name}: {exc}"

    return {
        "success": False,
        "input": image_path.name,
        "output": None,
        "time_ms": int((time.time() - start_time) * 1000),
        "error": last_error,
        "language": lang_config["folder"],
    }


def translate_image(
    image_path: Path,
    output_path: Path,
    lang_config: dict,
    settings: dict = None,
) -> dict:
    start_time = time.time()
    last_result = None

    for attempt_index in range(1, TRANSLATE_MAX_ATTEMPTS + 1):
        result = _translate_image_once(image_path, output_path, lang_config, settings)
        result["attempts"] = attempt_index
        result["time_ms"] = int((time.time() - start_time) * 1000)
        last_result = result

        if result["success"]:
            return result

        error_text = str(result.get("error") or "")
        if (
            attempt_index >= TRANSLATE_MAX_ATTEMPTS
            or not is_retryable_translate_error(error_text)
        ):
            return result

        time.sleep(
            retry_delay_seconds(
                attempt_index,
                http_status_from_error(error_text),
            )
        )

    return last_result


def collect_images(source_dir: Path):
    return sorted(
        [
            item
            for item in source_dir.iterdir()
            if item.is_file() and item.suffix.lower() in IMAGE_EXTENSIONS
        ],
        key=lambda item: item.name.lower(),
    )


def run_translation(
    codes,
    output_subdir="",
    logger=print,
    settings: dict = None,
    source_dir: Path = None,
    output_dir: Path = None,
    cancel_event=None,
    progress_callback=None,
) -> int:
    runtime_settings = normalize_settings(settings or load_settings())
    output_format = runtime_settings["output_format"]
    overwrite_policy = runtime_settings["overwrite_policy"]
    max_concurrent = runtime_settings["max_concurrent"]
    runtime_settings["output_format"] = output_format
    request_url = derive_chat_completions_url(runtime_settings["api_url"])
    languages = get_active_languages(codes)
    source_root = Path(source_dir) if source_dir is not None else SOURCE_DIR
    if output_dir is not None:
        output_root = Path(output_dir)
    elif output_subdir:
        output_root = OUTPUT_BASE_DIR / output_subdir
    else:
        output_root = OUTPUT_BASE_DIR / "custom_languages"

    logger("=" * 60)
    logger("图片翻译 - Nano Banana 2 (OpenRouter)")
    logger(f"读取目录: {source_root}")
    logger(f"输出目录: {output_root}")
    logger(f"输出格式: {output_format_label(output_format)}")
    logger(f"语言范围: {describe_languages(codes)}")
    logger("=" * 60)
    logger(f"输出尺寸: {output_size_label(runtime_settings)}")

    setting_errors = validate_settings(runtime_settings)
    if setting_errors:
        logger("请先完成 API 设置：")
        for error in setting_errors:
            logger(f"- {error}")
        return 1

    if source_dir is None:
        source_root.mkdir(parents=True, exist_ok=True)
    elif not source_root.exists():
        logger(f"输入目录不存在: {source_root}")
        return 1
    elif not source_root.is_dir():
        logger(f"输入路径不是文件夹: {source_root}")
        return 1

    output_root.mkdir(parents=True, exist_ok=True)

    images = collect_images(source_root)
    if not images:
        logger(f"输入目录里没有可处理的图片: {source_root}")
        logger("支持格式: png, jpg, jpeg, gif, webp")
        return 1

    output_dirs = {}
    for code, lang_config in languages.items():
        output_dir = output_root / lang_config["folder"]
        output_dir.mkdir(parents=True, exist_ok=True)
        output_dirs[code] = output_dir

    logger(f"图片数量: {len(images)}")
    logger(f"并发数: {max_concurrent}")
    logger(f"API 地址: {request_url}")
    logger(f"模型: {runtime_settings['model_id']}")
    logger(f"覆盖策略: {OVERWRITE_POLICIES[overwrite_policy]}")
    if runtime_settings["proxy_url"]:
        logger(f"手动代理: {runtime_settings['proxy_url']}")
    else:
        detected = [proxy for proxy in COMMON_PROXY_CANDIDATES if can_connect_to_proxy(proxy)]
        if detected:
            logger(f"自动检测到本地代理: {', '.join(detected)}")
        else:
            logger("代理: 未配置，将先尝试直连")
    logger("")

    for index, image_path in enumerate(images, start=1):
        size_mb = image_path.stat().st_size / (1024 * 1024)
        logger(f"{index}. {image_path.name} ({size_mb:.2f} MB)")
    logger("")

    start_time = time.time()
    logger(f"开始时间: {datetime.now().strftime('%H:%M:%S')}")
    logger("开始处理...")
    logger("")

    all_tasks = []
    results = []
    reserved_output_paths = set()
    for code, lang_config in languages.items():
        output_dir = output_dirs[code]
        for image_path in images:
            base_output_path = output_path_for_image(image_path, output_dir, output_format)
            output_path = resolve_output_path(
                base_output_path,
                overwrite_policy,
                reserved_output_paths,
            )
            if output_path is None:
                result = {
                    "success": True,
                    "skipped": True,
                    "input": image_path.name,
                    "output": base_output_path.name,
                    "time_ms": 0,
                    "error": None,
                    "language": lang_config["folder"],
                }
                results.append(result)
                logger(
                    f"跳过 [{lang_config['folder']}] {image_path.name} - 输出已存在: "
                    f"{base_output_path.name}"
                )
                continue
            reserved_output_paths.add(output_path)
            all_tasks.append(
                (
                    image_path,
                    output_path,
                    lang_config,
                )
            )

    def is_cancelled():
        return bool(cancel_event is not None and cancel_event.is_set())

    def log_result(result):
        elapsed = f"{result['time_ms'] / 1000:.2f}s"
        language = result["language"]
        attempts = int(result.get("attempts") or 1)
        if attempts > 1:
            elapsed = f"{elapsed}, attempts={attempts}"
        if result.get("skipped"):
            return
        if result["success"]:
            logger(f"成功 [{language}] {result['input']} ({elapsed})")
        else:
            logger(f"失败 [{language}] {result['input']} ({elapsed}) - {result['error'][:80]}")

    completed_count = len([item for item in results if item.get("skipped")])
    total_planned = len(all_tasks) + completed_count

    def report_progress(result=None):
        if progress_callback is None:
            return
        progress_callback(completed_count, total_planned, result)

    report_progress()

    task_index = 0
    with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        pending = set()

        def submit_next():
            nonlocal task_index
            if is_cancelled() or task_index >= len(all_tasks):
                return False
            image_path, output_path, lang_config = all_tasks[task_index]
            task_index += 1
            pending.add(
                executor.submit(
                    translate_image,
                    image_path,
                    output_path,
                    lang_config,
                    runtime_settings,
                )
            )
            return True

        for _index in range(min(max_concurrent, len(all_tasks))):
            submit_next()

        while pending:
            for future in as_completed(pending):
                pending.remove(future)
                result = future.result()
                results.append(result)
                log_result(result)
                completed_count += 1
                report_progress(result)
                if not is_cancelled():
                    submit_next()
                break

    cancelled = is_cancelled() and len(results) < total_planned
    if cancelled:
        remaining_count = total_planned - len(results)
        logger("")
        logger(f"任务已取消，未继续提交剩余 {remaining_count} 个任务。")

    total_time_ms = int((time.time() - start_time) * 1000)
    logger("")
    logger("=" * 60)
    logger("处理结果")
    logger("=" * 60)

    total_success = 0
    total_skipped = 0
    total_fail = 0
    for code, lang_config in languages.items():
        lang_folder = lang_config["folder"]
        lang_results = [item for item in results if item["language"] == lang_folder]
        skipped_count = sum(1 for item in lang_results if item.get("skipped"))
        success_count = sum(
            1 for item in lang_results if item["success"] and not item.get("skipped")
        )
        fail_count = sum(1 for item in lang_results if not item["success"])
        total_success += success_count
        total_skipped += skipped_count
        total_fail += fail_count
        line = f"{lang_config['name']}: {success_count}/{len(lang_results) - skipped_count} 成功"
        if skipped_count:
            line += f"，跳过 {skipped_count}"
        logger(line)

    logger("")
    logger(f"总成功: {total_success}/{len(results) - total_skipped}")
    if total_skipped:
        logger(f"总跳过: {total_skipped}")
    logger(f"总失败: {total_fail}/{len(results)}")
    logger(f"总耗时: {total_time_ms / 1000:.2f} 秒")
    logger(f"结束时间: {datetime.now().strftime('%H:%M:%S')}")
    failed_results = [item for item in results if not item["success"]]
    if failed_results:
        logger("")
        logger("失败明细")
        for item in failed_results:
            attempts = item.get("attempts")
            attempts_note = f" (attempts={attempts})" if attempts else ""
            logger(
                f"- [{item['language']}] {item['input']}{attempts_note}: "
                f"{item.get('error') or 'Unknown error'}"
            )

    if cancelled:
        return CANCELLED_EXIT_CODE
    return 0 if total_fail == 0 else 1


def main() -> int:
    args = parse_args()
    try:
        codes = get_active_language_codes(args)
    except ValueError as exc:
        print(str(exc))
        return 1

    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    source_dir = Path(args.source_dir.strip()) if args.source_dir.strip() else None
    output_root = resolve_output_root(args)
    settings = load_settings()
    if args.api_url.strip():
        settings["api_url"] = args.api_url.strip()
    if args.api_key.strip():
        settings["api_key"] = args.api_key.strip()
    if args.model_id.strip():
        settings["model_id"] = args.model_id.strip()
    if args.proxy_url.strip():
        settings["proxy_url"] = args.proxy_url.strip()
    settings["output_format"] = normalize_output_format(args.output_format)
    settings["overwrite_policy"] = normalize_overwrite_policy(args.overwrite_policy)
    if args.max_concurrent.strip():
        settings["max_concurrent"] = normalize_max_concurrent(args.max_concurrent)
    if args.output_width.strip():
        settings["output_width"] = normalize_output_dimension(
            args.output_width,
            DEFAULT_OUTPUT_WIDTH,
        )
    if args.output_height.strip():
        settings["output_height"] = normalize_output_dimension(
            args.output_height,
            DEFAULT_OUTPUT_HEIGHT,
        )

    return run_translation(
        codes,
        "" if args.output_dir.strip() else output_root.name,
        settings=settings,
        source_dir=source_dir,
        output_dir=output_root,
    )


if __name__ == "__main__":
    sys.exit(main())
