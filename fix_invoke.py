import os

# fix ui_manager.py
with open('ui/ui_manager.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(
    'QMetaObject.invokeMethod(self.explorer_window, "refresh", Qt.ConnectionType.QueuedConnection)',
    'QTimer.singleShot(0, self.explorer_window.refresh)'
)

if 'QTimer' not in content:
    content = 'from PyQt6.QtCore import QTimer\n' + content

with open('ui/ui_manager.py', 'w', encoding='utf-8') as f:
    f.write(content)

# fix settings_window.py
with open('ui/settings_window.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(
    'QMetaObject.invokeMethod(self, "_on_ping_success", Qt.ConnectionType.QueuedConnection)',
    'QTimer.singleShot(0, self._on_ping_success)'
)

content = content.replace(
    'QMetaObject.invokeMethod(self, "_on_ping_failed", Qt.ConnectionType.QueuedConnection)',
    'QTimer.singleShot(0, self._on_ping_failed)'
)

if 'QTimer' not in content:
    content = 'from PyQt6.QtCore import QTimer\n' + content

with open('ui/settings_window.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')
