import json
import os
import base64
import io
import sys
import tempfile
import threading
import urllib.error
import unittest
from pathlib import Path
from unittest.mock import patch

import image_translate_openrouter as translator


PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)

REQUESTED_LANGUAGE_NAMES = {
    "en": "英语",
    "es": "西班牙语",
    "ar": "阿拉伯语",
    "pt": "葡萄牙语",
    "hi": "印地语",
    "fr": "法语",
    "de": "德语",
    "ja": "日语",
    "ko": "韩语",
    "ru": "俄语",
    "it": "意大利语",
    "nl": "荷兰语",
    "pl": "波兰语",
    "sv": "瑞典语",
    "tr": "土耳其语",
    "id": "印尼语",
    "th": "泰语",
    "vi": "越南语",
    "ms": "马来语",
    "fil": "菲律宾语",
    "he": "希伯来语",
    "fa": "波斯语",
}


class FakeResponse:
    def __init__(self, body: bytes, status: int = 200):
        self._body = body
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self._body


class FakeOpener:
    def __init__(self, body: bytes):
        self.body = body
        self.requests = []

    def open(self, request, timeout=0):
        self.requests.append((request, timeout))
        return FakeResponse(self.body)


class RaisingOpener:
    def __init__(self, exc):
        self.exc = exc
        self.requests = []

    def open(self, request, timeout=0):
        self.requests.append((request, timeout))
        raise self.exc


