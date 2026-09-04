#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ADB 剪贴板助手 - PC 端精简图形界面（白色简约风）。

布局（自上而下）：
  1. 权限清单（最上层），【推送并运行】按钮在清单右下方；
  2. 最近推送（原文）；
  3. 运行日志（滚动）。

功能：
  1. 点击【推送并运行】：安装 APK → 识别手机品牌 → 针对性提权 → 启动悬浮窗 → 1 秒轮询同步。
  2. 权限清单随推送流程自动刷新（无独立检查按钮）。
  3. 最近推送显示原文。
  4. 软件打开后完全静默，不做任何自动检测。
"""

import logging
import os
import queue
import re
import subprocess
import sys
import threading
import time
from datetime import datetime

import tkinter as tk
from tkinter import ttk

from adb_clipboard_sync import (
    AdbManager,
    ClipboardSyncManager,
    CommandRunner,
    Config,
    create_clipboard_handler,
)

PACKAGE = "ch.pete.adbclipboard"
APK_FILE = "app.apk"
ADB_EXE = "adb.exe"

# 白色简约配色
BG = "#ffffff"
CARD = "#f5f7fa"
BORDER = "#e5e7eb"
TEXT = "#1f2329"
MUTED = "#6b7280"
ACCENT = "#2f7bff"
ACCENT_DARK = "#1d4ed8"
ACCENT_LIGHT = "#3b82f6"
GREEN = "#16a34a"
RED = "#dc2626"
DOT_IDLE = "#cbd5e1"

PERM_NAMES = (
    "ADB",
    "设备",
    "应用",
    "悬浮窗权限",
    "剪贴板权限",
    "电池优化",
    "服务",
)


# ---------------------------------------------------------------- helpers

def resource_path(name: str) -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, name)
    here = os.path.dirname(os.path.abspath(__file__))
    for base in (here, os.path.join(here, "assets"), os.path.join(here, "build", "pc_staging")):
        p = os.path.join(base, name)
        if os.path.exists(p):
            return p
    return os.path.join(here, name)


def adb_binary() -> str:
    if getattr(sys, "frozen", False):
        bundled = resource_path(ADB_EXE)
        if os.path.exists(bundled):
            return bundled
    return os.environ.get("ADB", "adb")


def run_cmd(cmd, timeout=30):
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except Exception:
        return None


def now_text() -> str:
    return datetime.now().strftime("%H:%M:%S")


def check_adb() -> bool:
    r = run_cmd([adb_binary(), "version"], timeout=10)
    return r is not None and r.returncode == 0


def get_devices() -> list:
    r = run_cmd([adb_binary(), "devices"], timeout=10)
    if r is None or r.returncode != 0:
        return []
    devices = []
    for line in r.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            devices.append(parts[0])
    return devices


def check_service(device: str):
    """内部校验：悬浮窗服务是否已在运行。"""
    r = run_cmd([adb_binary(), "-s", device, "shell", "dumpsys", "activity", "services", PACKAGE], timeout=15)
    ok = r is not None and "FloatingViewService" in (r.stdout or "")
    return ok, ("运行中" if ok else "未运行")


# ------------------------------------------------------------ brand detect

def get_device_props(device: str) -> dict:
    """读取设备关键系统属性，用于品牌识别。"""
    props = {}
    r = run_cmd([adb_binary(), "-s", device, "shell", "getprop"], timeout=15)
    if r is None:
        return props
    for line in r.stdout.splitlines():
        m = re.match(r"\[([^\]]+)\]: \[([^\]]*)\]", line.strip())
        if m:
            props[m.group(1)] = m.group(2)
    return props


def get_brand(device: str):
    """识别品牌，返回 (brand_key, 展示文本)。brand_key 用于针对性提权。"""
    props = get_device_props(device)
    brand = (props.get("ro.product.brand") or "").lower()
    manufacturer = (props.get("ro.product.manufacturer") or "").lower()
    model = (props.get("ro.product.model") or "").strip()
    miui = (props.get("ro.miui.ui.version.name") or "").strip()
    emui = (props.get("ro.build.version.emui") or "").strip()
    coloros = (props.get("ro.build.version.oplusrom") or props.get("ro.oppo.version") or "").strip()
    originos = (props.get("ro.vivo.os.build.display.id") or props.get("ro.vivo.os.version") or "").strip()
    base = f"{brand or manufacturer} {model}".strip()

    joined = " ".join((brand, manufacturer, model))

    if "xiaomi" in joined or "redmi" in joined or "poco" in joined or miui:
        extra = f"（{miui}）" if miui else ""
        return "xiaomi", f"小米/Xiaomi{extra} · {base}"
    if "oppo" in joined or "oneplus" in joined or "realme" in joined:
        extra = f"（ColorOS {coloros}）" if coloros else ""
        return "oppo", f"OPPO/一加/真我{extra} · {base}"
    if "huawei" in joined or "honor" in joined or emui:
        extra = f"（{emui}）" if emui else ""
        return "huawei", f"华为/荣耀{extra} · {base}"
    if "vivo" in joined or "iqoo" in joined or originos:
        extra = f"（{originos}）" if originos else ""
        return "vivo", f"vivo/iQOO{extra} · {base}"
    if "samsung" in joined:
        return "samsung", f"三星 Samsung · {base}"
    if "google" in joined or model.lower().startswith("pixel"):
        return "google", f"Google Pixel · {base}"
    return "unknown", f"未知品牌 · {base}"


def grant_permissions(device: str, brand_key: str, on_log, verbose=True, on_perm=None):
    """通用 + 品牌针对性提权。逐条尝试，失败静默跳过，不阻塞流程。"""
    steps = [
        ("悬浮窗权限", ["appops", "set", PACKAGE, "SYSTEM_ALERT_WINDOW", "allow"]),
        ("写剪贴板", ["appops", "set", PACKAGE, "WRITE_CLIPBOARD", "allow"]),
        ("读剪贴板", ["appops", "set", PACKAGE, "READ_CLIPBOARD", "allow"]),
        ("后台运行", ["appops", "set", PACKAGE, "RUN_IN_BACKGROUND", "allow"]),
        ("后台运行(任意)", ["appops", "set", PACKAGE, "RUN_ANY_IN_BACKGROUND", "allow"]),
        ("开机自启", ["appops", "set", PACKAGE, "BOOT_COMPLETED", "allow"]),
    ]
    brand_steps = {
        "xiaomi": [
            ("后台弹出界面", ["appops", "set", PACKAGE, "10017", "allow"]),
            ("自启动", ["appops", "set", PACKAGE, "10008", "allow"]),
            ("MIUI 后台限制", ["appops", "set", PACKAGE, "10021", "allow"]),
        ],
        "oppo": [
            ("自动启动", ["appops", "set", PACKAGE, "OP_AUTO_START", "allow"]),
            ("后台启动活动", ["appops", "set", PACKAGE, "OP_ACTIVITY_START_BACKGROUND", "allow"]),
        ],
        "huawei": [
            ("自动启动", ["appops", "set", PACKAGE, "OP_AUTO_START", "allow"]),
            ("后台启动活动", ["appops", "set", PACKAGE, "OP_ACTIVITY_START_BACKGROUND", "allow"]),
        ],
        "vivo": [
            ("自动启动", ["appops", "set", PACKAGE, "OP_AUTO_START", "allow"]),
            ("后台启动活动", ["appops", "set", PACKAGE, "OP_ACTIVITY_START_BACKGROUND", "allow"]),
        ],
        "samsung": [],
    }
    # 清单行与 appop 的对应关系
    row_map = {
        "SYSTEM_ALERT_WINDOW": "悬浮窗权限",
        "WRITE_CLIPBOARD": "剪贴板权限",
    }

    # 电池优化豁免
    r = run_cmd([adb_binary(), "-s", device, "shell", "dumpsys", "deviceidle", "whitelist", "+" + PACKAGE], timeout=15)
    whitelist_ok = r is not None and r.returncode == 0
    if whitelist_ok and verbose:
        on_log("已加入电池优化白名单")
    if on_perm:
        on_perm("电池优化", whitelist_ok, "已豁免" if whitelist_ok else "未豁免")

    for name, args in steps + brand_steps.get(brand_key, []):
        r = run_cmd([adb_binary(), "-s", device, "shell"] + args, timeout=15)
        ok = r is not None and r.returncode == 0
        if ok and verbose:
            on_log(f"已授予：{name}")
        if on_perm and args[3] in row_map:
            on_perm(row_map[args[3]], ok, "已允许" if ok else "授权失败")


# ------------------------------------------------------------ push & start

def push_and_start(device: str, on_log, on_perm=None):
    """安装 APK、识别品牌、针对性提权、启动悬浮窗。返回 (是否成功, 提示)。"""
    apk = resource_path(APK_FILE)
    if not os.path.exists(apk):
        return False, f"未找到内置 APK：{apk}"

    on_log("正在安装 APK ...")
    r = run_cmd([adb_binary(), "-s", device, "install", "-r", "-t", apk], timeout=180)
    output = (r.stdout or "") + (r.stderr or "")
    if r is None or r.returncode != 0:
        if "INSTALL_FAILED_USER_RESTRICTED" in output:
            return False, "安装被手机拦截：请在开发者选项中开启“USB 安装”后重试"
        if on_perm:
            on_perm("应用", False, "安装失败")
        return False, f"安装失败：{output.strip()[:200]}"
    on_log("APK 安装成功")
    if on_perm:
        on_perm("应用", True, "已安装")

    brand_key, brand_display = get_brand(device)
    on_log(f"检测到设备：{brand_display}")
    if on_perm:
        on_perm("设备", True, f"{device} · {brand_display}")
    on_log("正在针对性提权 ...")
    grant_permissions(device, brand_key, on_log, verbose=True, on_perm=on_perm)

    # 部分系统（如 MIUI）安装后会重置悬浮窗权限，最多重试 3 次
    for attempt in range(1, 4):
        on_log(f"启动悬浮窗（第 {attempt} 次）...")
        grant_permissions(device, brand_key, on_log, verbose=False, on_perm=None)
        run_cmd([adb_binary(), "-s", device, "shell", "am", "force-stop", PACKAGE], timeout=15)
        run_cmd([adb_binary(), "-s", device, "shell", "am", "start", "-n", f"{PACKAGE}/.MainActivity"], timeout=15)
        time.sleep(3)
        ok, detail = check_service(device)
        if on_perm:
            on_perm("服务", ok, detail)
        if ok:
            return True, f"已安装并运行（{brand_display} · {detail}）"

    return False, "应用已启动但悬浮窗服务未运行，请手动开启“显示在其他应用上层”权限后重试"


# ------------------------------------------------------------- sync thread

class GuiLogHandler(logging.Handler):
    def __init__(self, q: queue.Queue):
        super().__init__()
        self.q = q

    def emit(self, record):
        try:
            self.q.put(self.format(record))
        except Exception:
            pass


def start_sync_thread(log_queue: queue.Queue, adb_path_override=None, on_clipboard_synced=None):
    """在后台线程运行 1 秒轮询的同步循环。"""
    logger = logging.getLogger("adb_clipboard_sync")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = GuiLogHandler(log_queue)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s", "%H:%M:%S"))
    logger.handlers[:] = [handler]

    if adb_path_override:
        os.environ["ADB"] = adb_path_override

    config = Config(verbose=False, connected_devices_delay=1, no_connected_device_delay=3)
    command_runner = CommandRunner(logger)
    adb_manager = AdbManager(command_runner, logger, config)
    clipboard_handler = create_clipboard_handler(command_runner)
    sync_manager = ClipboardSyncManager(
        config, clipboard_handler, adb_manager, logger,
        on_clipboard_synced=on_clipboard_synced,
    )

    def run():
        sync_manager.sync_with_devices()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t


# -------------------------------------------------------------------- GUI

class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.log_queue = queue.Queue()
        self.busy = False
        self._sync_started = False

        root.title("ADB 剪贴板助手")
        root.geometry("460x600")
        root.minsize(400, 540)
        root.configure(bg=BG)
        self._set_window_icon(root)

        style = ttk.Style(root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure(
            "Accent.TButton",
            background=ACCENT, foreground="#ffffff",
            bordercolor=ACCENT, lightcolor=ACCENT, darkcolor=ACCENT,
            padding=(16, 7), font=("Microsoft YaHei UI", 10, "bold"),
        )
        style.map(
            "Accent.TButton",
            background=[("pressed", ACCENT_DARK), ("active", ACCENT_LIGHT), ("disabled", "#9dbdfb")],
            bordercolor=[("pressed", ACCENT_DARK), ("active", ACCENT_LIGHT)],
            lightcolor=[("pressed", ACCENT_DARK), ("active", ACCENT_LIGHT)],
            darkcolor=[("pressed", ACCENT_DARK), ("active", ACCENT_LIGHT)],
        )

        # 权限清单（最上层）
        perm_card = self._card(root)
        perm_card.pack(fill="x", padx=14, pady=(14, 0))
        tk.Label(perm_card, text="权限清单", bg=CARD, fg=TEXT,
                 font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w", padx=14, pady=(10, 4))
        perm_grid = tk.Frame(perm_card, bg=CARD)
        perm_grid.pack(fill="x", padx=14, pady=(0, 2))
        perm_grid.columnconfigure(1, weight=1)
        self.perm_rows = {}
        for i, name in enumerate(PERM_NAMES):
            left = tk.Frame(perm_grid, bg=CARD)
            left.grid(row=i, column=0, sticky="w", pady=2)
            dot = tk.Label(left, text="○", bg=CARD, fg=DOT_IDLE, font=("Segoe UI", 9), width=2, anchor="w")
            dot.pack(side="left")
            tk.Label(left, text=name, bg=CARD, fg=TEXT, font=("Microsoft YaHei UI", 10)).pack(side="left")
            status = tk.Label(perm_grid, text="-", bg=CARD, fg=MUTED,
                              font=("Microsoft YaHei UI", 9), anchor="e", wraplength=280, justify="right")
            status.grid(row=i, column=1, sticky="e", pady=2)
            self.perm_rows[name] = (dot, status)

        # 按钮：清单右下方
        btn_row = tk.Frame(perm_card, bg=CARD)
        btn_row.pack(fill="x", padx=14, pady=(4, 10))
        self.btn_push = ttk.Button(btn_row, text="推送并运行", style="Accent.TButton", command=self.on_push)
        self.btn_push.pack(side="right")

        # 最近推送（原文）：清单与日志之间
        push_card = self._card(root)
        push_card.pack(fill="x", padx=14, pady=(10, 0))
        tk.Label(push_card, text="最近推送（原文）", bg=CARD, fg=TEXT,
                 font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w", padx=14, pady=(10, 4))
        self.push_text = tk.Text(push_card, height=2, wrap="word", state="disabled",
                                 bg="#ffffff", fg=TEXT, relief="flat",
                                 highlightbackground=BORDER, highlightthickness=1,
                                 font=("Microsoft YaHei UI", 9), padx=8, pady=5)
        self.push_text.pack(fill="x", padx=14, pady=(2, 12))

        # 运行日志（底部滚动）
        log_card = self._card(root)
        log_card.pack(fill="both", expand=True, padx=14, pady=(10, 14))
        tk.Label(log_card, text="运行日志", bg=CARD, fg=TEXT,
                 font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w", padx=14, pady=(10, 4))
        self.log_text = tk.Text(log_card, height=8, state="disabled", wrap="none",
                                bg="#ffffff", fg=TEXT, relief="flat",
                                highlightbackground=BORDER, highlightthickness=1,
                                font=("Consolas", 9), padx=8, pady=5)
        self.log_text.pack(fill="both", expand=True, padx=14, pady=(2, 12))

        self.root.after(250, self.drain_log_queue)

    @staticmethod
    def _card(parent):
        return tk.Frame(parent, bg=CARD, highlightbackground=BORDER, highlightthickness=1)

    @staticmethod
    def _set_window_icon(root: tk.Tk):
        """把窗口标题栏图标设为软件图标（替代 Tk 默认的羽毛图标）。"""
        for name in ("ic_launcher.png", "app_icon.png"):
            path = resource_path(name)
            if not os.path.exists(path):
                continue
            try:
                img = tk.PhotoImage(file=path)
                root.iconphoto(True, img)
                # 保存引用，防止图标被垃圾回收
                root._window_icon = img
                return
            except Exception:
                continue

    # ---------------- ui helpers

    def log(self, message: str):
        self.log_queue.put(f"{now_text()} - INFO - {message}")

    def drain_log_queue(self):
        try:
            while True:
                item = self.log_queue.get_nowait()
                if isinstance(item, str):
                    self.append_log(item)
                elif item[0] == "__perm__":
                    _, name, ok, detail = item
                    self.set_perm(name, ok, detail)
                elif item[0] == "__push_result__":
                    _, ok, msg = item
                    self.append_log(("成功：", "失败：")[not ok] + msg)
                    if ok:
                        self.start_monitoring()
                elif item[0] == "__synced__":
                    _, text = item
                    self.set_push_text(text)
                elif item[0] == "__done__":
                    self.busy = False
                    self.btn_push.config(state="normal")
        except queue.Empty:
            pass
        self.root.after(250, self.drain_log_queue)

    def set_perm(self, name, ok, detail):
        row = self.perm_rows.get(name)
        if not row:
            return
        dot, status = row
        if ok is None:
            dot.config(text="○", fg=DOT_IDLE)
            status.config(text=detail or "-", fg=MUTED)
        else:
            dot.config(text="●", fg=(GREEN if ok else RED))
            status.config(text=detail, fg=(GREEN if ok else RED))

    def append_log(self, line: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line + "\n")
        # 保留最近 300 行
        count = int(self.log_text.index("end-1c").split(".")[0])
        if count > 300:
            self.log_text.delete("1.0", f"{count - 300}.0")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def set_push_text(self, text: str):
        self.push_text.configure(state="normal")
        self.push_text.delete("1.0", "end")
        self.push_text.insert("1.0", text)
        self.push_text.configure(state="disabled")

    # ---------------- actions

    def on_push(self):
        if self.busy:
            return
        self.busy = True
        self.btn_push.config(state="disabled")

        def work():
            try:
                adb_ok = check_adb()
                self.log_queue.put(("__perm__", "ADB", adb_ok, "就绪" if adb_ok else "未找到 adb"))
                devices = get_devices()
                device = devices[0] if devices else ""
                self.log_queue.put(("__perm__", "设备", bool(device), device if device else "未检测到设备"))
                if not device:
                    self.log_queue.put("未检测到设备，请先连接手机并开启 USB 调试")
                    return
                ok, msg = push_and_start(device, self.log_queue.put, on_perm=self.on_perm)
                self.log_queue.put(("__push_result__", ok, msg))
            finally:
                self.log_queue.put(("__done__",))

        threading.Thread(target=work, daemon=True).start()

    def on_perm(self, name, ok, detail):
        self.log_queue.put(("__perm__", name, ok, detail))

    def on_synced(self, text: str):
        self.log_queue.put(("__synced__", text))
        self.log_queue.put(f"{now_text()} - INFO - 已推送文本（{len(text)} 字符）")

    def start_monitoring(self):
        if self._sync_started:
            return
        self._sync_started = True
        self.log("开始 1 秒轮询同步监控 ...")
        start_sync_thread(self.log_queue, adb_path_override=adb_binary(), on_clipboard_synced=self.on_synced)

    def on_close(self):
        self.root.destroy()


def main():
    root = tk.Tk()
    app = App(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


def selftest(outfile: str):
    """命令行自检：把 adb、内置 APK、已连接设备与品牌识别写入文件（便于打包后诊断）。"""
    import json

    devices = get_devices()
    device = devices[0] if devices else ""
    brand = None
    if device:
        try:
            brand = get_brand(device)[1]
        except Exception:
            brand = "识别失败"
    result = {
        "adb": adb_binary(),
        "apk": resource_path(APK_FILE),
        "apk_exists": os.path.exists(resource_path(APK_FILE)),
        "devices": devices,
        "brand": brand,
    }
    with open(outfile, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest(sys.argv[sys.argv.index("--selftest") + 1])
    else:
        main()
