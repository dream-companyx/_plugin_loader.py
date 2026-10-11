# -*- coding: utf-8 -*-
# ============================================================
# DreamyPluginLoader (Bridge)
# ============================================================
# Связующее звено между лаунчером DreamyLauncherMega и плагинами.
#
# ЧТО ЭТО:
#   Этот файл загружает все остальные .py-плагины из папки plugins/
#   и предоставляет им API для работы с лаунчером (версии, события,
#   логирование, доступ к путям и т.д.).
#
# ГДЕ ЛЕЖИТ:
#   <корень_лаунчера>/plugins/_plugin_loader.py
#
# КАК ЭТО РАБОТАЕТ:
#   1. Лаунчер при старте ищет этот файл в plugins/.
#   2. Если файл есть — загружает его как модуль.
#   3. Bridge сканирует соседние .py-файлы (кроме себя).
#   4. Импортирует каждый через importlib.
#   5. Собирает у них get_versions() и вызывает события.
#
# ВНИМАНИЕ:
#   ⚠️ Плагины — это сторонний Python-код. Они имеют ПОЛНЫЙ доступ
#      к файловой системе, сети, subprocess и памяти лаунчера.
#      НЕ загружайте плагины из ненадёжных источников.
#
# API_VERSION: 1.0
# ============================================================

import os
import sys
import json
import importlib.util
import traceback
from pathlib import Path


# ============================================================
# Версия API bridge — лаунчер проверяет её при загрузке
# ============================================================
BRIDGE_API_VERSION = "1.0"
BRIDGE_NAME = "DreamyPluginLoader"
BRIDGE_VERSION = "1.0.0"
BRIDGE_AUTHOR = "DreamyLauncherMega"


# ============================================================
# Внутреннее состояние bridge
# ============================================================
_state = {
    "launcher": None,          # ссылка на окно лаунчера
    "plugins_dir": None,       # Path(plugins/)
    "loaded_plugins": {},      # {module_name: module}
    "enabled_plugins": {},     # {module_name: bool}
    "config_path": None,       # Path(plugins/.enabled.json)
    "log_fn": None,            # функция лаунчера для логов
}


# ============================================================
# Утилита логирования (работает даже без лаунчера)
# ============================================================
def _log(msg: str):
    fn = _state.get("log_fn")
    if callable(fn):
        try:
            fn(f"[Bridge] {msg}")
            return
        except Exception:
            pass
    try:
        print(f"[Bridge] {msg}", flush=True)
    except Exception:
        pass


# ============================================================
# Конфиг .enabled.json
# ============================================================
def _load_enabled():
    cfg = _state.get("config_path")
    if not cfg or not cfg.exists():
        return {}
    try:
        with open(cfg, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception as e:
        _log(f"Не удалось прочитать .enabled.json: {e}")
    return {}


def _save_enabled():
    cfg = _state.get("config_path")
    if not cfg:
        return
    try:
        cfg.parent.mkdir(parents=True, exist_ok=True)
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump(_state["enabled_plugins"], f, ensure_ascii=False, indent=2)
    except Exception as e:
        _log(f"Не удалось записать .enabled.json: {e}")


# ============================================================
# Загрузка одного плагина
# ============================================================
def _load_plugin_file(path: Path):
    name = path.stem
    if name.startswith("_"):
        # Файлы с _ в начале — служебные, не плагины
        return None
    try:
        spec = importlib.util.spec_from_file_location(f"dreamy_plugin_{name}", path)
        if spec is None or spec.loader is None:
            _log(f"Не удалось создать spec для {name}")
            return None
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"dreamy_plugin_{name}"] = module
        spec.loader.exec_module(module)
        return module
    except Exception as e:
        tb = traceback.format_exc()
        _log(f"Ошибка загрузки плагина {name}: {e}\n{tb}")
        return None