class SequenceOpener:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, request, timeout=0):
        self.requests.append((request, timeout))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class SettingsTests(unittest.TestCase):
    def test_save_and_load_settings_round_trip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = Path(temp_dir) / "settings.json"
            settings = {
                "api_url": "https://api.example.test/v1/chat/completions",
                "api_key": "test-key",
                "model_id": "custom/image-model",
                "proxy_url": "http://127.0.0.1:7890",
                "theme_id": "scheme_3",
            }

            translator.save_settings(settings, settings_path)
            loaded = translator.load_settings(settings_path)

        self.assertEqual(loaded, translator.normalize_settings(settings))

    def test_load_settings_merges_saved_values_with_defaults(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = Path(temp_dir) / "settings.json"
            settings_path.write_text(
                json.dumps({"api_url": "https://api.example.test/chat/completions"}),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "env-key"}, clear=True):
                loaded = translator.load_settings(settings_path)

        self.assertEqual(loaded["api_url"], "https://api.example.test/chat/completions")
        self.assertEqual(loaded["api_key"], "env-key")
        self.assertEqual(loaded["model_id"], translator.DEFAULT_MODEL_ID)
        self.assertEqual(loaded["proxy_url"], "")
        self.assertEqual(loaded["theme_id"], translator.DEFAULT_THEME_ID)

    def test_save_and_load_settings_keeps_ui_preferences(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = Path(temp_dir) / "settings.json"
            settings = {
                "api_url": "https://api.example.test/v1/chat/completions",
                "api_key": "test-key",
                "model_id": "custom/image-model",
                "proxy_url": "http://127.0.0.1:7890",
                "theme_id": "scheme_3",
                "source_dir": "D:/input",
                "output_dir": "D:/output",
                "output_format": "webp",
                "selected_languages": ["ja", "ko"],
                "overwrite_policy": "rename",
                "max_concurrent": 2,
            }

            translator.save_settings(settings, settings_path)
            loaded = translator.load_settings(settings_path)

        self.assertEqual(loaded["source_dir"], "D:/input")
        self.assertEqual(loaded["output_dir"], "D:/output")
        self.assertEqual(loaded["output_format"], "webp")
        self.assertEqual(loaded["selected_languages"], ["ja", "ko"])
        self.assertEqual(loaded["overwrite_policy"], "rename")
        self.assertEqual(loaded["max_concurrent"], 2)

    def test_validate_settings_reports_missing_or_invalid_fields(self):
        errors = translator.validate_settings(
            {
                "api_url": "ftp://api.example.test/chat/completions",
                "api_key": "",
                "model_id": "",
                "proxy_url": "",
            }
        )

        self.assertIn("API 地址必须以 http:// 或 https:// 开头。", errors)
        self.assertIn("API 密钥不能为空。", errors)
        self.assertIn("模型 ID 不能为空。", errors)

    def test_validate_settings_accepts_complete_configuration(self):
        errors = translator.validate_settings(
            {
                "api_url": "https://api.example.test/v1/chat/completions",
                "api_key": "test-key",
                "model_id": "custom/image-model",
                "proxy_url": "",
            }
        )

        self.assertEqual(errors, [])

    def test_translate_image_uses_configured_api_url_key_and_model(self):
        response = {
            "choices": [
                {
                    "message": {
                        "images": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": "data:image/png;base64,"
                                    + base64.b64encode(PNG_BYTES).decode("ascii")
                                },
                            }
                        ]
                    }
                }
            ]
        }
        fake_opener = FakeOpener(json.dumps(response).encode("utf-8"))

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "input.png"
            output_path = temp_path / "output.png"
            input_path.write_bytes(b"fake image bytes")

            settings = {
                "api_url": "https://api.example.test/v9/chat/completions",
                "api_key": "configured-key",
                "model_id": "configured-model",
                "proxy_url": "",
            }

            with patch.object(
                translator, "build_openers", return_value=[(fake_opener, "fake")]
            ):
                with patch.object(translator.time, "sleep"):
                    result = translator.translate_image(
                        input_path,
                        output_path,
                        {"prompt": "translate this", "folder": "English"},
                        settings,
                    )

            self.assertTrue(result["success"])
            self.assertTrue(output_path.exists())

        self.assertEqual(fake_opener.requests[0][0].full_url, settings["api_url"])
        self.assertEqual(
            fake_opener.requests[0][0].get_header("Authorization"),
            "Bearer configured-key",
        )
        payload = json.loads(fake_opener.requests[0][0].data.decode("utf-8"))
        self.assertEqual(payload["model"], "configured-model")

    def test_translate_image_derives_chat_endpoint_from_base_api_url(self):
        response = {
            "choices": [
                {
                    "message": {
                        "images": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": "data:image/png;base64,"
                                    + base64.b64encode(PNG_BYTES).decode("ascii")
                                },
                            }
                        ]
                    }
                }
            ]
        }
        fake_opener = FakeOpener(json.dumps(response).encode("utf-8"))

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "input.png"
            output_path = temp_path / "output.png"
            input_path.write_bytes(b"fake image bytes")

            settings = {
                "api_url": "https://api.example.test/v1/",
                "api_key": "configured-key",
                "model_id": "configured-model",
                "proxy_url": "",
                "output_format": "png",
            }

            with patch.object(
                translator, "build_openers", return_value=[(fake_opener, "fake")]
            ):
                with patch.object(translator.time, "sleep"):
                    result = translator.translate_image(
                        input_path,
                        output_path,
                        {"prompt": "translate this", "folder": "English"},
                        settings,
                    )

        self.assertTrue(result["success"])
        self.assertEqual(
            fake_opener.requests[0][0].full_url,
            "https://api.example.test/v1/chat/completions",
        )

    def test_translate_image_reports_non_json_api_response_clearly(self):
        fake_opener = FakeOpener(b"<html>not json</html>")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "input.png"
            output_path = temp_path / "output.png"
            input_path.write_bytes(b"fake image bytes")

            settings = {
                "api_url": "https://api.example.test/v1/",
                "api_key": "configured-key",
                "model_id": "configured-model",
                "proxy_url": "",
                "output_format": "png",
            }

            with patch.object(
                translator, "build_openers", return_value=[(fake_opener, "fake")]
            ):
                result = translator.translate_image(
                    input_path,
                    output_path,
                    {"prompt": "translate this", "folder": "English"},
                    settings,
                )

        self.assertFalse(result["success"])
        self.assertIn("接口返回不是 JSON", result["error"])
        self.assertIn("https://api.example.test/v1/chat/completions", result["error"])

    def test_translate_image_reports_actionable_401_error(self):
        http_error = urllib.error.HTTPError(
            "https://api.example.test/v1/chat/completions",
            401,
            "Unauthorized",
            {},
            io.BytesIO(b'{"error":"invalid api key"}'),
        )
        fake_opener = RaisingOpener(http_error)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "input.png"
            output_path = temp_path / "output.png"
            input_path.write_bytes(PNG_BYTES)

            settings = {
                "api_url": "https://api.example.test/v1/",
                "api_key": "bad-key",
                "model_id": "configured-model",
                "proxy_url": "",
                "output_format": "png",
            }

            with patch.object(
                translator, "build_openers", return_value=[(fake_opener, "direct")]
            ):
                with patch.object(translator.time, "sleep"):
                    result = translator.translate_image(
                        input_path,
                        output_path,
                        {"prompt": "translate this", "folder": "English"},
                        settings,
                    )

        self.assertFalse(result["success"])
        self.assertIn("HTTP 401", result["error"])
        self.assertIn("API Key", result["error"])

    def test_translate_image_reports_actionable_429_error(self):
        http_error = urllib.error.HTTPError(
            "https://api.example.test/v1/chat/completions",
            429,
            "Too Many Requests",
            {},
            io.BytesIO(b'{"error":"rate limit"}'),
        )
        fake_opener = RaisingOpener(http_error)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "input.png"
            output_path = temp_path / "output.png"
            input_path.write_bytes(PNG_BYTES)

            settings = {
                "api_url": "https://api.example.test/v1/",
                "api_key": "configured-key",
                "model_id": "configured-model",
                "proxy_url": "",
                "output_format": "png",
            }

            with patch.object(
                translator, "build_openers", return_value=[(fake_opener, "direct")]
            ):
                with patch.object(translator.time, "sleep"):
                    result = translator.translate_image(
                        input_path,
                        output_path,
                        {"prompt": "translate this", "folder": "English"},
                        settings,
                    )

        self.assertFalse(result["success"])
        self.assertIn("HTTP 429", result["error"])
        self.assertIn("降低并发", result["error"])

    def test_translate_image_retries_transient_http_error_and_succeeds(self):
        response = {
            "choices": [
                {
                    "message": {
                        "images": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": "data:image/png;base64,"
                                    + base64.b64encode(PNG_BYTES).decode("ascii")
                                },
                            }
                        ]
                    }
                }
            ]
        }
        http_error = urllib.error.HTTPError(
            "https://api.example.test/v1/chat/completions",
            503,
            "Service Unavailable",
            {},
            io.BytesIO(b'{"error":"busy"}'),
        )
        fake_opener = SequenceOpener(
            [
                http_error,
                FakeResponse(json.dumps(response).encode("utf-8")),
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "input.png"
            output_path = temp_path / "output.png"
            input_path.write_bytes(PNG_BYTES)

            settings = {
                "api_url": "https://api.example.test/v1/",
                "api_key": "configured-key",
                "model_id": "configured-model",
                "proxy_url": "",
                "output_format": "png",
            }

            with patch.object(
                translator, "build_openers", return_value=[(fake_opener, "direct")]
            ):
                with patch.object(translator.time, "sleep") as sleep:
                    result = translator.translate_image(
                        input_path,
                        output_path,
                        {"prompt": "translate this", "folder": "English"},
                        settings,
                    )

        self.assertTrue(result["success"])
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(len(fake_opener.requests), 2)
        sleep.assert_called_once()

    def test_translate_image_uses_rate_limit_backoff_for_429_retry(self):
        response = {
            "choices": [
                {
                    "message": {
                        "images": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": "data:image/png;base64,"
                                    + base64.b64encode(PNG_BYTES).decode("ascii")
                                },
                            }
                        ]
                    }
                }
            ]
        }
        http_error = urllib.error.HTTPError(
            "https://api.example.test/v1/chat/completions",
            429,
            "Too Many Requests",
            {},
            io.BytesIO(b'{"error":"rate limit"}'),
        )
        fake_opener = SequenceOpener(
            [
                http_error,
                FakeResponse(json.dumps(response).encode("utf-8")),
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "input.png"
            output_path = temp_path / "output.png"
            input_path.write_bytes(PNG_BYTES)

            settings = {
                "api_url": "https://api.example.test/v1/",
                "api_key": "configured-key",
                "model_id": "configured-model",
                "proxy_url": "",
                "output_format": "png",
            }

            with patch.object(
                translator, "build_openers", return_value=[(fake_opener, "direct")]
            ):
                with patch.object(translator.time, "sleep") as sleep:
                    result = translator.translate_image(
                        input_path,
                        output_path,
                        {"prompt": "translate this", "folder": "English"},
                        settings,
                    )

        self.assertTrue(result["success"])
        self.assertGreaterEqual(sleep.call_args_list[0].args[0], 3)

    def test_translate_image_converts_response_to_configured_output_format(self):
        response = {
            "choices": [
                {
                    "message": {
                        "images": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": "data:image/png;base64,"
                                    + base64.b64encode(PNG_BYTES).decode("ascii")
                                },
                            }
                        ]
                    }
                }
            ]
        }
        fake_opener = FakeOpener(json.dumps(response).encode("utf-8"))

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "input.png"
            output_path = temp_path / "output.jpg"
            input_path.write_bytes(b"fake image bytes")

            settings = {
                "api_url": "https://api.example.test/v9/chat/completions",
                "api_key": "configured-key",
                "model_id": "configured-model",
                "proxy_url": "",
                "output_format": "jpg",
            }

            with patch.object(
                translator, "build_openers", return_value=[(fake_opener, "fake")]
            ):
                result = translator.translate_image(
                    input_path,
                    output_path,
                    {"prompt": "translate this", "folder": "English"},
                    settings,
                )

            self.assertTrue(result["success"])
            self.assertEqual(output_path.read_bytes()[:3], b"\xff\xd8\xff")

    def test_derive_models_url_from_chat_completions_endpoint(self):
        models_url = translator.derive_models_url(
            "https://api.example.test/v1/chat/completions"
        )

        self.assertEqual(models_url, "https://api.example.test/v1/models")

    def test_fetch_available_models_uses_api_url_key_and_proxy_openers(self):
        response = {
            "data": [
                {"id": "gpt-5.4", "name": "GPT-5.4", "context_length": 128000},
                {"id": "gemini-3.1-flash-image-preview"},
            ]
        }
        fake_opener = FakeOpener(json.dumps(response).encode("utf-8"))
        settings = {
            "api_url": "https://api.example.test/v1/chat/completions",
            "api_key": "configured-key",
            "model_id": "existing-model",
            "proxy_url": "http://127.0.0.1:10808",
        }

        with patch.object(
            translator, "build_openers", return_value=[(fake_opener, "fake")]
        ) as build_openers:
            models = translator.fetch_available_models(settings)

        build_openers.assert_called_once_with(settings["proxy_url"])
        self.assertEqual(fake_opener.requests[0][0].full_url, "https://api.example.test/v1/models")
        self.assertEqual(
            fake_opener.requests[0][0].get_header("Authorization"),
            "Bearer configured-key",
        )
        self.assertEqual(
            models,
            [
                {"id": "gpt-5.4", "name": "GPT-5.4", "context_length": "128K"},
                {
                    "id": "gemini-3.1-flash-image-preview",
                    "name": "gemini-3.1-flash-image-preview",
                    "context_length": "",
                },
            ],
        )


