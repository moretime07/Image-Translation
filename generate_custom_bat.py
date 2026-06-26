#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pick languages and run translation directly from a small UI."""

import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

import image_translate_openrouter as translator

LANGUAGES = [
    (code, spec["name"])
    for code, spec in translator.LANGUAGE_SPECS.items()
]
LANGUAGE_COLUMNS = 3
DEFAULT_CODES = {"en"}
WINDOW_TITLE = "自定义语言翻译"
WINDOW_GEOMETRY = "980x780"
WINDOW_MIN_SIZE = (760, 560)
MODEL_SELECTOR_SIZE = (620, 520)
MODEL_SELECTOR_MIN_SIZE = (480, 360)
DEFAULT_THEME_ID = translator.DEFAULT_THEME_ID
THEME_PRESETS = {
    "scheme_1": {
        "label": "清爽浅色",
        "colors": {
            "background": "#f5f0e8",
            "panel": "#fffaf2",
            "panel_alt": "#eadfce",
            "input": "#fffdf8",
            "input_focus": "#fff8ea",
            "border": "#b87a3b",
            "border_soft": "#dbc7ad",
            "primary": "#2f6f73",
            "primary_hover": "#3f898d",
            "primary_pressed": "#23585b",
            "primary_text": "#ffffff",
            "accent": "#b45309",
            "text": "#24140f",
            "muted": "#715b4d",
            "subtle": "#8b5a2b",
            "disabled": "#a99789",
            "log_background": "#fffaf2",
            "log_success": "#047857",
            "log_error": "#b91c1c",
        },
    },
    "scheme_2": {
        "label": "暗红橙战斗",
        "colors": {
            "background": "#120706",
            "panel": "#24100d",
            "panel_alt": "#35150d",
            "input": "#170908",
            "input_focus": "#27100c",
            "border": "#7c2d12",
            "border_soft": "#4f1c12",
            "primary": "#f05a1a",
            "primary_hover": "#ff7a2f",
            "primary_pressed": "#b83f13",
            "primary_text": "#1b0b08",
            "accent": "#ffc46b",
            "text": "#fff5e8",
            "muted": "#d8bba4",
            "subtle": "#f6a35a",
            "disabled": "#87614f",
            "log_background": "#0b0504",
            "log_success": "#86efac",
            "log_error": "#fca5a5",
        },
    },
    "scheme_3": {
        "label": "墨绿金属",
        "colors": {
            "background": "#071310",
            "panel": "#10201b",
            "panel_alt": "#173227",
            "input": "#08100e",
            "input_focus": "#10241e",
            "border": "#2f6f5b",
            "border_soft": "#1b3b32",
            "primary": "#11a97d",
            "primary_hover": "#2dd4a3",
            "primary_pressed": "#08745a",
            "primary_text": "#02110d",
            "accent": "#f0c66d",
            "text": "#ecfff8",
            "muted": "#a7c7bb",
            "subtle": "#7dd3b7",
            "disabled": "#657c74",
            "log_background": "#040a09",
            "log_success": "#86efac",
            "log_error": "#fca5a5",
        },
    },
    "scheme_4": {
        "label": "纯黑高对比",
        "colors": {
            "background": "#050505",
            "panel": "#111111",
            "panel_alt": "#1f1f1f",
            "input": "#080808",
            "input_focus": "#161616",
            "border": "#5f5f5f",
            "border_soft": "#2f2f2f",
            "primary": "#e5e7eb",
            "primary_hover": "#ffffff",
            "primary_pressed": "#a3a3a3",
            "primary_text": "#050505",
            "accent": "#facc15",
            "text": "#f8fafc",
            "muted": "#cbd5e1",
            "subtle": "#a3a3a3",
            "disabled": "#737373",
            "log_background": "#000000",
            "log_success": "#86efac",
            "log_error": "#fca5a5",
        },
    },
    "scheme_5": {
        "label": "纯白简洁",
        "colors": {
            "background": "#ffffff",
            "panel": "#f8fafc",
            "panel_alt": "#e5e7eb",
            "input": "#ffffff",
            "input_focus": "#f1f5f9",
            "border": "#94a3b8",
            "border_soft": "#d1d5db",
            "primary": "#111827",
            "primary_hover": "#374151",
            "primary_pressed": "#030712",
            "primary_text": "#ffffff",
            "accent": "#2563eb",
            "text": "#111827",
            "muted": "#475569",
            "subtle": "#64748b",
            "disabled": "#9ca3af",
            "log_background": "#ffffff",
            "log_success": "#047857",
            "log_error": "#b91c1c",
        },
    },
}
THEME_LABEL_TO_ID = {
    spec["label"]: theme_id
    for theme_id, spec in THEME_PRESETS.items()
}
APP_THEME = THEME_PRESETS[DEFAULT_THEME_ID]["colors"]


def normalize_theme_id(theme_id):
    return theme_id if theme_id in THEME_PRESETS else DEFAULT_THEME_ID