# ============================================================
# Публичное API для лаунчера
# ============================================================
def register(launcher):
    """
    Лаунчер вызывает этот метод при старте, передавая себя.
    launcher должен предоставить:
        log(msg)
        get_minecraft_dir() -> str
        get_assets_dir() -> str
        get_script_dir() -> str
        get_current_account() -> dict | None
    """
    _state["launcher"] = launcher

    if hasattr(launcher, "log") and callable(getattr(launcher, "log")):
        _state["log_fn"] = getattr(launcher, "log")

    try:
        plugins_dir = Path(__file__).parent
    except Exception:
        plugins_dir = Path("plugins")
    _state["plugins_dir"] = plugins_dir
    _state["config_path"] = plugins_dir / ".enabled.json"

    _log(f"{BRIDGE_NAME} v{BRIDGE_VERSION} зарегистрирован")
    _log(f"Папка плагинов: {plugins_dir}")

    enabled_cfg = _load_enabled()

    loaded = {}
    enabled = {}
    for p in sorted(plugins_dir.glob("*.py")):
        if p.name == Path(__file__).name:
            continue
        if p.name.startswith("_"):
            continue
        mod = _load_plugin_file(p)
        if mod is None:
            continue
        loaded[p.stem] = mod
        enabled[p.stem] = bool(enabled_cfg.get(p.stem, True))

    _state["loaded_plugins"] = loaded
    _state["enabled_plugins"] = enabled
    _save_enabled()

    _log(f"Загружено плагинов: {len(loaded)}")
    for name in loaded:
        status = "вкл" if enabled.get(name) else "выкл"
        _log(f"  • {name} [{status}]")

    call_event("on_launcher_start")


def is_ready() -> bool:
    """Готов ли bridge к работе."""
    return _state.get("launcher") is not None


def list_plugins():
    """Список плагинов для вкладки «Плагины»."""
    result = []
    for name, mod in _state["loaded_plugins"].items():
        result.append({
            "name": name,
            "file": f"{name}.py",
            "title": getattr(mod, "PLUGIN_NAME", name),
            "author": getattr(mod, "PLUGIN_AUTHOR", "—"),
            "version": getattr(mod, "PLUGIN_VERSION", "—"),
            "description": getattr(mod, "PLUGIN_DESCRIPTION", ""),
            "enabled": bool(_state["enabled_plugins"].get(name, True)),
        })
    return result


def set_plugin_enabled(name: str, enabled: bool):
    """Включить/выключить плагин."""
    if name not in _state["loaded_plugins"]:
        return
    _state["enabled_plugins"][name] = bool(enabled)
    _save_enabled()
    _log(f"Плагин {name}: {'вкл' if enabled else 'выкл'}")


def reload_plugins():
    """Перезагрузить все плагины."""
    if _state["launcher"] is None:
        return
    register(_state["launcher"])


def get_plugin_source(name: str) -> str:
    """Путь к файлу плагина."""
    p = _state["plugins_dir"] / f"{name}.py"
    return str(p) if p.exists() else ""


# ============================================================
# Сбор версий из всех включённых плагинов
# ============================================================
def get_all_versions():
    """
    Возвращает список версий из всех включённых плагинов.
    Формат: [{"id": str, "type": str, "name": str, "plugin": str,
              "plugin_title": str}, ...]
    """
    result = []
    for name, mod in _state["loaded_plugins"].items():
        if not _state["enabled_plugins"].get(name, True):
            continue
        fn = getattr(mod, "get_versions", None)
        if not callable(fn):
            continue
        try:
            versions = fn() or []
            for v in versions:
                if not isinstance(v, dict):
                    continue
                v.setdefault("plugin", name)
                v.setdefault("plugin_title",
                             getattr(mod, "PLUGIN_NAME", name))
                result.append(v)
        except Exception as e:
            tb = traceback.format_exc()
            _log(f"Ошибка get_versions в плагине {name}: {e}\n{tb}")
    return result


def install_version(version_id: str):
    """
    Найти плагин, который умеет ставить эту версию, и вызвать его.
    Возвращает True/False.
    """
    for name, mod in _state["loaded_plugins"].items():
        if not _state["enabled_plugins"].get(name, True):
            continue
        get_fn = getattr(mod, "get_versions", None)
        if not callable(get_fn):
            continue
        try:
            versions = get_fn() or []
        except Exception:
            continue
        match = None
        for v in versions:
            if isinstance(v, dict) and v.get("id") == version_id:
                match = v
                break
        if match is None:
            continue

        install_fn = getattr(mod, "install_version", None)
        if not callable(install_fn):
            _log(f"Плагин {name} не имеет install_version")
            return False

        ctx = PluginContext(name, version_id)
        try:
            result = install_fn(version_id, ctx)
            return bool(result)
        except Exception as e:
            tb = traceback.format_exc()
            _log(f"Ошибка install_version в плагине {name}: {e}\n{tb}")
            return False
    _log(f"Не найден плагин для версии {version_id}")
    return False


