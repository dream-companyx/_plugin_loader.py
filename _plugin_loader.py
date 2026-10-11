# Загрузка bridge
import importlib.util
spec = importlib.util.spec_from_file_location(
    "dreamy_plugin_loader",
    plugins_dir / "_plugin_loader.py"
)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

# Проверка версии
assert bridge.BRIDGE_API_VERSION == "1.0"

# Регистрация
bridge.register(self)   # self — окно лаунчера

# Получить версии для комбобокса
versions = bridge.get_all_versions()
# → [{"id": "...", "type": "...", "name": "...", "plugin": "..."}, ...]

# Установить версию
ok = bridge.install_version("example-test-1.0")

# События
bridge.call_event("on_game_start", version_id=vid, mode=mode)
bridge.call_event("on_game_exit", version_id=vid, code=rc, is_crash=crash)

# Список плагинов для вкладки
plugins = bridge.list_plugins()

# Включить/выключить
bridge.set_plugin_enabled("my_plugin", False)