class LanguageCatalogTests(unittest.TestCase):
    def test_language_catalog_includes_requested_languages(self):
        for code, name in REQUESTED_LANGUAGE_NAMES.items():
            with self.subTest(code=code):
                self.assertIn(code, translator.LANGUAGE_SPECS)
                self.assertEqual(translator.LANGUAGE_SPECS[code]["name"], name)
                self.assertEqual(translator.LANGUAGE_SPECS[code]["folder"], name)
                self.assertIn(
                    translator.OUTPUT_SIZE,
                    translator.LANGUAGE_SPECS[code]["prompt"],
                )

        self.assertEqual(
            len(translator.ALL_LANGUAGE_CODES),
            len(set(translator.ALL_LANGUAGE_CODES)),
        )

    def test_custom_language_ui_uses_translator_catalog(self):
        import generate_custom_bat

        expected = [
            (code, spec["name"])
            for code, spec in translator.LANGUAGE_SPECS.items()
        ]

        self.assertEqual(generate_custom_bat.LANGUAGES, expected)


class WindowLayoutTests(unittest.TestCase):
    def test_dark_orange_theme_is_applied_to_root_and_log(self):
        import generate_custom_bat

        scheme_2 = generate_custom_bat.THEME_PRESETS["scheme_2"]["colors"]
        self.assertEqual(scheme_2["background"], "#120706")
        self.assertEqual(scheme_2["panel"], "#24100d")
        self.assertEqual(scheme_2["primary"], "#f05a1a")

        app = generate_custom_bat.App()
        app.root.withdraw()
        try:
            theme = generate_custom_bat.THEME_PRESETS[app.theme_id.get()]["colors"]
            self.assertEqual(
                app.root.cget("background"),
                theme["background"],
            )
            self.assertEqual(
                app.log.cget("background"),
                theme["log_background"],
            )
            self.assertEqual(
                app.log.cget("foreground"),
                theme["text"],
            )
        finally:
            app.root.destroy()

    def test_log_selection_uses_contrasting_theme_text(self):
        import generate_custom_bat

        class FakeText:
            def __init__(self):
                self.options = {}

            def configure(self, **kwargs):
                self.options.update(kwargs)

        for theme_id, theme_spec in generate_custom_bat.THEME_PRESETS.items():
            with self.subTest(theme_id=theme_id):
                widget = FakeText()
                theme = generate_custom_bat.set_app_theme(theme_id)
                generate_custom_bat.configure_log_widget(widget)

                self.assertEqual(widget.options["selectbackground"], theme["primary"])
                self.assertEqual(widget.options["selectforeground"], theme["primary_text"])
                self.assertNotEqual(
                    widget.options["selectforeground"],
                    widget.options["selectbackground"],
                )
                self.assertEqual(theme["primary_text"], theme_spec["colors"]["primary_text"])

    def test_theme_switcher_has_five_presets_and_applies_selected_theme(self):
        import generate_custom_bat

        with patch.object(
            generate_custom_bat.translator,
            "load_settings",
            return_value=generate_custom_bat.translator.default_settings(),
        ):
            app = generate_custom_bat.App()
        app.root.withdraw()
        try:
            self.assertEqual(
                list(generate_custom_bat.THEME_PRESETS),
                ["scheme_1", "scheme_2", "scheme_3", "scheme_4", "scheme_5"],
            )
            self.assertEqual(
                generate_custom_bat.THEME_PRESETS["scheme_4"]["colors"]["background"],
                "#050505",
            )
            self.assertEqual(
                generate_custom_bat.THEME_PRESETS["scheme_5"]["colors"]["background"],
                "#ffffff",
            )
            for theme_spec in generate_custom_bat.THEME_PRESETS.values():
                self.assertIn("primary_text", theme_spec["colors"])
            self.assertEqual(
                generate_custom_bat.theme_labels(),
                ("清爽浅色", "暗红橙战斗", "墨绿金属", "纯黑高对比", "纯白简洁"),
            )
            self.assertTrue(
                all("方案" not in label for label in generate_custom_bat.theme_labels())
            )
            self.assertEqual(app.theme_id.get(), generate_custom_bat.DEFAULT_THEME_ID)

            app.theme_label.set(generate_custom_bat.THEME_PRESETS["scheme_5"]["label"])
            app.on_theme_selected()

            theme = generate_custom_bat.THEME_PRESETS["scheme_5"]["colors"]
            self.assertEqual(app.theme_id.get(), "scheme_5")
            self.assertEqual(app.root.cget("background"), theme["background"])
            self.assertEqual(app.log.cget("background"), theme["log_background"])
            self.assertEqual(app.log.cget("foreground"), theme["text"])
            self.assertEqual(
                generate_custom_bat.ttk.Style(app.root).lookup("Primary.TButton", "foreground"),
                theme["primary_text"],
            )
            popup_options = generate_custom_bat.combobox_popdown_options(app.theme_combo)
            self.assertEqual(popup_options["selectbackground"], theme["primary"])
            self.assertEqual(popup_options["selectforeground"], theme["primary_text"])

            app.apply_theme("scheme_2")
            theme = generate_custom_bat.THEME_PRESETS["scheme_2"]["colors"]
            popup_options = generate_custom_bat.combobox_popdown_options(app.theme_combo)
            self.assertEqual(popup_options["selectbackground"], theme["primary"])
            self.assertEqual(popup_options["selectforeground"], theme["primary_text"])
        finally:
            app.root.destroy()

    def test_default_theme_is_white_and_sections_use_rounded_frames(self):
        import generate_custom_bat

        self.assertEqual(translator.DEFAULT_THEME_ID, "scheme_5")
        self.assertEqual(generate_custom_bat.DEFAULT_THEME_ID, "scheme_5")

        with patch.object(
            generate_custom_bat.translator,
            "load_settings",
            return_value=generate_custom_bat.translator.default_settings(),
        ):
            app = generate_custom_bat.App()
        app.root.withdraw()
        try:
            theme = generate_custom_bat.THEME_PRESETS["scheme_5"]["colors"]
            self.assertEqual(app.theme_id.get(), "scheme_5")
            self.assertEqual(app.root.cget("background"), theme["background"])
            self.assertGreaterEqual(len(app.rounded_sections), 4)
            self.assertTrue(
                all(isinstance(section, generate_custom_bat.RoundedSection) for section in app.rounded_sections)
            )
            self.assertTrue(all(section.radius >= 10 for section in app.rounded_sections))
            self.assertGreaterEqual(len(app.rounded_buttons), 8)
            self.assertTrue(
                all(isinstance(button, generate_custom_bat.RoundedButton) for button in app.rounded_buttons)
            )
            self.assertTrue(all(button.radius >= 10 for button in app.rounded_buttons))
            self.assertEqual(app.log.cget("borderwidth"), 0)
            self.assertEqual(app.log.cget("highlightthickness"), 0)
        finally:
            app.root.destroy()

    def test_center_window_on_parent_positions_dialog_in_parent_middle(self):
        import generate_custom_bat

        class FakeParent:
            def update_idletasks(self):
                pass

            def winfo_rootx(self):
                return 100

            def winfo_rooty(self):
                return 200

            def winfo_width(self):
                return 1000

            def winfo_height(self):
                return 800

        class FakeWindow:
            def __init__(self):
                self.geometry_value = None

            def update_idletasks(self):
                pass

            def winfo_screenwidth(self):
                return 1920

            def winfo_screenheight(self):
                return 1080

            def geometry(self, value):
                self.geometry_value = value

        window = FakeWindow()

        generate_custom_bat.center_window_on_parent(FakeParent(), window, 620, 520)

        self.assertEqual(window.geometry_value, "620x520+290+340")

    def test_default_ui_selection_matches_marked_choices(self):
        import generate_custom_bat

        app = generate_custom_bat.App()
        app.root.withdraw()
        try:
            self.assertEqual(app.selected_codes(), ["en"])
            self.assertEqual(app.output_format.get(), "jpeg")
        finally:
            app.root.destroy()

    def test_mousewheel_events_scroll_the_page_canvas(self):
        import generate_custom_bat
        from types import SimpleNamespace

        class FakeRoot:
            def __init__(self):
                self.bindings = {}

            def bind(self, sequence, callback, add=None):
                self.bindings[sequence] = (callback, add)

        class FakeCanvas:
            def __init__(self):
                self.scrolls = []

            def yview_scroll(self, units, what):
                self.scrolls.append((units, what))

        fake_root = FakeRoot()
        fake_canvas = FakeCanvas()

        generate_custom_bat.bind_page_mousewheel(fake_root, fake_canvas)

        self.assertEqual(fake_root.bindings["<MouseWheel>"][1], "+")
        self.assertEqual(fake_root.bindings["<Button-4>"][1], "+")
        self.assertEqual(fake_root.bindings["<Button-5>"][1], "+")

        mousewheel_handler = fake_root.bindings["<MouseWheel>"][0]
        button4_handler = fake_root.bindings["<Button-4>"][0]
        button5_handler = fake_root.bindings["<Button-5>"][0]

        self.assertEqual(mousewheel_handler(SimpleNamespace(delta=-120, num=None)), "break")
        self.assertEqual(mousewheel_handler(SimpleNamespace(delta=120, num=None)), "break")
        self.assertEqual(button4_handler(SimpleNamespace(delta=0, num=4)), "break")
        self.assertEqual(button5_handler(SimpleNamespace(delta=0, num=5)), "break")
        self.assertEqual(
            fake_canvas.scrolls,
            [(1, "units"), (-1, "units"), (-1, "units"), (1, "units")],
        )

    def test_bulk_language_selection_buttons_are_removed(self):
        import generate_custom_bat
        from tkinter import ttk
        button_types = (ttk.Button, generate_custom_bat.RoundedButton)

        def collect_button_texts(widget):
            texts = []
            for child in widget.winfo_children():
                if isinstance(child, button_types):
                    texts.append(child.cget("text"))
                texts.extend(collect_button_texts(child))
            return texts

        app = generate_custom_bat.App()
        app.root.withdraw()
        try:
            button_texts = collect_button_texts(app.root)
        finally:
            app.root.destroy()

        self.assertNotIn("全选四语", button_texts)
        self.assertNotIn("全选全部语言", button_texts)
        self.assertIn("清空选择", button_texts)

    def test_model_selector_button_is_rendered(self):
        import generate_custom_bat
        from tkinter import ttk
        button_types = (ttk.Button, generate_custom_bat.RoundedButton)

        def collect_button_texts(widget):
            texts = []
            for child in widget.winfo_children():
                if isinstance(child, button_types):
                    texts.append(child.cget("text"))
                texts.extend(collect_button_texts(child))
            return texts

        app = generate_custom_bat.App()
        app.root.withdraw()
        try:
            button_texts = collect_button_texts(app.root)
        finally:
            app.root.destroy()

        self.assertIn("选择模型", button_texts)

    def test_cancel_button_and_overwrite_policy_controls_are_rendered(self):
        import generate_custom_bat
        from tkinter import ttk

        button_types = (ttk.Button, generate_custom_bat.RoundedButton)

        def collect_widgets(widget, widget_type):
            items = []
            for child in widget.winfo_children():
                if isinstance(child, widget_type):
                    items.append(child)
                items.extend(collect_widgets(child, widget_type))
            return items

        app = generate_custom_bat.App()
        app.root.withdraw()
        try:
            button_texts = [button.cget("text") for button in collect_widgets(app.root, button_types)]
            combo_values = [
                tuple(combo.cget("values"))
                for combo in collect_widgets(app.root, ttk.Combobox)
            ]
        finally:
            app.root.destroy()

        self.assertIn("取消任务", button_texts)
        self.assertIn("打开输出文件夹", button_texts)
        self.assertIn("保存日志", button_texts)
        self.assertIn(
            ("覆盖已有文件", "跳过已有文件", "自动重命名"),
            combo_values,
        )

    def test_version_is_visible_in_window_title(self):
        import generate_custom_bat

        self.assertEqual(generate_custom_bat.APP_VERSION, "v1.0.4")
        self.assertIn(generate_custom_bat.APP_VERSION, generate_custom_bat.WINDOW_TITLE)

    def test_app_loads_saved_directory_and_output_preferences(self):
        import generate_custom_bat

        saved = generate_custom_bat.translator.default_settings()
        saved.update(
            {
                "source_dir": "D:/input-images",
                "output_dir": "D:/translated-images",
                "output_format": "webp",
                "selected_languages": ["ja", "ko"],
                "overwrite_policy": "skip",
                "max_concurrent": 2,
            }
        )

        with patch.object(generate_custom_bat.translator, "load_settings", return_value=saved):
            app = generate_custom_bat.App()
        app.root.withdraw()
        try:
            self.assertEqual(app.source_dir.get(), "D:/input-images")
            self.assertEqual(app.output_dir.get(), "D:/translated-images")
            self.assertEqual(app.output_format.get(), "webp")
            self.assertEqual(app.overwrite_policy.get(), "skip")
            self.assertEqual(app.max_concurrent.get(), "2")
            self.assertEqual(app.selected_codes(), ["ja", "ko"])
        finally:
            app.root.destroy()

    def test_open_output_folder_creates_and_opens_saved_output_dir(self):
        import generate_custom_bat

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "new-output"
            app = generate_custom_bat.App()
            app.root.withdraw()
            try:
                app.output_dir.set(str(output_dir))
                with patch.object(generate_custom_bat.os, "startfile") as startfile:
                    app.open_output_folder()
                self.assertTrue(output_dir.exists())
                startfile.assert_called_once_with(str(output_dir))
            finally:
                app.root.destroy()

    def test_save_log_exports_redacted_log_text(self):
        import generate_custom_bat

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "translation-log.txt"
            app = generate_custom_bat.App()
            app.root.withdraw()
            try:
                app.api_key.set("secret-key")
                app.append_log("失败: secret-key should not be exported")
                with patch.object(
                    generate_custom_bat.filedialog,
                    "asksaveasfilename",
                    return_value=str(output_path),
                ):
                    app.save_log()
                saved_text = output_path.read_text(encoding="utf-8")
            finally:
                app.root.destroy()

        self.assertIn("***", saved_text)
        self.assertNotIn("secret-key", saved_text)

    def test_progress_status_updates_from_counts(self):
        import generate_custom_bat

        app = generate_custom_bat.App()
        app.root.withdraw()
        try:
            self.assertEqual(app.progress_value.get(), 0)
            self.assertIn("0/0", app.progress_text.get())

            app.update_progress(1, 4)

            self.assertEqual(app.progress_value.get(), 1)
            self.assertEqual(app.progress_bar.cget("maximum"), 4)
            self.assertIn("1/4", app.progress_text.get())
        finally:
            app.root.destroy()

    def test_root_window_is_resizable_with_minimum_size(self):
        import generate_custom_bat

        class FakeRoot:
            def __init__(self):
                self.title_value = None
                self.geometry_value = None
                self.minsize_value = None
                self.resizable_value = None

            def title(self, value):
                self.title_value = value

            def geometry(self, value):
                self.geometry_value = value

            def minsize(self, width, height):
                self.minsize_value = (width, height)

            def resizable(self, width_enabled, height_enabled):
                self.resizable_value = (width_enabled, height_enabled)

        fake_root = FakeRoot()

        generate_custom_bat.configure_root_window(fake_root)

        self.assertEqual(fake_root.title_value, generate_custom_bat.WINDOW_TITLE)
        self.assertEqual(fake_root.geometry_value, generate_custom_bat.WINDOW_GEOMETRY)
        self.assertEqual(fake_root.minsize_value, generate_custom_bat.WINDOW_MIN_SIZE)
        self.assertEqual(fake_root.resizable_value, (True, True))