def theme_labels():
    return tuple(spec["label"] for spec in THEME_PRESETS.values())


def theme_label(theme_id):
    return THEME_PRESETS[normalize_theme_id(theme_id)]["label"]


def theme_id_for_label(label):
    return THEME_LABEL_TO_ID.get(label, DEFAULT_THEME_ID)


def set_app_theme(theme_id):
    global APP_THEME
    APP_THEME = THEME_PRESETS[normalize_theme_id(theme_id)]["colors"]
    return APP_THEME


def configure_root_window(root, theme_id=DEFAULT_THEME_ID):
    root.title(WINDOW_TITLE)
    root.geometry(WINDOW_GEOMETRY)
    root.minsize(*WINDOW_MIN_SIZE)
    root.resizable(True, True)
    if hasattr(root, "tk"):
        configure_app_style(root, theme_id)


def configure_app_style(root, theme_id=DEFAULT_THEME_ID):
    set_app_theme(theme_id)
    root.configure(background=APP_THEME["background"])
    root.option_add("*TCombobox*Listbox.background", APP_THEME["input"])
    root.option_add("*TCombobox*Listbox.foreground", APP_THEME["text"])
    root.option_add("*TCombobox*Listbox.selectBackground", APP_THEME["primary"])
    root.option_add("*TCombobox*Listbox.selectForeground", APP_THEME["primary_text"])
    root.option_add("*TCombobox*Listbox.selectforeground", APP_THEME["primary_text"])
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    base_font = ("Microsoft YaHei UI", 9)
    title_font = ("Microsoft YaHei UI", 11, "bold")
    button_font = ("Microsoft YaHei UI", 9, "bold")

    style.configure(
        ".",
        background=APP_THEME["background"],
        foreground=APP_THEME["text"],
        font=base_font,
    )
    style.configure("App.TFrame", background=APP_THEME["background"])
    style.configure("Dialog.TFrame", background=APP_THEME["panel"])
    style.configure("Panel.TFrame", background=APP_THEME["panel"])
    style.configure("App.TLabel", background=APP_THEME["background"], foreground=APP_THEME["text"])
    style.configure("Hint.TLabel", background=APP_THEME["background"], foreground=APP_THEME["muted"])
    style.configure("Dialog.TLabel", background=APP_THEME["panel"], foreground=APP_THEME["text"])
    style.configure(
        "Title.TLabel",
        background=APP_THEME["panel"],
        foreground=APP_THEME["text"],
        font=title_font,
    )
    style.configure(
        "Panel.TLabelframe",
        background=APP_THEME["panel"],
        bordercolor=APP_THEME["border"],
        borderwidth=1,
        relief="solid",
    )
    style.configure(
        "Panel.TLabelframe.Label",
        background=APP_THEME["background"],
        foreground=APP_THEME["accent"],
        font=button_font,
    )
    style.configure("Panel.TLabel", background=APP_THEME["panel"], foreground=APP_THEME["text"])
    style.configure(
        "App.TEntry",
        fieldbackground=APP_THEME["input"],
        foreground=APP_THEME["text"],
        insertcolor=APP_THEME["primary_hover"],
        bordercolor=APP_THEME["border_soft"],
        lightcolor=APP_THEME["border"],
        darkcolor=APP_THEME["border_soft"],
        padding=5,
    )
    style.map(
        "App.TEntry",
        fieldbackground=[("focus", APP_THEME["input_focus"])],
        bordercolor=[("focus", APP_THEME["primary"])],
    )
    style.configure(
        "App.TCombobox",
        fieldbackground=APP_THEME["input"],
        background=APP_THEME["panel_alt"],
        foreground=APP_THEME["text"],
        arrowcolor=APP_THEME["accent"],
        bordercolor=APP_THEME["border_soft"],
        lightcolor=APP_THEME["border"],
        darkcolor=APP_THEME["border_soft"],
        padding=5,
    )
    style.map(
        "App.TCombobox",
        fieldbackground=[("readonly", APP_THEME["input"]), ("focus", APP_THEME["input_focus"])],
        background=[("active", APP_THEME["panel_alt"])],
        foreground=[("readonly", APP_THEME["text"]), ("disabled", APP_THEME["disabled"])],
        bordercolor=[("focus", APP_THEME["primary"])],
    )
    style.configure(
        "App.TButton",
        background=APP_THEME["panel_alt"],
        foreground=APP_THEME["text"],
        bordercolor=APP_THEME["border"],
        lightcolor=APP_THEME["border"],
        darkcolor=APP_THEME["border_soft"],
        focusthickness=1,
        focuscolor=APP_THEME["primary"],
        padding=(12, 5),
        font=button_font,
    )
    style.map(
        "App.TButton",
        background=[
            ("pressed", APP_THEME["primary_pressed"]),
            ("active", APP_THEME["border"]),
            ("disabled", APP_THEME["input"]),
        ],
        foreground=[("disabled", APP_THEME["disabled"])],
    )
    style.configure(
        "Primary.TButton",
        background=APP_THEME["primary"],
        foreground=APP_THEME["primary_text"],
        bordercolor=APP_THEME["primary_hover"],
        lightcolor=APP_THEME["primary_hover"],
        darkcolor=APP_THEME["primary_pressed"],
        padding=(14, 7),
        font=button_font,
    )
    style.map(
        "Primary.TButton",
        background=[
            ("pressed", APP_THEME["primary_pressed"]),
            ("active", APP_THEME["primary_hover"]),
            ("disabled", APP_THEME["input"]),
        ],
        foreground=[
            ("disabled", APP_THEME["disabled"]),
            ("pressed", APP_THEME["primary_text"]),
            ("active", APP_THEME["primary_text"]),
        ],
    )
    style.configure(
        "Subtle.TButton",
        background=APP_THEME["input"],
        foreground=APP_THEME["muted"],
        bordercolor=APP_THEME["border_soft"],
        padding=(12, 5),
        font=base_font,
    )
    style.map(
        "Subtle.TButton",
        background=[("pressed", APP_THEME["border"]), ("active", APP_THEME["panel_alt"])],
        foreground=[("active", APP_THEME["text"])],
    )
    style.configure(
        "App.TCheckbutton",
        background=APP_THEME["background"],
        foreground=APP_THEME["text"],
        focuscolor=APP_THEME["primary"],
        indicatorbackground=APP_THEME["input"],
        indicatorforeground=APP_THEME["primary"],
    )
    style.map(
        "App.TCheckbutton",
        background=[("active", APP_THEME["background"])],
        foreground=[("active", APP_THEME["accent"]), ("selected", APP_THEME["text"])],
        indicatorbackground=[("selected", APP_THEME["primary"]), ("active", APP_THEME["panel_alt"])],
    )
    style.configure(
        "App.TRadiobutton",
        background=APP_THEME["panel"],
        foreground=APP_THEME["text"],
        focuscolor=APP_THEME["primary"],
        indicatorbackground=APP_THEME["input"],
        indicatorforeground=APP_THEME["primary"],
    )
    style.map(
        "App.TRadiobutton",
        background=[("active", APP_THEME["panel"])],
        foreground=[("active", APP_THEME["accent"]), ("selected", APP_THEME["text"])],
        indicatorbackground=[("selected", APP_THEME["primary"]), ("active", APP_THEME["panel_alt"])],
    )
    style.configure(
        "App.Horizontal.TSeparator",
        background=APP_THEME["border_soft"],
    )
    style.configure(
        "Model.Treeview",
        background=APP_THEME["input"],
        fieldbackground=APP_THEME["input"],
        foreground=APP_THEME["text"],
        bordercolor=APP_THEME["border_soft"],
        rowheight=24,
    )
    style.configure(
        "Model.Treeview.Heading",
        background=APP_THEME["panel_alt"],
        foreground=APP_THEME["text"],
        bordercolor=APP_THEME["border"],
        font=button_font,
    )
    style.map(
        "Model.Treeview",
        background=[("selected", APP_THEME["primary"])],
        foreground=[("selected", APP_THEME["text"])],
    )
    style.configure(
        "App.Vertical.TScrollbar",
        background=APP_THEME["panel_alt"],
        troughcolor=APP_THEME["input"],
        bordercolor=APP_THEME["border_soft"],
        arrowcolor=APP_THEME["accent"],
    )