# ============================================================
# События
# ============================================================
def call_event(event_name: str, **kwargs):
    """
    Вызвать событие у всех включённых плагинов.
    Плагин может определить функцию с именем события:
        def on_launcher_start(ctx): ...
        def on_game_start(ctx, version_id, mode): ...
    """
    for name, mod in _state["loaded_plugins"].items():
        if not _state["enabled_plugins"].get(name, True):
            continue
        fn = getattr(mod, event_name, None)
        if not callable(fn):
            continue
        ctx = PluginContext(name, kwargs.get("version_id", ""))
        try:
            fn(ctx, **kwargs)
        except Exception as e:
            tb = traceback.format_exc()
            _log(f"Ошибка события {event_name} в плагине {name}: {e}\n{tb}")


# ============================================================
# PluginContext — то, что плагин получает для работы
# ============================================================
class PluginContext:
    """
    Объект, передаваемый плагину.
    Даёт доступ к:
        ctx.log(msg)
        ctx.progress(value, status)
        ctx.minecraft_dir
        ctx.assets_dir
        ctx.script_dir
        ctx.plugin_name
        ctx.version_id
        ctx.current_account()
        ctx.get_setting(key, default)
        ctx.set_setting(key, value)
    """
    def __init__(self, plugin_name: str, version_id: str = ""):
        self.plugin_name = plugin_name
        self.version_id = version_id
        self._progress_fn = None
        self._settings_path = None
        self._settings = {}

        launcher = _state.get("launcher")

        self.minecraft_dir = ""
        self.assets_dir = ""
        self.script_dir = ""
        if launcher is not None:
            try:
                if hasattr(launcher, "get_minecraft_dir"):
                    self.minecraft_dir = launcher.get_minecraft_dir() or ""
                elif hasattr(launcher, "minecraft_dir"):
                    self.minecraft_dir = launcher.minecraft_dir or ""
            except Exception:
                pass
            try:
                if hasattr(launcher, "get_assets_dir"):
                    self.assets_dir = launcher.get_assets_dir() or ""
            except Exception:
                pass
            try:
                if hasattr(launcher, "get_script_dir"):
                    self.script_dir = launcher.get_script_dir() or ""
                elif hasattr(launcher, "script_dir"):
                    self.script_dir = str(launcher.script_dir)
            except Exception:
                pass

        if launcher is not None and hasattr(launcher, "set_plugin_progress"):
            self._progress_fn = getattr(launcher, "set_plugin_progress")

        if _state.get("plugins_dir"):
            self._settings_path = _state["plugins_dir"] / f".{plugin_name}.settings.json"
            self._load_settings()

    def log(self, msg: str):
        _log(f"[{self.plugin_name}] {msg}")

    def progress(self, value: int, status: str = ""):
        if callable(self._progress_fn):
            try:
                self._progress_fn(int(value), status)
                return
            except Exception:
                pass
        _log(f"[{self.plugin_name}] progress {value}% {status}")

    def current_account(self):
        launcher = _state.get("launcher")
        if launcher is None:
            return None
        if hasattr(launcher, "get_current_account"):
            try:
                return launcher.get_current_account()
            except Exception:
                return None
        return None

    def _load_settings(self):
        if self._settings_path and self._settings_path.exists():
            try:
                with open(self._settings_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self._settings = data
            except Exception:
                pass

    def get_setting(self, key: str, default=None):
        return self._settings.get(key, default)

    def set_setting(self, key: str, value):
        self._settings[key] = value
        if self._settings_path:
            try:
                self._settings_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self._settings_path, "w", encoding="utf-8") as f:
                    json.dump(self._settings, f, ensure_ascii=False, indent=2)
            except Exception as e:
                self.log(f"Не удалось сохранить настройки: {e}")


# ============================================================
# Утилита для плагинов: скачивание по URL
# ============================================================
def download_file(url: str, dest_path, progress_ctx=None) -> bool:
    """
    Скачивает файл по URL с поддержкой прогресса.
    progress_ctx — PluginContext (для progress()).
    Возвращает True/False.
    """
    import urllib.request
    try:
        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)

        req = urllib.request.Request(
            url,
            headers={"User-Agent": "DreamyPluginLoader/1.0"}
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            total = int(response.headers.get("Content-Length", 0))
            chunk = 65536
            got = 0
            with open(dest, "wb") as f:
                while True:
                    data = response.read(chunk)
                    if not data:
                        break
                    f.write(data)
                    got += len(data)
                    if progress_ctx and total:
                        pct = int(got * 100 / total)
                        progress_ctx.progress(pct, f"Скачано {got // 1024} КБ")
        return True
    except Exception as e:
        _log(f"download_file error: {e}")
        return False