class DirectorySelectionTests(unittest.TestCase):
    def test_run_translation_uses_custom_source_and_output_dirs(self):
        logs = []

        def fake_translate(image_path, output_path, lang_config, settings):
            output_path.write_bytes(PNG_BYTES)
            return {
                "success": True,
                "input": image_path.name,
                "output": output_path.name,
                "time_ms": 0,
                "error": None,
                "language": lang_config["folder"],
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_dir = temp_path / "input images"
            output_dir = temp_path / "translated output"
            source_dir.mkdir()
            (source_dir / "poster.png").write_bytes(PNG_BYTES)

            settings = {
                "api_url": "https://api.example.test/v1/chat/completions",
                "api_key": "test-key",
                "model_id": "test-model",
                "proxy_url": "",
                "output_format": "png",
            }

            with patch.object(translator, "translate_image", side_effect=fake_translate):
                with patch.object(translator, "can_connect_to_proxy", return_value=False):
                    exit_code = translator.run_translation(
                        ("en",),
                        logger=logs.append,
                        settings=settings,
                        source_dir=source_dir,
                        output_dir=output_dir,
                    )

            self.assertEqual(exit_code, 0)
            self.assertEqual((output_dir / "英语" / "poster.png").read_bytes(), PNG_BYTES)
            self.assertIn(f"读取目录: {source_dir}", logs)
            self.assertIn(f"输出目录: {output_dir}", logs)

    def test_main_passes_custom_source_and_output_dirs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir) / "source"
            output_dir = Path(temp_dir) / "output"

            captured = {}

            def fake_run_translation(codes, output_subdir="", logger=print, settings=None, **kwargs):
                captured["codes"] = codes
                captured["output_subdir"] = output_subdir
                captured["source_dir"] = kwargs.get("source_dir")
                captured["output_dir"] = kwargs.get("output_dir")
                captured["settings"] = settings
                return 0

            argv = [
                "image_translate_openrouter.py",
                "--languages",
                "en",
                "--source-dir",
                str(source_dir),
                "--output-dir",
                str(output_dir),
                "--output-format",
                "webp",
            ]

            with patch.object(sys, "argv", argv):
                with patch.object(translator, "run_translation", side_effect=fake_run_translation):
                    exit_code = translator.main()

            self.assertEqual(exit_code, 0)
            self.assertEqual(captured["codes"], ("en",))
            self.assertEqual(captured["output_subdir"], "")
            self.assertEqual(captured["source_dir"], source_dir)
            self.assertEqual(captured["output_dir"], output_dir)
            self.assertEqual(captured["settings"]["output_format"], "webp")

    def test_run_translation_uses_selected_output_extension(self):
        seen_output_paths = []
        logs = []

        def fake_translate(image_path, output_path, lang_config, settings):
            seen_output_paths.append(output_path)
            output_path.write_bytes(PNG_BYTES)
            return {
                "success": True,
                "input": image_path.name,
                "output": output_path.name,
                "time_ms": 0,
                "error": None,
                "language": lang_config["folder"],
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_dir = temp_path / "source"
            output_dir = temp_path / "output"
            source_dir.mkdir()
            (source_dir / "poster.png").write_bytes(PNG_BYTES)

            settings = {
                "api_url": "https://api.example.test/v1/chat/completions",
                "api_key": "test-key",
                "model_id": "test-model",
                "proxy_url": "",
                "output_format": "jpeg",
            }

            with patch.object(translator, "translate_image", side_effect=fake_translate):
                with patch.object(translator, "can_connect_to_proxy", return_value=False):
                    exit_code = translator.run_translation(
                        ("en",),
                        logger=logs.append,
                        settings=settings,
                        source_dir=source_dir,
                        output_dir=output_dir,
                    )

        self.assertEqual(exit_code, 0)
        self.assertEqual([path.name for path in seen_output_paths], ["poster.jpeg"])

    def test_run_translation_uses_configured_max_concurrent(self):
        logs = []

        def fake_translate(image_path, output_path, lang_config, settings):
            output_path.write_bytes(PNG_BYTES)
            return {
                "success": True,
                "input": image_path.name,
                "output": output_path.name,
                "time_ms": 0,
                "error": None,
                "language": lang_config["folder"],
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_dir = temp_path / "source"
            output_dir = temp_path / "output"
            source_dir.mkdir()
            (source_dir / "poster.png").write_bytes(PNG_BYTES)

            settings = {
                "api_url": "https://api.example.test/v1/chat/completions",
                "api_key": "test-key",
                "model_id": "test-model",
                "proxy_url": "",
                "output_format": "png",
                "max_concurrent": 2,
            }

            with patch.object(translator, "translate_image", side_effect=fake_translate):
                with patch.object(translator, "can_connect_to_proxy", return_value=False):
                    exit_code = translator.run_translation(
                        ("en",),
                        logger=logs.append,
                        settings=settings,
                        source_dir=source_dir,
                        output_dir=output_dir,
                    )

        self.assertEqual(exit_code, 0)
        self.assertIn("并发数: 2", logs)

    def test_run_translation_reports_progress_counts(self):
        progress_events = []

        def fake_translate(image_path, output_path, lang_config, settings):
            output_path.write_bytes(PNG_BYTES)
            return {
                "success": True,
                "input": image_path.name,
                "output": output_path.name,
                "time_ms": 0,
                "error": None,
                "language": lang_config["folder"],
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_dir = temp_path / "source"
            output_dir = temp_path / "output"
            source_dir.mkdir()
            (source_dir / "poster-a.png").write_bytes(PNG_BYTES)
            (source_dir / "poster-b.png").write_bytes(PNG_BYTES)

            settings = {
                "api_url": "https://api.example.test/v1/chat/completions",
                "api_key": "test-key",
                "model_id": "test-model",
                "proxy_url": "",
                "output_format": "png",
                "max_concurrent": 1,
            }

            with patch.object(translator, "translate_image", side_effect=fake_translate):
                with patch.object(translator, "can_connect_to_proxy", return_value=False):
                    exit_code = translator.run_translation(
                        ("en",),
                        logger=lambda _message: None,
                        settings=settings,
                        source_dir=source_dir,
                        output_dir=output_dir,
                        progress_callback=lambda completed, total, result=None: progress_events.append(
                            (completed, total, result["input"] if result else None)
                        ),
                    )

        self.assertEqual(exit_code, 0)
        self.assertEqual(progress_events[0], (0, 2, None))
        self.assertEqual(progress_events[-1], (2, 2, "poster-b.png"))

    def test_run_translation_skips_existing_outputs_when_policy_is_skip(self):
        seen_output_paths = []
        logs = []

        def fake_translate(image_path, output_path, lang_config, settings):
            seen_output_paths.append(output_path)
            output_path.write_bytes(PNG_BYTES)
            return {
                "success": True,
                "input": image_path.name,
                "output": output_path.name,
                "time_ms": 0,
                "error": None,
                "language": lang_config["folder"],
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_dir = temp_path / "source"
            output_dir = temp_path / "output"
            source_dir.mkdir()
            (source_dir / "poster.png").write_bytes(PNG_BYTES)
            language_dir = output_dir / translator.LANGUAGE_SPECS["en"]["folder"]
            language_dir.mkdir(parents=True)
            existing_output = language_dir / "poster.png"
            existing_output.write_bytes(b"existing")

            settings = {
                "api_url": "https://api.example.test/v1/chat/completions",
                "api_key": "test-key",
                "model_id": "test-model",
                "proxy_url": "",
                "output_format": "png",
                "overwrite_policy": "skip",
            }

            with patch.object(translator, "translate_image", side_effect=fake_translate):
                with patch.object(translator, "can_connect_to_proxy", return_value=False):
                    exit_code = translator.run_translation(
                        ("en",),
                        logger=logs.append,
                        settings=settings,
                        source_dir=source_dir,
                        output_dir=output_dir,
                    )
            existing_bytes = existing_output.read_bytes()

        self.assertEqual(exit_code, 0)
        self.assertEqual(seen_output_paths, [])
        self.assertEqual(existing_bytes, b"existing")
        self.assertTrue(any("跳过" in line for line in logs))

    def test_run_translation_auto_renames_existing_outputs_when_policy_is_rename(self):
        seen_output_paths = []

        def fake_translate(image_path, output_path, lang_config, settings):
            seen_output_paths.append(output_path)
            output_path.write_bytes(PNG_BYTES)
            return {
                "success": True,
                "input": image_path.name,
                "output": output_path.name,
                "time_ms": 0,
                "error": None,
                "language": lang_config["folder"],
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_dir = temp_path / "source"
            output_dir = temp_path / "output"
            source_dir.mkdir()
            (source_dir / "poster.png").write_bytes(PNG_BYTES)
            language_dir = output_dir / translator.LANGUAGE_SPECS["en"]["folder"]
            language_dir.mkdir(parents=True)
            (language_dir / "poster.jpeg").write_bytes(b"existing")
            (language_dir / "poster-1.jpeg").write_bytes(b"existing")

            settings = {
                "api_url": "https://api.example.test/v1/chat/completions",
                "api_key": "test-key",
                "model_id": "test-model",
                "proxy_url": "",
                "output_format": "jpeg",
                "overwrite_policy": "rename",
            }

            with patch.object(translator, "translate_image", side_effect=fake_translate):
                with patch.object(translator, "can_connect_to_proxy", return_value=False):
                    exit_code = translator.run_translation(
                        ("en",),
                        logger=lambda _message: None,
                        settings=settings,
                        source_dir=source_dir,
                        output_dir=output_dir,
                    )

        self.assertEqual(exit_code, 0)
        self.assertEqual([path.name for path in seen_output_paths], ["poster-2.jpeg"])

    def test_run_translation_logs_failed_item_summary(self):
        logs = []

        def fake_translate(image_path, output_path, lang_config, settings):
            return {
                "success": False,
                "input": image_path.name,
                "output": None,
                "time_ms": 0,
                "error": "HTTP 429 via direct: rate limit",
                "language": lang_config["folder"],
                "attempts": 3,
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_dir = temp_path / "source"
            output_dir = temp_path / "output"
            source_dir.mkdir()
            (source_dir / "poster.png").write_bytes(PNG_BYTES)

            settings = {
                "api_url": "https://api.example.test/v1/chat/completions",
                "api_key": "test-key",
                "model_id": "test-model",
                "proxy_url": "",
                "output_format": "png",
            }

            with patch.object(translator, "translate_image", side_effect=fake_translate):
                with patch.object(translator, "can_connect_to_proxy", return_value=False):
                    exit_code = translator.run_translation(
                        ("en",),
                        logger=logs.append,
                        settings=settings,
                        source_dir=source_dir,
                        output_dir=output_dir,
                    )

        self.assertEqual(exit_code, 1)
        joined_logs = "\n".join(logs)
        self.assertIn("失败明细", joined_logs)
        self.assertIn("poster.png", joined_logs)
        self.assertIn("HTTP 429", joined_logs)
        self.assertIn("attempts=3", joined_logs)

    def test_run_translation_stops_submitting_work_after_cancel_event_is_set(self):
        cancel_event = threading.Event()
        seen_images = []

        def fake_translate(image_path, output_path, lang_config, settings):
            seen_images.append(image_path.name)
            cancel_event.set()
            output_path.write_bytes(PNG_BYTES)
            return {
                "success": True,
                "input": image_path.name,
                "output": output_path.name,
                "time_ms": 0,
                "error": None,
                "language": lang_config["folder"],
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_dir = temp_path / "source"
            output_dir = temp_path / "output"
            source_dir.mkdir()
            for index in range(3):
                (source_dir / f"poster-{index}.png").write_bytes(PNG_BYTES)

            settings = {
                "api_url": "https://api.example.test/v1/chat/completions",
                "api_key": "test-key",
                "model_id": "test-model",
                "proxy_url": "",
                "output_format": "png",
            }

            with patch.object(translator, "MAX_CONCURRENT", 1):
                with patch.object(translator, "translate_image", side_effect=fake_translate):
                    with patch.object(translator, "can_connect_to_proxy", return_value=False):
                        exit_code = translator.run_translation(
                            ("en",),
                            logger=lambda _message: None,
                            settings=settings,
                            source_dir=source_dir,
                            output_dir=output_dir,
                            cancel_event=cancel_event,
                        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(seen_images, ["poster-0.png"])


class ResponseExtractionTests(unittest.TestCase):
    def test_extract_and_save_image_accepts_provider_audio_base64_png(self):
        result = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "audio": {
                            "data": base64.b64encode(PNG_BYTES).decode("ascii"),
                            "extra_content": {"google": {"mime_type": "image/png"}},
                        },
                    }
                }
            ]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "output.png"
            error = translator.extract_and_save_image(result, None, output_path, "png")

            self.assertEqual(error, "")
            self.assertTrue(output_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))

    def test_extract_and_save_image_accepts_openrouter_image_api_b64_json(self):
        result = {
            "created": 1748372400,
            "data": [{"b64_json": base64.b64encode(PNG_BYTES).decode("ascii")}],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "output.png"
            error = translator.extract_and_save_image(result, None, output_path, "png")

            self.assertEqual(error, "")
            self.assertTrue(output_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))


if __name__ == "__main__":
    unittest.main()