def configure_log_widget(log_widget):
    log_widget.configure(
        background=APP_THEME["log_background"],
        foreground=APP_THEME["text"],
        insertbackground=APP_THEME["primary_hover"],
        selectbackground=APP_THEME["primary"],
        selectforeground=APP_THEME["primary_text"],
        relief="flat",
        borderwidth=0,
        highlightthickness=0,
    )


def combobox_popdown_listbox_path(combobox):
    try:
        popdown = combobox.tk.call("ttk::combobox::PopdownWindow", str(combobox))
    except tk.TclError:
        return ""
    return f"{popdown}.f.l"


def combobox_popdown_options(combobox):
    listbox_path = combobox_popdown_listbox_path(combobox)
    options = {}
    for option in ("background", "foreground", "selectbackground", "selectforeground"):
        try:
            options[option] = str(combobox.tk.call(listbox_path, "cget", f"-{option}"))
        except tk.TclError:
            options[option] = ""
    return options


def configure_combobox_popdown(combobox):
    listbox_path = combobox_popdown_listbox_path(combobox)
    if not listbox_path:
        return
    option_values = {
        "background": APP_THEME["input"],
        "foreground": APP_THEME["text"],
        "selectbackground": APP_THEME["primary"],
        "selectforeground": APP_THEME["primary_text"],
    }
    for option, value in option_values.items():
        try:
            combobox.tk.call(listbox_path, "configure", f"-{option}", value)
        except tk.TclError:
            pass


def draw_rounded_rectangle(canvas, x1, y1, x2, y2, radius, fill, outline, width=1):
    radius = max(1, min(radius, int((x2 - x1) / 2), int((y2 - y1) / 2)))
    points = [
        x1 + radius, y1,
        x2 - radius, y1,
        x2, y1,
        x2, y1 + radius,
        x2, y2 - radius,
        x2, y2,
        x2 - radius, y2,
        x1 + radius, y2,
        x1, y2,
        x1, y2 - radius,
        x1, y1 + radius,
        x1, y1,
    ]
    canvas.create_polygon(
        points,
        smooth=True,
        splinesteps=16,
        fill=fill,
        outline=outline,
        width=width,
        tags="rounded",
    )


class RoundedSection(tk.Frame):
    def __init__(self, master, text, padding=10, radius=12):
        super().__init__(master, background=APP_THEME["background"], borderwidth=0, highlightthickness=0)
        self.radius = radius
        self.title = ttk.Label(self, text=text, style="Panel.TLabelframe.Label")
        self.title.pack(anchor="w", pady=(0, 4))
        self.box = tk.Frame(self, background=APP_THEME["background"], borderwidth=0, highlightthickness=0)
        self.box.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(
            self.box,
            borderwidth=0,
            highlightthickness=0,
            background=APP_THEME["background"],
        )
        self.canvas.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.body = ttk.Frame(self.box, padding=padding, style="Panel.TFrame")
        self.body.pack(fill="both", expand=True, padx=2, pady=2)
        self.box.bind("<Configure>", self._redraw)

    def _redraw(self, _event=None):
        width = max(self.box.winfo_width() - 1, 2)
        height = max(self.box.winfo_height() - 1, 2)
        self.canvas.delete("rounded")
        draw_rounded_rectangle(
            self.canvas,
            1,
            1,
            width,
            height,
            self.radius,
            APP_THEME["panel"],
            APP_THEME["border"],
            1,
        )
        self.canvas.lower("rounded")

    def apply_theme(self):
        super().configure(background=APP_THEME["background"])
        self.box.configure(background=APP_THEME["background"])
        self.canvas.configure(background=APP_THEME["background"])
        self._redraw()


class RoundedButton(tk.Canvas):
    def __init__(self, master, text, command=None, variant="app", radius=12, width=112, height=34):
        super().__init__(
            master,
            borderwidth=0,
            highlightthickness=0,
            background=APP_THEME["background"],
            width=width,
            height=height,
            cursor="hand2",
        )
        self._text = text
        self.command = command
        self.variant = variant
        self.radius = radius
        self.state = "normal"
        self._hover = False
        self._pressed = False
        self.bind("<Configure>", self._redraw)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self._redraw()

    def _colors(self):
        disabled = self.state == "disabled"
        if self.variant == "primary":
            background = APP_THEME["primary"]
            foreground = APP_THEME["primary_text"]
            outline = APP_THEME["primary_hover"]
            if self._pressed:
                background = APP_THEME["primary_pressed"]
            elif self._hover:
                background = APP_THEME["primary_hover"]
        elif self.variant == "subtle":
            background = APP_THEME["input"]
            foreground = APP_THEME["muted"]
            outline = APP_THEME["border_soft"]
            if self._pressed:
                background = APP_THEME["border"]
            elif self._hover:
                background = APP_THEME["panel_alt"]
                foreground = APP_THEME["text"]
        else:
            background = APP_THEME["panel_alt"]
            foreground = APP_THEME["text"]
            outline = APP_THEME["border"]
            if self._pressed:
                background = APP_THEME["primary_pressed"]
            elif self._hover:
                background = APP_THEME["border"]
        if disabled:
            background = APP_THEME["input"]
            foreground = APP_THEME["disabled"]
            outline = APP_THEME["border_soft"]
        return background, foreground, outline

    def _redraw(self, _event=None):
        width = max(self.winfo_width() - 1, 2)
        height = max(self.winfo_height() - 1, 2)
        background, foreground, outline = self._colors()
        super().configure(background=APP_THEME["background"])
        self.delete("all")
        draw_rounded_rectangle(
            self,
            1,
            1,
            width,
            height,
            self.radius,
            background,
            outline,
            1,
        )
        self.create_text(
            width / 2,
            height / 2,
            text=self._text,
            fill=foreground,
            font=("Microsoft YaHei UI", 9, "bold" if self.variant == "primary" else "normal"),
            tags="label",
        )

    def _on_enter(self, _event):
        if self.state != "disabled":
            self._hover = True
            self._redraw()

    def _on_leave(self, _event):
        self._hover = False
        self._pressed = False
        self._redraw()

    def _on_press(self, _event):
        if self.state != "disabled":
            self._pressed = True
            self._redraw()

    def _on_release(self, event):
        if self.state == "disabled":
            return
        was_pressed = self._pressed
        self._pressed = False
        self._redraw()
        if was_pressed and 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height():
            if self.command:
                self.command()

    def configure(self, cnf=None, **kwargs):
        if cnf:
            kwargs.update(cnf)
        for key in ("text", "command", "state"):
            if key in kwargs:
                value = kwargs.pop(key)
                if key == "text":
                    self._text = value
                elif key == "command":
                    self.command = value
                else:
                    self.state = value
                    super().configure(cursor="" if value == "disabled" else "hand2")
        result = None
        if kwargs:
            result = super().configure(**kwargs)
        self._redraw()
        return result

    config = configure

    def cget(self, key):
        if key == "text":
            return self._text
        if key == "state":
            return self.state
        if key == "command":
            return self.command
        return super().cget(key)

    def apply_theme(self):
        self._redraw()


def center_window_on_parent(parent, window, width, height):
    parent.update_idletasks()
    window.update_idletasks()

    parent_x = parent.winfo_rootx()
    parent_y = parent.winfo_rooty()
    parent_width = parent.winfo_width()
    parent_height = parent.winfo_height()

    x = parent_x + max((parent_width - width) // 2, 0)
    y = parent_y + max((parent_height - height) // 2, 0)

    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    x = max(0, min(x, screen_width - width))
    y = max(0, min(y, screen_height - height))

    window.geometry(f"{width}x{height}+{x}+{y}")


def mousewheel_scroll_units(event):
    if getattr(event, "num", None) == 4:
        return -1
    if getattr(event, "num", None) == 5:
        return 1

    delta = getattr(event, "delta", 0)
    if not delta:
        return 0
    if abs(delta) < 120:
        return -1 if delta > 0 else 1
    return -int(delta / 120)


def bind_page_mousewheel(root, canvas):
    def scroll_page(event):
        units = mousewheel_scroll_units(event)
        if not units:
            return None
        canvas.yview_scroll(units, "units")
        return "break"

    root.bind("<MouseWheel>", scroll_page, add="+")
    root.bind("<Button-4>", scroll_page, add="+")
    root.bind("<Button-5>", scroll_page, add="+")


class ModelSelectorDialog:
    def __init__(self, app, settings):
        self.app = app
        self.root = app.root
        self.settings = settings
        self.models = []
        self.model_by_tree_id = {}

        self.window = tk.Toplevel(self.root)
        self.window.withdraw()
        self.window.title("选择模型")
        self.window.minsize(*MODEL_SELECTOR_MIN_SIZE)
        self.window.transient(self.root)
        self.window.configure(background=APP_THEME["background"])
        center_window_on_parent(self.root, self.window, *MODEL_SELECTOR_SIZE)

        frame = ttk.Frame(self.window, padding=14, style="Dialog.TFrame")
        frame.pack(fill="both", expand=True)
        frame.rowconfigure(2, weight=1)
        frame.columnconfigure(0, weight=1)

        header = ttk.Frame(frame, style="Dialog.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="模型", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(header, text="刷新", command=self.load_models, style="App.TButton").grid(
            row=0, column=1, sticky="e"
        )

        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(frame, textvariable=self.search_var, style="App.TEntry")
        search_entry.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        search_entry.insert(0, "")
        search_entry.configure()
        self.search_var.trace_add("write", lambda *_args: self.render_models())

        list_frame = ttk.Frame(frame, style="Dialog.TFrame")
        list_frame.grid(row=2, column=0, sticky="nsew")
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            list_frame,
            columns=("name", "id", "context"),
            show="headings",
            selectmode="browse",
            style="Model.Treeview",
        )
        self.tree.heading("name", text="名称")
        self.tree.heading("id", text="模型 ID")
        self.tree.heading("context", text="上下文")
        self.tree.column("name", width=180, anchor="w")
        self.tree.column("id", width=290, anchor="w")
        self.tree.column("context", width=80, anchor="e")
        tree_scrollbar = ttk.Scrollbar(
            list_frame,
            orient="vertical",
            command=self.tree.yview,
            style="App.Vertical.TScrollbar",
        )
        self.tree.configure(yscrollcommand=tree_scrollbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        tree_scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<Double-1>", lambda _event: self.use_selected_model())
        self.tree.bind("<Return>", lambda _event: self.use_selected_model())

        bottom = ttk.Frame(frame, style="Dialog.TFrame")
        bottom.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        bottom.columnconfigure(0, weight=1)
        self.status_var = tk.StringVar(value="")
        ttk.Label(bottom, textvariable=self.status_var, style="Dialog.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Button(
            bottom,
            text="使用选中模型",
            command=self.use_selected_model,
            style="Primary.TButton",
        ).grid(
            row=0, column=1, sticky="e", padx=(8, 0)
        )
        ttk.Button(bottom, text="关闭", command=self.window.destroy, style="Subtle.TButton").grid(
            row=0, column=2, sticky="e", padx=(8, 0)
        )

        self.window.deiconify()
        self.window.lift(self.root)
        search_entry.focus_set()
        self.load_models()

    def load_models(self):
        self.status_var.set("正在拉取模型列表...")
        for item_id in self.tree.get_children():
            self.tree.delete(item_id)

        def worker():
            try:
                models = translator.fetch_available_models(self.settings)
            except Exception as exc:  # noqa: BLE001
                message = str(exc)
                self.root.after(0, lambda message=message: self.show_error(message))
                return
            self.root.after(0, lambda: self.show_models(models))

        threading.Thread(target=worker, daemon=True).start()

    def show_error(self, message):
        if not self.window.winfo_exists():
            return
        self.models = []
        self.model_by_tree_id = {}
        self.status_var.set(message)
        messagebox.showerror("模型列表", message, parent=self.window)

    def show_models(self, models):
        if not self.window.winfo_exists():
            return
        self.models = models
        self.render_models()

    def render_models(self):
        if not self.window.winfo_exists():
            return

        query = self.search_var.get().strip().lower()
        for item_id in self.tree.get_children():
            self.tree.delete(item_id)

        self.model_by_tree_id = {}
        matched = 0
        for model in self.models:
            text = f"{model['name']} {model['id']}".lower()
            if query and query not in text:
                continue
            item_id = self.tree.insert(
                "",
                "end",
                values=(model["name"], model["id"], model["context_length"]),
            )
            self.model_by_tree_id[item_id] = model
            matched += 1

        if matched:
            first = self.tree.get_children()[0]
            self.tree.selection_set(first)
            self.tree.focus(first)
        self.status_var.set(f"共 {len(self.models)} 个模型，当前显示 {matched} 个")

    def use_selected_model(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("模型列表", "请先选择一个模型。", parent=self.window)
            return

        model = self.model_by_tree_id.get(selection[0])
        if not model:
            return
        self.app.model_id.set(model["id"])
        self.window.destroy()


class App:
    def __init__(self):
        self.root = tk.Tk()
        saved_settings = translator.load_settings()
        self.theme_id = tk.StringVar(value=normalize_theme_id(saved_settings.get("theme_id", "")))
        self.theme_label = tk.StringVar(value=theme_label(self.theme_id.get()))
        configure_root_window(self.root, self.theme_id.get())

        self.vars = {}
        self.source_dir = tk.StringVar(value=str(translator.SOURCE_DIR))
        self.output_dir = tk.StringVar(value=str(translator.OUTPUT_BASE_DIR / "custom_languages"))
        self.output_format = tk.StringVar(value=translator.DEFAULT_OUTPUT_FORMAT)
        self.api_url = tk.StringVar(value=saved_settings["api_url"])
        self.api_key = tk.StringVar(value=saved_settings["api_key"])
        self.model_id = tk.StringVar(value=saved_settings["model_id"])
        self.proxy_url = tk.StringVar(value=saved_settings["proxy_url"])
        self.log_queue = queue.Queue()
        self.worker = None
        self.rounded_sections = []
        self.rounded_buttons = []

        self.build_ui()
        self.root.after(150, self.flush_logs)

    def create_section(self, parent, text, padding=10, **pack_options):
        section = RoundedSection(parent, text=text, padding=padding)
        section.pack(**pack_options)
        self.rounded_sections.append(section)
        return section.body

    def create_button(self, parent, text, command, variant="app", **layout_options):
        button = RoundedButton(parent, text=text, command=command, variant=variant)
        manager = layout_options.pop("manager", "grid")
        if manager == "pack":
            button.pack(**layout_options)
        else:
            button.grid(**layout_options)
        self.rounded_buttons.append(button)
        return button

    def build_ui(self):
        outer = ttk.Frame(self.root, style="App.TFrame")
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(
            outer,
            borderwidth=0,
            highlightthickness=0,
            background=APP_THEME["background"],
        )
        self.canvas = canvas
        scrollbar = ttk.Scrollbar(
            outer,
            orient="vertical",
            command=canvas.yview,
            style="App.Vertical.TScrollbar",
        )
        canvas.configure(yscrollcommand=scrollbar.set)
        bind_page_mousewheel(self.root, canvas)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        frame = ttk.Frame(canvas, padding=16, style="App.TFrame")
        window_id = canvas.create_window((0, 0), window=frame, anchor="nw")

        def update_scroll_region(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def resize_inner_frame(event):
            canvas.itemconfigure(window_id, width=event.width)

        frame.bind("<Configure>", update_scroll_region)
        canvas.bind("<Configure>", resize_inner_frame)

        settings_frame = self.create_section(frame, text="API 设置", padding=10, fill="x", pady=(0, 12))
        settings_frame.columnconfigure(1, weight=1)

        ttk.Label(settings_frame, text="API 地址", style="Panel.TLabel").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(settings_frame, textvariable=self.api_url, style="App.TEntry").grid(
            row=0, column=1, columnspan=2, sticky="ew", padx=(10, 0), pady=4
        )

        ttk.Label(settings_frame, text="API 密钥", style="Panel.TLabel").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(settings_frame, textvariable=self.api_key, show="*", style="App.TEntry").grid(
            row=1, column=1, sticky="ew", padx=(10, 8), pady=4
        )
        self.create_button(
            settings_frame, text="检查配置", command=self.check_settings, row=1, column=2, sticky="e", pady=4
        )

        ttk.Label(settings_frame, text="模型 ID", style="Panel.TLabel").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(settings_frame, textvariable=self.model_id, style="App.TEntry").grid(
            row=2, column=1, sticky="ew", padx=(10, 8), pady=4
        )
        self.create_button(
            settings_frame, text="选择模型", command=self.open_model_selector, row=2, column=2, sticky="e", pady=4
        )

        ttk.Label(settings_frame, text="代理地址", style="Panel.TLabel").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Entry(settings_frame, textvariable=self.proxy_url, style="App.TEntry").grid(
            row=3, column=1, sticky="ew", padx=(10, 8), pady=4
        )
        self.create_button(
            settings_frame, text="保存设置", command=self.save_settings, row=3, column=2, sticky="e", pady=4
        )

        ttk.Label(settings_frame, text="界面配色", style="Panel.TLabel").grid(row=4, column=0, sticky="w", pady=4)
        theme_combo = ttk.Combobox(
            settings_frame,
            textvariable=self.theme_label,
            values=theme_labels(),
            state="readonly",
            style="App.TCombobox",
        )
        self.theme_combo = theme_combo
        theme_combo.grid(row=4, column=1, sticky="ew", padx=(10, 8), pady=4)
        theme_combo.bind("<<ComboboxSelected>>", self.on_theme_selected)
        configure_combobox_popdown(theme_combo)
        self.create_button(
            settings_frame, text="应用配色", command=self.on_theme_selected, row=4, column=2, sticky="e", pady=4
        )

        ttk.Label(frame, text="选择要生成的语言", style="App.TLabel").pack(anchor="w")
        ttk.Label(frame, text="点开始后会直接运行翻译，不再生成 BAT", style="Hint.TLabel").pack(anchor="w", pady=(0, 10))

        grid = ttk.Frame(frame, style="App.TFrame")
        grid.pack(fill="x")
        for column in range(LANGUAGE_COLUMNS):
            grid.columnconfigure(column, weight=1)

        for index, (code, label) in enumerate(LANGUAGES):
            var = tk.BooleanVar(value=code in DEFAULT_CODES)
            self.vars[code] = var
            checkbox = ttk.Checkbutton(
                grid,
                text=f"{label} ({code})",
                variable=var,
                style="App.TCheckbutton",
            )
            checkbox.grid(
                row=index // LANGUAGE_COLUMNS,
                column=index % LANGUAGE_COLUMNS,
                sticky="w",
                padx=(0, 18),
                pady=4,
            )

        ttk.Separator(frame, style="App.Horizontal.TSeparator").pack(fill="x", pady=12)

        paths_frame = self.create_section(frame, text="输入输出目录", padding=10, fill="x", pady=(0, 12))
        paths_frame.columnconfigure(1, weight=1)

        ttk.Label(paths_frame, text="输入图片文件夹", style="Panel.TLabel").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(paths_frame, textvariable=self.source_dir, style="App.TEntry").grid(
            row=0, column=1, sticky="ew", padx=(10, 8), pady=4
        )
        self.create_button(
            paths_frame, text="选择", command=self.choose_source_dir, row=0, column=2, sticky="e", pady=4
        )

        ttk.Label(paths_frame, text="输出文件夹", style="Panel.TLabel").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(paths_frame, textvariable=self.output_dir, style="App.TEntry").grid(
            row=1, column=1, sticky="ew", padx=(10, 8), pady=4
        )
        self.create_button(
            paths_frame, text="选择", command=self.choose_output_dir, row=1, column=2, sticky="e", pady=4
        )

        format_frame = self.create_section(frame, text="输出图片格式", padding=10, fill="x", pady=(0, 12))
        for column in range(len(translator.OUTPUT_FORMATS)):
            format_frame.columnconfigure(column, weight=1)
        for index, (format_code, format_spec) in enumerate(translator.OUTPUT_FORMATS.items()):
            ttk.Radiobutton(
                format_frame,
                text=format_spec["label"],
                value=format_code,
                variable=self.output_format,
                style="App.TRadiobutton",
            ).grid(row=0, column=index, sticky="w", padx=(0, 24), pady=2)

        button_row = ttk.Frame(frame, style="App.TFrame")
        button_row.pack(fill="x", pady=(4, 8))

        self.start_button = self.create_button(
            button_row,
            text="开始翻译",
            command=self.start_translation,
            variant="primary",
            manager="pack",
            fill="x",
        )
        self.create_button(
            frame,
            text="清空选择",
            command=self.clear_all,
            variant="subtle",
            manager="pack",
            fill="x",
            pady=(8, 0),
        )

        log_frame = self.create_section(frame, text="运行日志", padding=8, fill="both", expand=True, pady=(14, 0))
        self.log = scrolledtext.ScrolledText(log_frame, height=12, wrap="word", font=("Consolas", 10))
        self.log.pack(fill="both", expand=True)
        self.log.configure(
            state="disabled",
        )
        configure_log_widget(self.log)

        note = (
            "说明：\n"
            "1. 输入图片文件夹支持直接复制粘贴路径\n"
            "2. 输出会写入你填写的输出文件夹，并按语言自动分子文件夹\n"
            "3. API 设置会保存到同目录下的 settings.json\n"
            "4. 如果接口额度用完，日志里会直接显示"
        )
        ttk.Label(frame, text=note, justify="left", style="Hint.TLabel").pack(anchor="w", pady=(14, 0))

    def choose_source_dir(self):
        selected = filedialog.askdirectory(
            title="选择输入图片文件夹",
            initialdir=self.source_dir.get() or str(translator.BASE_DIR),
        )
        if selected:
            self.source_dir.set(selected)

    def choose_output_dir(self):
        selected = filedialog.askdirectory(
            title="选择输出文件夹",
            initialdir=self.output_dir.get() or str(translator.OUTPUT_BASE_DIR),
        )
        if selected:
            self.output_dir.set(selected)

    def apply_theme(self, theme_id):
        normalized_theme_id = normalize_theme_id(theme_id)
        self.theme_id.set(normalized_theme_id)
        self.theme_label.set(theme_label(normalized_theme_id))
        configure_app_style(self.root, normalized_theme_id)
        if hasattr(self, "canvas"):
            self.canvas.configure(background=APP_THEME["background"])
        for section in getattr(self, "rounded_sections", []):
            section.apply_theme()
        for button in getattr(self, "rounded_buttons", []):
            button.apply_theme()
        if hasattr(self, "theme_combo"):
            configure_combobox_popdown(self.theme_combo)
        if hasattr(self, "log"):
            configure_log_widget(self.log)

    def on_theme_selected(self, _event=None):
        self.apply_theme(theme_id_for_label(self.theme_label.get()))

    def current_settings(self):
        return {
            "api_url": self.api_url.get(),
            "api_key": self.api_key.get(),
            "model_id": self.model_id.get(),
            "proxy_url": self.proxy_url.get(),
            "theme_id": self.theme_id.get(),
        }

    def save_settings(self, show_message=True):
        settings = self.current_settings()
        errors = translator.validate_settings(settings)
        if errors:
            messagebox.showerror("API 设置不完整", "\n".join(errors))
            return None

        saved = translator.save_settings(settings)
        self.api_url.set(saved["api_url"])
        self.api_key.set(saved["api_key"])
        self.model_id.set(saved["model_id"])
        self.proxy_url.set(saved["proxy_url"])
        self.apply_theme(saved.get("theme_id", DEFAULT_THEME_ID))
        if show_message:
            messagebox.showinfo("已保存", "API 设置已保存。")
        return saved

    def check_settings(self):
        errors = translator.validate_settings(self.current_settings())
        if errors:
            messagebox.showerror("检查未通过", "\n".join(errors))
            return
        messagebox.showinfo("检查通过", "配置格式有效。开始翻译时会使用这些设置。")

    def open_model_selector(self):
        settings = self.current_settings()
        errors = translator.validate_model_fetch_settings(settings)
        if errors:
            messagebox.showerror("模型列表", "\n".join(errors))
            return
        ModelSelectorDialog(self, settings)

    def selected_codes(self):
        return [code for code, _label in LANGUAGES if self.vars[code].get()]

    def clear_all(self):
        for code, _label in LANGUAGES:
            self.vars[code].set(False)

    def append_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def flush_logs(self):
        try:
            while True:
                item = self.log_queue.get_nowait()
                if isinstance(item, tuple) and item[0] == "__done__":
                    exit_code = item[1]
                    self.start_button.configure(state="normal")
                    if exit_code == 0:
                        messagebox.showinfo("完成", "翻译任务已完成。")
                    else:
                        messagebox.showwarning("结束", "翻译任务已结束，但有失败项，请查看日志。")
                else:
                    self.append_log(str(item))
        except queue.Empty:
            pass
        self.root.after(150, self.flush_logs)

    def start_translation(self):
        codes = self.selected_codes()
        if not codes:
            messagebox.showerror("提示", "请至少选择一种语言。")
            return

        settings = self.save_settings(show_message=False)
        if settings is None:
            return
        settings["output_format"] = self.output_format.get()

        source_dir = self.source_dir.get().strip()
        output_dir = self.output_dir.get().strip()
        if not source_dir:
            messagebox.showerror("提示", "请填写输入图片文件夹。")
            return
        if not output_dir:
            messagebox.showerror("提示", "请填写输出文件夹。")
            return

        if self.worker and self.worker.is_alive():
            messagebox.showwarning("提示", "当前任务还在运行中。")
            return

        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.start_button.configure(state="disabled")

        def logger(message):
            self.log_queue.put(message)

        def worker():
            exit_code = translator.run_translation(
                tuple(codes),
                logger=logger,
                settings=settings,
                source_dir=source_dir,
                output_dir=output_dir,
            )
            self.log_queue.put(("__done__", exit_code))

        self.worker = threading.Thread(target=worker, daemon=True)
        self.worker.start()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
