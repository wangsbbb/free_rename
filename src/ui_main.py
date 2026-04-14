from __future__ import annotations

import os
import sys
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QAbstractTableModel, QFile, QModelIndex, QIODevice, QSettings, QSize, QStandardPaths, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QDragEnterEvent, QDropEvent, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QRadioButton,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QStyle,
    QTableView,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from file_manager import FileManager
from rule_engine import FileItem, PreviewRow, PreviewSummary, RuleConfig, RuleEngine
from workers import PreviewWorker, RenameWorker, ScanWorker

try:
    import resources_rc  # type: ignore  # noqa: F401
except Exception:
    resources_rc = None

APP_NAME = "free_rename"
APP_VERSION = "1.0.14"
APP_TITLE = APP_NAME
PROJECT_URL = ""
PREVIEW_DEBOUNCE_MS = 350
SETTINGS_ORG = "free_rename"
SETTINGS_APP = "free_rename"


def resource_path(relative_path: str) -> str:
    base_path = getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)
    return str(Path(base_path) / relative_path)


def qrc_asset_path(name: str) -> str:
    return f":/assets/icons/{name}"


def qrc_style_path(theme: str) -> str:
    return f":/styles/{theme}.qss"


def find_asset(candidates: list[str]) -> Optional[Path]:
    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    search_roots = [
        base_path / "assets" / "icons",
        base_path / "assets",
        base_path,
    ]
    for name in candidates:
        for root in search_roots:
            path = root / name
            if path.exists():
                return path
    return None


def read_qt_resource_text(path: str) -> Optional[str]:
    file = QFile(path)
    if not file.exists():
        return None
    if not file.open(QIODevice.OpenModeFlag.ReadOnly | QIODevice.OpenModeFlag.Text):
        return None
    try:
        data = bytes(file.readAll())
    finally:
        file.close()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="ignore")

class DropTable(QTableView):
    filesDropped = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setDragDropOverwriteMode(False)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        paths: list[str] = []
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                local = url.toLocalFile()
                if local:
                    paths.append(local)
        if paths:
            self.filesDropped.emit(paths)
            event.acceptProposedAction()
        else:
            event.ignore()


class PreviewTableModel(QAbstractTableModel):
    headers = ["原文件名", "预览新文件名", "状态", "扩展名", "所在目录"]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._rows: list[PreviewRow] = []
        self._target_map: dict[str, int] = {}

    def update_data(self, rows: list[PreviewRow], target_map: dict[str, int]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self._target_map = dict(target_map)
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self.headers)

    def _display_state(self, row: PreviewRow) -> str:
        if row.new_name and self._target_map.get(str(row.item.folder / row.new_name).lower(), 0) > 1:
            return "重名冲突"
        return row.state

    def data(self, index: QModelIndex, role: int = int(Qt.ItemDataRole.DisplayRole)):
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None
        row = self._rows[index.row()]
        state = self._display_state(row)
        values = [row.item.name, row.new_name or "-", state, row.ext, row.folder]

        if role == int(Qt.ItemDataRole.DisplayRole):
            return values[index.column()]

        if role == int(Qt.ItemDataRole.BackgroundRole):
            if state == "重名冲突":
                return QColor("#fee2e2")
            if state.startswith("错误"):
                return QColor("#ffedd5")
            if state == "跳过":
                return QColor("#f3f4f6")

        if role == int(Qt.ItemDataRole.ToolTipRole):
            return values[index.column()]

        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = int(Qt.ItemDataRole.DisplayRole)):
        if role != int(Qt.ItemDataRole.DisplayRole):
            return None
        if orientation == Qt.Orientation.Horizontal and 0 <= section < len(self.headers):
            return self.headers[section]
        return super().headerData(section, orientation, role)


class SidebarButton(QPushButton):
    def __init__(self, text: str, icon: QIcon) -> None:
        super().__init__(text)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(44)
        self.setIcon(icon)
        self.setIconSize(QSize(16, 16))
        self.setObjectName("NavButton")


class HeaderIconButton(QToolButton):
    def __init__(self, icon: Optional[QIcon] = None) -> None:
        super().__init__()
        self.setCursor(Qt.PointingHandCursor)
        self.setAutoRaise(True)
        self.setFixedSize(38, 38)
        self.setObjectName("HeaderIconButton")
        if icon is not None:
            self.setIcon(icon)
            self.setIconSize(QSize(18, 18))


class StatCard(QFrame):
    def __init__(self, title: str, value: str, accent: str) -> None:
        super().__init__()
        self.setObjectName("StatCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("MutedLabel")
        self.value_label = QLabel(value)
        self.value_label.setObjectName("StatValue")
        self.bar = QFrame()
        self.bar.setFixedHeight(4)
        self.bar.setStyleSheet(f"background:{accent}; border:none; border-radius:2px;")
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.bar)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)


def build_embedded_stylesheet(theme: str) -> str:
    if theme == "dark":
        bg = "#0f172a"
        panel = "#111827"
        card = "#172033"
        soft = "#1f2937"
        text = "#e5e7eb"
        sub = "#94a3b8"
        border = "#2a3447"
        accent = "#3b82f6"
        accent_hover = "#2563eb"
        table_alt = "#132033"
    else:
        bg = "#f3f5f9"
        panel = "#eef2f7"
        card = "#ffffff"
        soft = "#f8fafc"
        text = "#111827"
        sub = "#6b7280"
        border = "#d9e1ea"
        accent = "#3b82f6"
        accent_hover = "#2563eb"
        table_alt = "#f8fbff"

    return f"""
    QMainWindow {{
        background: {bg};
    }}
    QWidget {{
        color: {text};
        font-family: 'Microsoft YaHei UI', 'Segoe UI', sans-serif;
        font-size: 13px;
    }}
    QLabel, QCheckBox, QRadioButton, QGroupBox {{
        background: transparent;
    }}
    QFrame#Sidebar {{
        background: {panel};
        border-right: 1px solid {border};
    }}
    QLabel#BrandLabel {{
        font-size: 24px;
        font-weight: 700;
        color: {text};
        padding: 6px 4px 12px 4px;
    }}
    QLabel#SidebarHint {{
        color: {sub};
        line-height: 1.5;
        padding: 8px 6px 4px 6px;
        font-size: 12px;
    }}
    QPushButton {{
        background: {soft};
        border: 1px solid {border};
        border-radius: 12px;
        padding: 10px 14px;
        color: {text};
    }}
    QPushButton:hover {{
        border-color: {accent};
        background: {'#ffffff' if theme == 'light' else '#1c2436'};
    }}
    QPushButton#NavButton {{
        text-align: left;
        padding: 10px 12px;
        padding-left: 14px;
        background: {soft};
    }}
    QPushButton#NavButton:hover {{
        border-color: {accent};
        background: {soft};
    }}
    QPushButton#NavButton:checked {{
        background: rgba(59,130,246,0.12);
        border-color: rgba(59,130,246,0.28);
        font-weight: 700;
    }}
    QToolButton#HeaderIconButton, QToolButton#GithubButton {{
        background: {soft};
        border: 1px solid {border};
        border-radius: 16px;
        padding: 8px;
    }}
    QToolButton#HeaderIconButton:hover, QToolButton#GithubButton:hover {{
        border-color: {accent};
        background: {'#ffffff' if theme == 'light' else '#1c2436'};
    }}
    QPushButton:pressed {{
        background: {accent};
        color: white;
    }}
    QPushButton#PrimaryButton {{
        background: {accent};
        color: white;
        font-weight: 700;
        border-color: {accent};
    }}
    QPushButton#PrimaryButton:hover {{
        background: {accent_hover};
        border-color: {accent_hover};
    }}
    SidebarButton, QPushButton:checked {{
        background: rgba(59,130,246,0.14);
        border-color: rgba(59,130,246,0.28);
    }}
    QLabel#PageTitle {{
        font-size: 28px;
        font-weight: 700;
        color: {text};
    }}
    QLabel#SubTitle, QLabel#MutedLabel {{
        color: {sub};
    }}
    QLabel#CardTitle {{
        font-size: 18px;
        font-weight: 700;
    }}
    QLabel#StatValue {{
        font-size: 26px;
        font-weight: 700;
    }}
    QFrame#TopBar, QFrame#Card, QFrame#StatCard, QFrame#InnerCard {{
        background: {card};
        border: 1px solid {border};
        border-radius: 18px;
    }}
    QGroupBox#Group {{
        background: {card};
        border: 1px solid {border};
        border-radius: 16px;
        margin-top: 10px;
        padding-top: 14px;
        font-weight: 700;
    }}
    QGroupBox#Group::title {{
        subcontrol-origin: margin;
        left: 14px;
        padding: 0 6px;
        color: {text};
    }}
    QLineEdit, QComboBox {{
        background: {soft};
        border: 1px solid {border};
        border-radius: 12px;
        padding: 9px 12px;
        min-height: 20px;
        color: {text};
    }}
    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 28px;
        border: none;
        background: transparent;
    }}
    QComboBox QAbstractItemView {{
        background: {card};
        color: {text};
        border: 1px solid {border};
        selection-background-color: rgba(59,130,246,0.28);
        selection-color: {'#ffffff' if theme == 'dark' else text};
        outline: 0;
    }}
    QComboBox QAbstractItemView::item {{
        min-height: 28px;
        padding: 6px 10px;
    }}
    QComboBox QAbstractItemView::item:hover {{
        background: rgba(59,130,246,0.16);
        color: {'#ffffff' if theme == 'dark' else text};
    }}
    QTextEdit, QListWidget {{
        background: {card};
        border: 1px solid {border};
        border-radius: 12px;
    }}
    QLineEdit:focus, QComboBox:focus, QTextEdit:focus {{
        border-color: {accent};
    }}
    QTabWidget::pane {{
        padding: 8px;
        margin-top: 8px;
        background: transparent;
        border: none;
    }}
    QTabBar::tab {{
        background: transparent;
        color: {sub};
        border: 1px solid transparent;
        border-radius: 12px;
        padding: 10px 16px;
        margin-right: 6px;
    }}
    QTabBar::tab:selected {{
        background: rgba(59,130,246,0.12);
        color: {accent};
        border-color: rgba(59,130,246,0.24);
        font-weight: 700;
    }}
    QHeaderView::section {{
        background: {soft};
        color: {text};
        padding: 10px;
        border: none;
        border-bottom: 1px solid {border};
        font-weight: 700;
    }}
    QTableWidget, QTableView {{
        background: {card};
        alternate-background-color: {table_alt};
        border: 1px solid {border};
        border-radius: 14px;
        gridline-color: {border};
    }}
    QTableWidget::item, QTableView::item {{
        padding: 8px;
    }}
    QTableWidget::item:selected, QTableView::item:selected {{
        background: rgba(59,130,246,0.16);
        color: {text};
    }}
    QStatusBar {{
        background: {panel};
        border-top: 1px solid {border};
    }}
    QRadioButton, QCheckBox {{
        spacing: 8px;
    }}
    """


def load_stylesheet(theme: str) -> str:
    qrc_text = read_qt_resource_text(qrc_style_path(theme))
    if qrc_text:
        return qrc_text
    style_path = Path(resource_path(f"styles/{theme}.qss"))
    try:
        if style_path.exists():
            return style_path.read_text(encoding="utf-8")
    except Exception:
        pass
    return build_embedded_stylesheet(theme)


class RenamerWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.files: list[FileItem] = []
        self.preview_rows: list[PreviewRow] = []
        self.preview_summary = PreviewSummary(0, 0, 0, 0, 0)
        self.preview_target_map: dict[str, int] = {}
        self.history: list[str] = []
        self.current_theme = "light"
        self.settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        self.history_file = self._history_file_path()
        self.preview_model = PreviewTableModel(self)
        self._table_columns_initialized = False
        self.last_dir = self.settings.value("paths/last_dir", str(Path.home()), type=str) or str(Path.home())
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(PREVIEW_DEBOUNCE_MS)
        self.preview_timer.timeout.connect(self._refresh_preview_debounced)
        self._signals_bound = False
        self._preview_dirty = False
        self._preview_pending = False
        self._preview_pending_show_errors = False
        self._preview_thread: Optional[QThread] = None
        self._preview_worker: Optional[PreviewWorker] = None
        self._scan_thread: Optional[QThread] = None
        self._scan_worker: Optional[ScanWorker] = None
        self._execute_thread: Optional[QThread] = None
        self._execute_worker: Optional[RenameWorker] = None
        self._cancel_requested = False
        self._build_window()
        self._load_history()
        self._restore_ui_settings()
        self._apply_icon()
        self.refresh_preview(show_errors=False)

    def _std_icon(self, which: QStyle.StandardPixmap) -> QIcon:
        return self.style().standardIcon(which)

    def _asset_icon(self, names: list[str], fallback: QStyle.StandardPixmap) -> QIcon:
        for name in names:
            icon = QIcon(qrc_asset_path(name))
            if not icon.isNull():
                return icon
        asset = find_asset(names)
        if asset is not None:
            suffix = asset.suffix.lower()
            if suffix in {".png", ".ico", ".jpg", ".jpeg", ".bmp", ".webp"}:
                pixmap = QPixmap(str(asset))
                if not pixmap.isNull():
                    return QIcon(pixmap)
            icon = QIcon(str(asset))
            if not icon.isNull():
                return icon
        return self._std_icon(fallback)

    def _open_project_url(self) -> None:
        if not PROJECT_URL.strip():
            QMessageBox.information(self, APP_TITLE, "请先在 free_rename.py 中把 PROJECT_URL 改成你的 GitHub 仓库地址。")
            return
        QDesktopServices.openUrl(QUrl(PROJECT_URL))

    def _app_data_dir(self) -> Path:
        raw = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        base = Path(raw) if raw else (Path.home() / f'.{APP_NAME}')
        base.mkdir(parents=True, exist_ok=True)
        return base

    def _history_file_path(self) -> Path:
        return self._app_data_dir() / 'history.log'


    def _history_timestamp(self) -> str:
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    def _load_history(self) -> None:
        try:
            if self.history_file.exists():
                with self.history_file.open('r', encoding='utf-8', errors='ignore') as f:
                    self.history = [line.rstrip('\n') for line in deque((line for line in f if line.strip()), maxlen=500)]
            else:
                self.history = []
        except Exception:
            self.history = []
        self._refresh_history_panel()

    def _add_history(self, message: str, refresh: bool = True) -> None:
        entry = f'[{self._history_timestamp()}] {message}'
        self.history.append(entry)
        self.history = self.history[-500:]
        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            with self.history_file.open('a', encoding='utf-8') as f:
                f.write(entry + '\n')
        except Exception:
            pass
        if refresh:
            self._refresh_history_panel()


    def _restore_ui_settings(self) -> None:
        theme = self.settings.value("ui/theme", "light", type=str) or "light"
        self.current_theme = theme
        self._setup_stylesheet(theme)
        self.theme_combo.blockSignals(True)
        self.theme_combo.setCurrentText("深色" if theme == "dark" else "浅色")
        self.theme_combo.blockSignals(False)

        geometry = self.settings.value("ui/geometry")
        if geometry:
            self.restoreGeometry(geometry)

        self.base_name_edit.setText(self.settings.value("rules/base_name", "", type=str) or "")
        self.start_num_edit.setText(self.settings.value("rules/start_num", "1", type=str) or "1")
        self.step_edit.setText(self.settings.value("rules/step", "1", type=str) or "1")
        self.digits_combo.setCurrentText(self.settings.value("rules/digits", "1", type=str) or "1")
        self.position_combo.setCurrentText(self.settings.value("rules/position", "后面", type=str) or "后面")
        self.sep_edit.setText(self.settings.value("rules/separator", "", type=str) or "")
        self.keep_ext_check.setChecked(self.settings.value("rules/keep_ext", True, type=bool))
        self.sort_mode_combo.setCurrentText(self.settings.value("rules/sort_mode", "当前顺序", type=str) or "当前顺序")
        self.sort_reverse_check.setChecked(self.settings.value("rules/sort_reverse", False, type=bool))

        self.insert_enabled.setChecked(self.settings.value("rules/insert_enabled", False, type=bool))
        self.insert_text_edit.setText(self.settings.value("rules/insert_text", "", type=str) or "")
        self.insert_mode_combo.setCurrentText(self.settings.value("rules/insert_mode", "前面", type=str) or "前面")
        self.insert_index_edit.setText(self.settings.value("rules/insert_index", "1", type=str) or "1")

        self.replace_enabled.setChecked(self.settings.value("rules/replace_enabled", False, type=bool))
        self.replace_find_edit.setText(self.settings.value("rules/replace_find", "", type=str) or "")
        self.replace_to_edit.setText(self.settings.value("rules/replace_to", "", type=str) or "")
        self.replace_case_check.setChecked(self.settings.value("rules/replace_case", False, type=bool))
        self.replace_first_only_check.setChecked(self.settings.value("rules/replace_first_only", False, type=bool))

        self.delete_enabled.setChecked(self.settings.value("rules/delete_enabled", False, type=bool))
        self.delete_mode_combo.setCurrentText(self.settings.value("rules/delete_mode", "删除文本", type=str) or "删除文本")
        self.delete_text_edit.setText(self.settings.value("rules/delete_text", "", type=str) or "")
        self.delete_start_edit.setText(self.settings.value("rules/delete_start", "1", type=str) or "1")
        self.delete_len_edit.setText(self.settings.value("rules/delete_length", "1", type=str) or "1")
        self.delete_prefix_count_edit.setText(self.settings.value("rules/delete_prefix_count", "1", type=str) or "1")
        self.delete_suffix_count_edit.setText(self.settings.value("rules/delete_suffix_count", "1", type=str) or "1")

        self.regex_enabled.setChecked(self.settings.value("rules/regex_enabled", False, type=bool))
        self.regex_pattern_edit.setText(self.settings.value("rules/regex_pattern", "", type=str) or "")
        self.regex_replace_edit.setText(self.settings.value("rules/regex_replace", "", type=str) or "")
        self.regex_ignore_case_check.setChecked(self.settings.value("rules/regex_ignore_case", False, type=bool))

        self.filter_enabled.setChecked(self.settings.value("rules/filter_enabled", False, type=bool))
        self.filter_ext_edit.setText(self.settings.value("rules/filter_ext_text", "", type=str) or "")
        self.filter_mode_combo.setCurrentText(self.settings.value("rules/filter_mode", "仅处理这些扩展名", type=str) or "仅处理这些扩展名")

        current_page = self.settings.value("ui/current_page", 0, type=int)
        current_tab = self.settings.value("ui/current_tab", 0, type=int)
        if 0 <= current_page < self.stack.count():
            self._switch_page(current_page)
        if 0 <= current_tab < self.tabs.count():
            self.tabs.setCurrentIndex(current_tab)

        splitter_state = self.settings.value("ui/main_splitter_state")
        if splitter_state:
            self.main_splitter.restoreState(splitter_state)

        header_state = self.settings.value("ui/table_header_state")
        if header_state:
            self.table.horizontalHeader().restoreState(header_state)
            self._table_columns_initialized = True

    def _save_ui_settings(self) -> None:
        self.settings.setValue("ui/theme", self.current_theme)
        self.settings.setValue("ui/geometry", self.saveGeometry())
        self.settings.setValue("paths/last_dir", self.last_dir)

        self.settings.setValue("rules/base_name", self.base_name_edit.text())
        self.settings.setValue("rules/start_num", self.start_num_edit.text())
        self.settings.setValue("rules/step", self.step_edit.text())
        self.settings.setValue("rules/digits", self.digits_combo.currentText())
        self.settings.setValue("rules/position", self.position_combo.currentText())
        self.settings.setValue("rules/separator", self.sep_edit.text())
        self.settings.setValue("rules/keep_ext", self.keep_ext_check.isChecked())
        self.settings.setValue("rules/sort_mode", self.sort_mode_combo.currentText())
        self.settings.setValue("rules/sort_reverse", self.sort_reverse_check.isChecked())

        self.settings.setValue("rules/insert_enabled", self.insert_enabled.isChecked())
        self.settings.setValue("rules/insert_text", self.insert_text_edit.text())
        self.settings.setValue("rules/insert_mode", self.insert_mode_combo.currentText())
        self.settings.setValue("rules/insert_index", self.insert_index_edit.text())

        self.settings.setValue("rules/replace_enabled", self.replace_enabled.isChecked())
        self.settings.setValue("rules/replace_find", self.replace_find_edit.text())
        self.settings.setValue("rules/replace_to", self.replace_to_edit.text())
        self.settings.setValue("rules/replace_case", self.replace_case_check.isChecked())
        self.settings.setValue("rules/replace_first_only", self.replace_first_only_check.isChecked())

        self.settings.setValue("rules/delete_enabled", self.delete_enabled.isChecked())
        self.settings.setValue("rules/delete_mode", self.delete_mode_combo.currentText())
        self.settings.setValue("rules/delete_text", self.delete_text_edit.text())
        self.settings.setValue("rules/delete_start", self.delete_start_edit.text())
        self.settings.setValue("rules/delete_length", self.delete_len_edit.text())
        self.settings.setValue("rules/delete_prefix_count", self.delete_prefix_count_edit.text())
        self.settings.setValue("rules/delete_suffix_count", self.delete_suffix_count_edit.text())

        self.settings.setValue("rules/regex_enabled", self.regex_enabled.isChecked())
        self.settings.setValue("rules/regex_pattern", self.regex_pattern_edit.text())
        self.settings.setValue("rules/regex_replace", self.regex_replace_edit.text())
        self.settings.setValue("rules/regex_ignore_case", self.regex_ignore_case_check.isChecked())

        self.settings.setValue("rules/filter_enabled", self.filter_enabled.isChecked())
        self.settings.setValue("rules/filter_ext_text", self.filter_ext_edit.text())
        self.settings.setValue("rules/filter_mode", self.filter_mode_combo.currentText())

        self.settings.setValue("ui/current_page", self.stack.currentIndex())
        self.settings.setValue("ui/current_tab", self.tabs.currentIndex())
        self.settings.setValue("ui/main_splitter_state", self.main_splitter.saveState())
        self.settings.setValue("ui/table_header_state", self.table.horizontalHeader().saveState())
    def closeEvent(self, event) -> None:
        if self._execute_thread is not None or self._scan_thread is not None or self._preview_thread is not None:
            QMessageBox.information(self, APP_TITLE, "当前仍有后台任务在运行，可先点击“取消任务”，待任务结束后再关闭窗口。")
            event.ignore()
            return
        self._save_ui_settings()
        super().closeEvent(event)

    def _normalize_dir(self, raw_path: str) -> str:
        if not raw_path:
            return str(Path.home())
        path = Path(raw_path)
        if path.is_file():
            path = path.parent
        return str(path if path.exists() else Path.home())

    def _dialog_start_dir(self) -> str:
        return self._normalize_dir(self.last_dir)

    def _remember_path(self, raw_path: str) -> None:
        self.last_dir = self._normalize_dir(raw_path)
        self.settings.setValue("paths/last_dir", self.last_dir)

    def _build_window(self) -> None:
        self.setWindowTitle(f"{APP_TITLE} V{APP_VERSION}")
        self.setWindowFilePath(APP_TITLE)
        self.resize(1480, 920)
        self.setMinimumSize(1240, 780)

        root = QWidget()
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.sidebar = self._build_sidebar()
        outer.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)

        self.page_home = self._build_home_page()
        self.page_renamer = self._build_renamer_page()
        self.page_history = self._build_history_page()
        self.page_settings = self._build_settings_page()

        self.stack.addWidget(self.page_home)
        self.stack.addWidget(self.page_renamer)
        self.stack.addWidget(self.page_history)
        self.stack.addWidget(self.page_settings)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("准备就绪")

    def _build_sidebar(self) -> QWidget:
        box = QFrame()
        box.setObjectName("Sidebar")
        box.setFixedWidth(208)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        brand = QLabel(APP_TITLE)
        brand.setObjectName("BrandLabel")
        layout.addWidget(brand)
        layout.addSpacing(10)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        items = [
            ("首页", self._asset_icon(["home.png", "home.svg", "icons8-首页.svg"], QStyle.SP_DirHomeIcon)),
            ("批量重命名", self._asset_icon(["rename.png", "icons8-重命名-30.png"], QStyle.SP_FileDialogDetailedView)),
            ("历史记录", self._asset_icon(["history.png", "icons8-历史-50.png"], QStyle.SP_BrowserReload)),
            ("设置", self._asset_icon(["settings.png", "settings.svg", "icons8-设置.svg"], QStyle.SP_FileDialogContentsView)),
        ]
        self.nav_buttons: list[SidebarButton] = []
        for idx, (label, nav_icon) in enumerate(items):
            btn = SidebarButton(label, nav_icon)
            btn.clicked.connect(lambda checked=False, i=idx: self._switch_page(i))
            self.nav_group.addButton(btn, idx)
            layout.addWidget(btn)
            self.nav_buttons.append(btn)
        if self.nav_buttons:
            self.nav_buttons[0].setChecked(True)

        layout.addStretch(1)
        hint = QLabel(f"版本 V{APP_VERSION}")
        hint.setObjectName("SidebarHint")
        layout.addWidget(hint)
        return box

    def _make_page_shell(self, title: str, subtitle: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(24, 20, 24, 24)
        page_layout.setSpacing(18)

        header = QFrame()
        header.setObjectName("TopBar")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 14, 18, 14)
        header_layout.setSpacing(10)
        texts = QVBoxLayout()
        title_label = QLabel(title)
        title_label.setObjectName("PageTitle")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("SubTitle")
        texts.addWidget(title_label)
        texts.addWidget(subtitle_label)
        header_layout.addLayout(texts)
        header_layout.addStretch(1)

        gh_btn = HeaderIconButton(self._asset_icon(["github_mark_blackcat.png", "github.png", "github.svg", "github_mark_blackcat.svg"], QStyle.SP_CommandLink))
        gh_btn.setObjectName("GithubButton")
        gh_btn.setToolTip("打开 GitHub 项目")
        gh_btn.clicked.connect(self._open_project_url)
        header_layout.addWidget(gh_btn)

        page_layout.addWidget(header)
        return page, page_layout

    def _build_home_page(self) -> QWidget:
        page, layout = self._make_page_shell("首页", "一款开源的批量重命名软件，轻量，便捷，持续优化更新中")

        stats_row = QHBoxLayout()
        stats_row.setSpacing(16)
        self.card_total = StatCard("文件总数", "0", "#3b82f6")
        self.card_ready = StatCard("可处理", "0", "#22c55e")
        self.card_dup = StatCard("重名冲突", "0", "#ef4444")
        self.card_err = StatCard("错误 / 跳过", "0", "#f59e0b")
        for card in [self.card_total, self.card_ready, self.card_dup, self.card_err]:
            stats_row.addWidget(card)
        layout.addLayout(stats_row)

        panel_row = QHBoxLayout()
        panel_row.setSpacing(16)

        quick = QFrame()
        quick.setObjectName("Card")
        ql = QVBoxLayout(quick)
        ql.setContentsMargins(20, 18, 20, 18)
        ql.setSpacing(12)
        qt = QLabel("快速操作")
        qt.setObjectName("CardTitle")
        ql.addWidget(qt)
        self.home_action_buttons: list[QPushButton] = []
        for text, cb in [
            ("➕ 添加文件", self.add_files),
            ("📁 添加文件夹", self.add_folder),
            ("🔁 递归添加", self.add_folder_recursive),
            ("🚀 转到批量重命名", lambda: self._switch_page(1)),
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(cb)
            ql.addWidget(btn)
            if text != "🚀 转到批量重命名":
                self.home_action_buttons.append(btn)
        ql.addStretch(1)

        info = QFrame()
        info.setObjectName("Card")
        il = QVBoxLayout(info)
        il.setContentsMargins(20, 18, 20, 18)
        il.setSpacing(10)
        it = QLabel("当前工作区")
        it.setObjectName("CardTitle")
        self.home_info = QTextEdit()
        self.home_info.setReadOnly(True)
        self.home_info.setMinimumHeight(220)
        self.home_info.setPlainText("还没有导入文件。\n\n你可以从左侧工作区进入‘批量重命名’，也可以在这里先快速添加文件。")
        il.addWidget(it)
        il.addWidget(self.home_info)

        panel_row.addWidget(quick, 1)
        panel_row.addWidget(info, 2)
        layout.addLayout(panel_row)
        layout.addStretch(1)
        return page

    def _build_renamer_page(self) -> QWidget:
        page, layout = self._make_page_shell("free_rename", "左侧文件清单 + 右侧规则中心，整体风格统一。")

        splitter = QSplitter(Qt.Horizontal)
        self.main_splitter = splitter
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(8)
        layout.addWidget(splitter, 1)

        left = QFrame()
        left.setObjectName("Card")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(16, 16, 16, 16)
        left_layout.setSpacing(14)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        self.file_action_buttons: list[QPushButton] = []
        self.add_files_btn = QPushButton("➕ 添加文件")
        self.add_files_btn.clicked.connect(self.add_files)
        self.file_action_buttons.append(self.add_files_btn)
        toolbar.addWidget(self.add_files_btn)

        self.add_folder_btn = QPushButton("📁 文件夹")
        self.add_folder_btn.clicked.connect(self.add_folder)
        self.file_action_buttons.append(self.add_folder_btn)
        toolbar.addWidget(self.add_folder_btn)

        self.add_recursive_btn = QPushButton("🔁 递归")
        self.add_recursive_btn.clicked.connect(self.add_folder_recursive)
        self.file_action_buttons.append(self.add_recursive_btn)
        toolbar.addWidget(self.add_recursive_btn)

        self.remove_btn = QPushButton("🗑 移除")
        self.remove_btn.clicked.connect(self.remove_selected)
        self.file_action_buttons.append(self.remove_btn)
        toolbar.addWidget(self.remove_btn)

        self.clear_btn = QPushButton("🧹 清空")
        self.clear_btn.clicked.connect(self.clear_files)
        self.file_action_buttons.append(self.clear_btn)
        toolbar.addWidget(self.clear_btn)

        self.move_up_btn = QPushButton("⬆ 上移")
        self.move_up_btn.clicked.connect(lambda: self.move_selected(-1))
        self.file_action_buttons.append(self.move_up_btn)
        toolbar.addWidget(self.move_up_btn)

        self.move_down_btn = QPushButton("⬇ 下移")
        self.move_down_btn.clicked.connect(lambda: self.move_selected(1))
        self.file_action_buttons.append(self.move_down_btn)
        toolbar.addWidget(self.move_down_btn)

        toolbar.addStretch(1)
        left_layout.addLayout(toolbar)

        self.table = DropTable()
        self.table.filesDropped.connect(self.on_files_dropped)
        self.table.setModel(self.preview_model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(False)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.setMinimumWidth(620)
        left_layout.addWidget(self.table, 1)

        bottom = QHBoxLayout()
        self.file_count_label = QLabel("0 个文件")
        self.drag_hint = QLabel("支持拖拽导入文件或文件夹")
        self.drag_hint.setObjectName("MutedLabel")
        bottom.addWidget(self.file_count_label)
        bottom.addStretch(1)
        bottom.addWidget(self.drag_hint)
        left_layout.addLayout(bottom)

        right_host = QFrame()
        right_host.setObjectName("Card")
        right_layout = QVBoxLayout(right_host)
        right_layout.setContentsMargins(16, 16, 16, 16)
        right_layout.setSpacing(14)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._tab_numbering(), "统一命名")
        self.tabs.addTab(self._tab_insert(), "插入")
        self.tabs.addTab(self._tab_replace(), "替换")
        self.tabs.addTab(self._tab_delete(), "删除")
        self.tabs.addTab(self._tab_regex(), "正则")
        self.tabs.addTab(self._tab_filter(), "筛选")
        right_layout.addWidget(self.tabs, 1)
        right_layout.addWidget(self._build_execute_box())

        splitter.addWidget(left)
        splitter.addWidget(right_host)
        splitter.setSizes([840, 560])
        return page

    def _build_history_page(self) -> QWidget:
        page, layout = self._make_page_shell("历史记录", "记录最近执行结果与失败原因。")
        card = QFrame()
        card.setObjectName("Card")
        box = QVBoxLayout(card)
        box.setContentsMargins(20, 18, 20, 18)
        box.setSpacing(12)

        top = QHBoxLayout()
        title = QLabel("最近操作")
        title.setObjectName("CardTitle")
        self.history_meta_label = QLabel("0 条记录")
        self.history_meta_label.setObjectName("MutedLabel")
        top.addWidget(title)
        top.addStretch(1)
        top.addWidget(self.history_meta_label)

        tools = QHBoxLayout()
        self.history_search_edit = QLineEdit()
        self.history_search_edit.setPlaceholderText("搜索历史记录…")
        self.history_search_edit.textChanged.connect(self._refresh_history_panel)
        self.history_open_btn = QPushButton("打开日志位置")
        self.history_open_btn.clicked.connect(self._open_history_location)
        self.history_export_btn = QPushButton("导出历史")
        self.history_export_btn.clicked.connect(self._export_history)
        self.history_clear_btn = QPushButton("清空历史")
        self.history_clear_btn.clicked.connect(self._clear_history)
        tools.addWidget(self.history_search_edit, 1)
        tools.addWidget(self.history_open_btn)
        tools.addWidget(self.history_export_btn)
        tools.addWidget(self.history_clear_btn)

        self.history_list = QListWidget()
        self.history_list.setAlternatingRowColors(True)
        box.addLayout(top)
        box.addLayout(tools)
        box.addWidget(self.history_list)
        layout.addWidget(card, 1)
        return page

    def _open_history_location(self) -> None:
        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.history_file.parent)))

    def _export_history(self) -> None:
        default_path = str(Path(self._dialog_start_dir()) / 'free_rename_history.txt')
        save_path, _ = QFileDialog.getSaveFileName(self, '导出历史记录', default_path, 'Text Files (*.txt)')
        if not save_path:
            return
        self._remember_path(save_path)
        try:
            Path(save_path).write_text('\n'.join(self.history), encoding='utf-8')
            QMessageBox.information(self, APP_TITLE, '历史记录导出完成。')
            self._add_history(f'导出历史：{save_path}')
        except Exception as exc:
            QMessageBox.critical(self, APP_TITLE, f'导出历史失败：{exc}')

    def _clear_history(self) -> None:
        if not self.history:
            QMessageBox.information(self, APP_TITLE, '当前没有可清空的历史记录。')
            return
        if QMessageBox.question(self, APP_TITLE, '确认清空本地历史记录吗？') != QMessageBox.Yes:
            return
        self.history.clear()
        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            self.history_file.write_text('', encoding='utf-8')
        except Exception:
            pass
        self._refresh_history_panel()
        self.status.showMessage('历史记录已清空')

    def _build_settings_page(self) -> QWidget:
        page, layout = self._make_page_shell("设置", "主题、显示与基础偏好。")
        card = QFrame()
        card.setObjectName("Card")
        box = QVBoxLayout(card)
        box.setContentsMargins(20, 18, 20, 18)
        box.setSpacing(16)
        title = QLabel("界面外观")
        title.setObjectName("CardTitle")
        box.addWidget(title)
        row = QHBoxLayout()
        row.addWidget(QLabel("主题模式"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["浅色", "深色"])
        self.theme_combo.currentTextChanged.connect(self._on_theme_changed)
        row.addWidget(self.theme_combo)
        row.addStretch(1)
        box.addLayout(row)
        note = QLabel("主题和规则参数会自动记忆；styles 目录存在时会优先读取外部 QSS。")
        note.setWordWrap(True)
        note.setObjectName("MutedLabel")
        box.addWidget(note)
        layout.addWidget(card)
        layout.addStretch(1)
        return page

    def _make_group(self, title: str) -> tuple[QGroupBox, QGridLayout]:
        g = QGroupBox(title)
        g.setObjectName("Group")
        grid = QGridLayout(g)
        grid.setContentsMargins(14, 16, 14, 14)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        return g, grid

    def _tab_numbering(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(14)

        g1, grid1 = self._make_group("基础命名")
        self.base_name_edit = QLineEdit()
        grid1.addWidget(QLabel("基础文件名"), 0, 0)
        grid1.addWidget(self.base_name_edit, 1, 0, 1, 3)
        outer.addWidget(g1)

        g2, grid2 = self._make_group("编号规则")
        self.start_num_edit = QLineEdit("1")
        self.step_edit = QLineEdit("1")
        self.digits_combo = QComboBox()
        self.digits_combo.addItems([str(i) for i in range(1, 21)])
        self.position_combo = QComboBox()
        self.position_combo.addItems(["后面", "前面"])
        self.sep_edit = QLineEdit()
        self.keep_ext_check = QCheckBox("保留原扩展名")
        self.keep_ext_check.setChecked(True)

        grid2.addWidget(QLabel("起始编号"), 0, 0)
        grid2.addWidget(QLabel("递增量"), 0, 1)
        grid2.addWidget(QLabel("位数"), 0, 2)
        grid2.addWidget(self.start_num_edit, 1, 0)
        grid2.addWidget(self.step_edit, 1, 1)
        grid2.addWidget(self.digits_combo, 1, 2)
        grid2.addWidget(QLabel("分隔符"), 2, 0)
        grid2.addWidget(QLabel("编号位置"), 2, 1)
        grid2.addWidget(self.sep_edit, 3, 0)
        grid2.addWidget(self.position_combo, 3, 1)
        grid2.addWidget(self.keep_ext_check, 3, 2)
        outer.addWidget(g2)

        g3, grid3 = self._make_group("排序与编号")
        self.sort_mode_combo = QComboBox()
        self.sort_mode_combo.addItems(RuleEngine.SORT_MODES)
        self.sort_reverse_check = QCheckBox("倒序")
        grid3.addWidget(QLabel("编号前排序"), 0, 0)
        grid3.addWidget(self.sort_mode_combo, 1, 0)
        grid3.addWidget(self.sort_reverse_check, 1, 1)
        outer.addWidget(g3)
        outer.addStretch(1)
        return w

    def _tab_insert(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(0, 0, 0, 0)
        g, grid = self._make_group("插入规则")
        self.insert_enabled = QCheckBox("启用插入")
        self.insert_text_edit = QLineEdit()
        self.insert_mode_combo = QComboBox()
        self.insert_mode_combo.addItems(["前面", "后面", "指定位置"])
        self.insert_index_edit = QLineEdit("1")
        grid.addWidget(self.insert_enabled, 0, 0, 1, 2)
        grid.addWidget(QLabel("插入文本"), 1, 0)
        grid.addWidget(self.insert_text_edit, 2, 0, 1, 2)
        grid.addWidget(QLabel("插入位置"), 3, 0)
        grid.addWidget(QLabel("字符索引"), 3, 1)
        grid.addWidget(self.insert_mode_combo, 4, 0)
        grid.addWidget(self.insert_index_edit, 4, 1)
        outer.addWidget(g)
        outer.addStretch(1)
        return w

    def _tab_replace(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(0, 0, 0, 0)
        g, grid = self._make_group("替换规则")
        self.replace_enabled = QCheckBox("启用替换")
        self.replace_find_edit = QLineEdit()
        self.replace_to_edit = QLineEdit()
        self.replace_case_check = QCheckBox("区分大小写")
        self.replace_first_only_check = QCheckBox("仅替换第一个")
        grid.addWidget(self.replace_enabled, 0, 0, 1, 2)
        grid.addWidget(QLabel("查找内容"), 1, 0)
        grid.addWidget(QLabel("替换为"), 1, 1)
        grid.addWidget(self.replace_find_edit, 2, 0)
        grid.addWidget(self.replace_to_edit, 2, 1)
        grid.addWidget(self.replace_case_check, 3, 0)
        grid.addWidget(self.replace_first_only_check, 3, 1)
        outer.addWidget(g)
        outer.addStretch(1)
        return w

    def _tab_delete(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(0, 0, 0, 0)
        g, grid = self._make_group("删除规则")
        self.delete_enabled = QCheckBox("启用删除")
        self.delete_mode_combo = QComboBox()
        self.delete_mode_combo.addItems(["删除文本", "按区间删除", "删除前缀", "删除后缀"])
        self.delete_text_edit = QLineEdit()
        self.delete_start_edit = QLineEdit("1")
        self.delete_len_edit = QLineEdit("1")
        self.delete_prefix_count_edit = QLineEdit("1")
        self.delete_suffix_count_edit = QLineEdit("1")
        grid.addWidget(self.delete_enabled, 0, 0, 1, 2)
        grid.addWidget(QLabel("删除模式"), 1, 0)
        grid.addWidget(self.delete_mode_combo, 2, 0, 1, 2)
        grid.addWidget(QLabel("删除文本"), 3, 0)
        grid.addWidget(self.delete_text_edit, 4, 0, 1, 2)
        grid.addWidget(QLabel("起始位置"), 5, 0)
        grid.addWidget(QLabel("删除长度"), 5, 1)
        grid.addWidget(self.delete_start_edit, 6, 0)
        grid.addWidget(self.delete_len_edit, 6, 1)
        grid.addWidget(QLabel("前缀字符数"), 7, 0)
        grid.addWidget(QLabel("后缀字符数"), 7, 1)
        grid.addWidget(self.delete_prefix_count_edit, 8, 0)
        grid.addWidget(self.delete_suffix_count_edit, 8, 1)
        outer.addWidget(g)
        outer.addStretch(1)
        return w

    def _tab_regex(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(0, 0, 0, 0)
        g, grid = self._make_group("正则规则")
        self.regex_enabled = QCheckBox("启用正则")
        self.regex_pattern_edit = QLineEdit()
        self.regex_replace_edit = QLineEdit()
        self.regex_ignore_case_check = QCheckBox("忽略大小写")
        grid.addWidget(self.regex_enabled, 0, 0)
        grid.addWidget(QLabel("匹配表达式"), 1, 0)
        grid.addWidget(self.regex_pattern_edit, 2, 0)
        grid.addWidget(QLabel("替换表达式"), 3, 0)
        grid.addWidget(self.regex_replace_edit, 4, 0)
        grid.addWidget(self.regex_ignore_case_check, 5, 0)
        outer.addWidget(g)
        outer.addStretch(1)
        return w

    def _tab_filter(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(0, 0, 0, 0)
        g, grid = self._make_group("扩展名筛选")
        self.filter_enabled = QCheckBox("启用筛选")
        self.filter_ext_edit = QLineEdit()
        self.filter_mode_combo = QComboBox()
        self.filter_mode_combo.addItems(["仅处理这些扩展名", "排除这些扩展名"])
        grid.addWidget(self.filter_enabled, 0, 0, 1, 2)
        grid.addWidget(QLabel("扩展名"), 1, 0)
        grid.addWidget(QLabel("筛选方式"), 1, 1)
        grid.addWidget(self.filter_ext_edit, 2, 0)
        grid.addWidget(self.filter_mode_combo, 2, 1)
        outer.addWidget(g)
        outer.addStretch(1)
        return w

    def _build_execute_box(self) -> QWidget:
        box = QFrame()
        box.setObjectName("InnerCard")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        mode_row = QHBoxLayout()
        self.rename_mode_radio = QRadioButton("覆盖原文件")
        self.copy_mode_radio = QRadioButton("另存为副本")
        self.rename_mode_radio.setChecked(True)
        self.continue_on_error_check = QCheckBox("遇错继续")
        self.continue_on_error_check.setToolTip("启用后会跳过无效项和单文件失败项，继续处理剩余文件。")
        mode_row.addWidget(self.rename_mode_radio)
        mode_row.addWidget(self.copy_mode_radio)
        mode_row.addWidget(self.continue_on_error_check)
        mode_row.addStretch(1)
        layout.addLayout(mode_row)

        btn_row = QHBoxLayout()
        self.refresh_btn = QPushButton("刷新预览")
        self.export_btn = QPushButton("导出当前列表")
        self.execute_btn = QPushButton("开始重命名")
        self.cancel_btn = QPushButton("取消任务")
        self.execute_btn.setObjectName("PrimaryButton")
        self.refresh_btn.clicked.connect(lambda: self.refresh_preview(show_errors=True))
        self.export_btn.clicked.connect(self.export_list)
        self.execute_btn.clicked.connect(self.execute)
        self.cancel_btn.clicked.connect(self.cancel_current_task)
        btn_row.addWidget(self.refresh_btn)
        btn_row.addWidget(self.export_btn)
        btn_row.addWidget(self.execute_btn)
        btn_row.addWidget(self.cancel_btn)
        layout.addLayout(btn_row)

        self.progress_label = QLabel("空闲")
        self.progress_label.setObjectName("MutedLabel")
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(1)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_label)
        layout.addWidget(self.progress_bar)
        return box

    def cancel_current_task(self) -> None:
        if self._execute_worker is not None:
            self._cancel_requested = True
            self._execute_worker.stop()
            self.progress_label.setText('已请求取消执行任务，正在安全收尾…')
            self.status.showMessage('已请求取消执行任务，正在安全收尾…')
            self._add_history('请求取消执行任务')
            self._update_interaction_state()
            return
        if self._scan_worker is not None:
            self._cancel_requested = True
            self._scan_worker.stop()
            self.progress_label.setText('已请求取消扫描任务，正在收尾…')
            self.status.showMessage('已请求取消扫描任务，正在收尾…')
            self._add_history('请求取消扫描任务')
            self._update_interaction_state()
            return
        if self._preview_worker is not None:
            self._cancel_requested = True
            self._preview_pending = False
            self._preview_pending_show_errors = False
            self._preview_dirty = True
            self._preview_worker.stop()
            self.progress_label.setText('已请求取消预览任务，正在收尾…')
            self.status.showMessage('已请求取消预览任务，正在收尾…')
            self._add_history('请求取消预览任务')
            self._update_interaction_state()
            return
        QMessageBox.information(self, APP_TITLE, '当前没有正在运行的后台任务。')

    def _switch_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        if 0 <= index < len(self.nav_buttons):
            self.nav_buttons[index].setChecked(True)

    def _apply_icon(self) -> None:
        app_icon = self._asset_icon(["app_icon_final.ico", "app_icon_final.png", "app_icon.ico", "app_icon.png"], QStyle.SP_DesktopIcon)
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)
            app = QApplication.instance()
            if app is not None:
                app.setWindowIcon(app_icon)

    def _setup_stylesheet(self, theme: str) -> None:
        self.current_theme = theme
        self.setStyleSheet(load_stylesheet(theme))

    def _on_theme_changed(self, text: str) -> None:
        self._setup_stylesheet("dark" if text == "深色" else "light")
        self.settings.setValue("ui/theme", self.current_theme)

    def _watch_fields(self) -> list[QWidget]:
        return [
            self.base_name_edit, self.start_num_edit, self.step_edit, self.digits_combo,
            self.sep_edit, self.position_combo, self.keep_ext_check, self.sort_mode_combo, self.sort_reverse_check, self.insert_enabled,
            self.insert_text_edit, self.insert_mode_combo, self.insert_index_edit,
            self.replace_enabled, self.replace_find_edit, self.replace_to_edit,
            self.replace_case_check, self.replace_first_only_check, self.delete_enabled,
            self.delete_mode_combo, self.delete_text_edit, self.delete_start_edit,
            self.delete_len_edit, self.delete_prefix_count_edit, self.delete_suffix_count_edit,
            self.regex_enabled, self.regex_pattern_edit, self.regex_replace_edit,
            self.regex_ignore_case_check, self.filter_enabled, self.filter_ext_edit,
            self.filter_mode_combo,
        ]

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._signals_bound:
            for widget in self._watch_fields():
                if isinstance(widget, QLineEdit):
                    widget.textChanged.connect(self._schedule_preview_refresh)
                elif isinstance(widget, QComboBox):
                    widget.currentTextChanged.connect(self._schedule_preview_refresh)
                elif isinstance(widget, (QCheckBox, QRadioButton)):
                    widget.toggled.connect(self._schedule_preview_refresh)
            self._signals_bound = True

    def _build_rule_config(self) -> RuleConfig:
        return RuleConfig(
            base_name=self.base_name_edit.text().strip(),
            start_num=RuleEngine.parse_int(self.start_num_edit.text().strip(), "起始编号"),
            step=RuleEngine.parse_int(self.step_edit.text().strip(), "递增量", minimum=1),
            digits=RuleEngine.parse_int(self.digits_combo.currentText().strip(), "位数", minimum=1),
            position=self.position_combo.currentText().strip(),
            separator=self.sep_edit.text(),
            keep_ext=self.keep_ext_check.isChecked(),
            sort_mode=self.sort_mode_combo.currentText().strip(),
            sort_reverse=self.sort_reverse_check.isChecked(),
            insert_enabled=self.insert_enabled.isChecked(),
            insert_text=self.insert_text_edit.text(),
            insert_mode=self.insert_mode_combo.currentText().strip(),
            insert_index=RuleEngine.parse_int(self.insert_index_edit.text().strip(), "插入位置", minimum=1),
            replace_enabled=self.replace_enabled.isChecked(),
            replace_find=self.replace_find_edit.text(),
            replace_to=self.replace_to_edit.text(),
            replace_case_sensitive=self.replace_case_check.isChecked(),
            replace_first_only=self.replace_first_only_check.isChecked(),
            delete_enabled=self.delete_enabled.isChecked(),
            delete_mode=self.delete_mode_combo.currentText().strip(),
            delete_text=self.delete_text_edit.text(),
            delete_start=RuleEngine.parse_int(self.delete_start_edit.text().strip(), "删除起始位置", minimum=1),
            delete_length=RuleEngine.parse_int(self.delete_len_edit.text().strip(), "删除长度", minimum=0),
            delete_prefix_count=RuleEngine.parse_int(self.delete_prefix_count_edit.text().strip(), "前缀删除数量", minimum=0),
            delete_suffix_count=RuleEngine.parse_int(self.delete_suffix_count_edit.text().strip(), "后缀删除数量", minimum=0),
            regex_enabled=self.regex_enabled.isChecked(),
            regex_pattern=self.regex_pattern_edit.text().strip(),
            regex_replace=self.regex_replace_edit.text(),
            regex_ignore_case=self.regex_ignore_case_check.isChecked(),
            filter_enabled=self.filter_enabled.isChecked(),
            filter_ext_text=self.filter_ext_edit.text(),
            filter_mode=self.filter_mode_combo.currentText().strip(),
        )

    def _schedule_preview_refresh(self, *_args) -> None:
        if self._execute_thread is not None:
            return
        self._preview_dirty = True
        self.progress_label.setText(f"输入已变更，{PREVIEW_DEBOUNCE_MS}ms 后自动刷新预览…")
        self.preview_timer.start()

    def _refresh_preview_debounced(self) -> None:
        self.refresh_preview(show_errors=False)

    def refresh_preview(self, show_errors: bool = True) -> None:
        self.preview_timer.stop()
        self.file_count_label.setText(f"{len(self.files)} 个文件")
        self._start_preview(show_errors=show_errors)

    def _start_preview(self, show_errors: bool) -> None:
        self.file_count_label.setText(f"{len(self.files)} 个文件")
        if self._preview_thread is not None:
            self._preview_pending = True
            self._preview_pending_show_errors = self._preview_pending_show_errors or show_errors
            self.progress_label.setText("预览正在计算，已合并新的刷新请求…")
            return

        if not self.files:
            self.preview_rows = []
            self.preview_summary = PreviewSummary(0, 0, 0, 0, 0)
            self.preview_target_map = {}
            self._preview_dirty = False
            self._render_preview()
            self._update_home_stats()
            self._refresh_history_panel()
            self.progress_label.setText("空闲")
            return

        try:
            config = self._build_rule_config()
        except Exception as exc:
            self._preview_dirty = True
            if show_errors:
                QMessageBox.warning(self, APP_TITLE, str(exc))
            self.status.showMessage(f"预览未更新：{exc}")
            self.progress_label.setText(f"预览参数无效：{exc}")
            return

        self._set_preview_busy(True)
        total = max(len(self.files), 1)
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat(f"0/{total}")
        self.progress_label.setText("正在后台计算预览…")
        self.status.showMessage("正在后台计算预览…")

        self._preview_thread = QThread(self)
        self._preview_worker = PreviewWorker(self.files, config)
        self._preview_worker.moveToThread(self._preview_thread)
        self._preview_thread.started.connect(self._preview_worker.run)
        self._preview_worker.progress.connect(self._on_preview_progress)
        self._preview_worker.finished.connect(self._on_preview_finished)
        self._preview_worker.finished.connect(self._preview_thread.quit)
        self._preview_worker.failed.connect(lambda text: self._on_preview_failed(text, show_errors))
        self._preview_worker.failed.connect(self._preview_thread.quit)
        self._preview_thread.finished.connect(self._cleanup_preview_thread)
        self._preview_thread.start()

    def _update_interaction_state(self) -> None:
        preview_busy = self._preview_thread is not None
        scan_busy = self._scan_thread is not None
        execute_busy = self._execute_thread is not None
        any_busy = preview_busy or scan_busy or execute_busy

        self.refresh_btn.setEnabled(not scan_busy and not execute_busy and not preview_busy)
        self.execute_btn.setEnabled(not any_busy and not self._preview_dirty and bool(self.preview_rows))
        self.export_btn.setEnabled(not any_busy and bool(self.preview_rows))
        self.cancel_btn.setEnabled(any_busy and not self._cancel_requested)

        if hasattr(self, 'file_action_buttons'):
            for button in self.file_action_buttons:
                button.setEnabled(not any_busy)
        if hasattr(self, 'home_action_buttons'):
            for button in self.home_action_buttons:
                button.setEnabled(not any_busy)

        self.tabs.setEnabled(not scan_busy and not execute_busy)
        self.table.setEnabled(not scan_busy and not execute_busy)
        self.rename_mode_radio.setEnabled(not scan_busy and not execute_busy)
        self.copy_mode_radio.setEnabled(not scan_busy and not execute_busy)
        self.continue_on_error_check.setEnabled(not scan_busy and not execute_busy)
        if hasattr(self, 'move_up_btn'):
            move_allowed = (self.sort_mode_combo.currentText() == '当前顺序' and not self.sort_reverse_check.isChecked())
            self.move_up_btn.setEnabled(not any_busy and move_allowed)
            self.move_down_btn.setEnabled(not any_busy and move_allowed)

    def _set_preview_busy(self, busy: bool) -> None:
        _ = busy
        self._update_interaction_state()

    def _set_execute_busy(self, busy: bool) -> None:
        _ = busy
        self._update_interaction_state()

    def _set_scan_busy(self, busy: bool) -> None:
        _ = busy
        self._update_interaction_state()

    def _on_preview_progress(self, current: int, total: int, message: str) -> None:
        total = max(total, 1)
        shown = min(current, total)
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(shown)
        self.progress_bar.setFormat(f"{shown}/{total}")
        self.progress_label.setText(message)
        self.status.showMessage(message)

    def _on_preview_finished(self, result: object) -> None:
        data = result if isinstance(result, dict) else {}
        if data.get('cancelled'):
            self._preview_dirty = True
            self.progress_label.setText('预览已取消')
            self.status.showMessage('预览已取消')
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat('')
            self._set_preview_busy(False)
            return
        rows = data.get('rows', []) if isinstance(data, dict) else []
        normalized_rows = [row for row in rows if isinstance(row, PreviewRow)]
        self.preview_rows = normalized_rows
        self.preview_summary, self.preview_target_map = RuleEngine.summarize(self.preview_rows)
        self._preview_dirty = False
        self._render_preview()
        self._update_home_stats()
        self._refresh_history_panel()
        self.progress_bar.setValue(self.progress_bar.maximum())
        self.progress_bar.setFormat(f"{self.progress_bar.maximum()}/{self.progress_bar.maximum()}")
        self.progress_label.setText("预览已更新")
        self.status.showMessage(
            f"共 {self.preview_summary.total} 个文件，可处理 {self.preview_summary.ready} 个，跳过 {self.preview_summary.skip} 个，"
            f"冲突 {self.preview_summary.duplicate} 个，错误 {self.preview_summary.error} 个"
        )
        self._set_preview_busy(False)

    def _on_preview_failed(self, error_text: str, show_errors: bool) -> None:
        self._preview_dirty = True
        self._set_preview_busy(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("")
        self.progress_label.setText(f"预览参数无效：{error_text}")
        self.status.showMessage(f"预览未更新：{error_text}")
        if show_errors:
            QMessageBox.warning(self, APP_TITLE, error_text)

    def _cleanup_preview_thread(self) -> None:
        if self._preview_worker is not None:
            self._preview_worker.deleteLater()
        if self._preview_thread is not None:
            self._preview_thread.deleteLater()
        self._preview_worker = None
        self._preview_thread = None
        self._cancel_requested = False
        self._set_preview_busy(False)
        if self._preview_pending and self._execute_thread is None and self._scan_thread is None:
            show_errors = self._preview_pending_show_errors
            self._preview_pending = False
            self._preview_pending_show_errors = False
            QTimer.singleShot(0, lambda: self._start_preview(show_errors=show_errors))

    def _start_scan(self, paths: list[str], recursive: bool, label: str) -> None:
        if not paths:
            return
        if self._scan_thread is not None:
            QMessageBox.information(self, APP_TITLE, "当前仍有扫描任务在进行中，请稍后再试。")
            return
        if self._preview_thread is not None:
            QMessageBox.information(self, APP_TITLE, "预览仍在刷新，请稍后再扫描文件夹。")
            return
        self._cancel_requested = False
        self._set_scan_busy(True)
        self.progress_bar.setRange(0, 0)
        self.progress_label.setText(f"正在后台扫描{label}…")
        self.status.showMessage(f"正在后台扫描{label}…")

        self._scan_thread = QThread(self)
        self._scan_worker = ScanWorker(paths, recursive=recursive)
        self._scan_worker.moveToThread(self._scan_thread)
        self._scan_thread.started.connect(self._scan_worker.run)
        self._scan_worker.progress.connect(self._on_scan_progress)
        self._scan_worker.finished.connect(self._on_scan_finished)
        self._scan_worker.finished.connect(self._scan_thread.quit)
        self._scan_worker.failed.connect(self._on_scan_failed)
        self._scan_worker.failed.connect(self._scan_thread.quit)
        self._scan_thread.finished.connect(self._cleanup_scan_thread)
        self._scan_thread.start()

    def _on_scan_progress(self, count: int, message: str) -> None:
        suffix = f"（已发现 {count} 个文件）" if count > 0 else ""
        self.progress_label.setText(f"{message}{suffix}")
        self.status.showMessage(f"{message}{suffix}")

    def _on_scan_finished(self, result: object) -> None:
        data = result if isinstance(result, dict) else {}
        paths = [str(p) for p in data.get('paths', [])] if isinstance(data, dict) else []
        cancelled = bool(data.get('cancelled', False)) if isinstance(data, dict) else False
        self._append_paths(paths, trigger_preview=False)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("")
        if cancelled:
            self.progress_label.setText(f"扫描已取消，已发现 {len(paths)} 项")
            self.status.showMessage(f"扫描已取消，已发现 {len(paths)} 个文件")
        else:
            self.progress_label.setText(f"扫描完成，新增候选 {len(paths)} 项")
            self.status.showMessage(f"扫描完成，找到 {len(paths)} 个文件")
        self.refresh_preview(show_errors=False)

    def _on_scan_failed(self, error_text: str) -> None:
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("")
        self.progress_label.setText(f"扫描失败：{error_text}")
        self.status.showMessage(f"扫描失败：{error_text}")
        QMessageBox.critical(self, APP_TITLE, f"扫描失败：{error_text}")

    def _cleanup_scan_thread(self) -> None:
        if self._scan_worker is not None:
            self._scan_worker.deleteLater()
        if self._scan_thread is not None:
            self._scan_thread.deleteLater()
        self._scan_worker = None
        self._scan_thread = None
        self._cancel_requested = False
        self._set_scan_busy(False)

    def add_files(self) -> None:
        if self._scan_thread is not None:
            QMessageBox.information(self, APP_TITLE, "当前仍有扫描任务在进行中，请稍后再试。")
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "选择文件", self._dialog_start_dir())
        if paths:
            self._remember_path(paths[0])
        self._append_paths(paths)

    def add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹", self._dialog_start_dir())
        if folder:
            self._remember_path(folder)
            self._start_scan([folder], recursive=False, label="文件夹")

    def add_folder_recursive(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹（递归添加）", self._dialog_start_dir())
        if folder:
            self._remember_path(folder)
            self._start_scan([folder], recursive=True, label="文件夹（递归）")

    def on_files_dropped(self, paths: list[str]) -> None:
        if self._scan_thread is not None:
            QMessageBox.information(self, APP_TITLE, "当前仍有扫描任务在进行中，请稍后再试。")
            return
        if any(Path(raw).is_dir() for raw in paths):
            self._start_scan(paths, recursive=False, label="拖拽目录")
            return
        self._append_paths(paths)

    def _append_paths(self, paths: list[str], trigger_preview: bool = True) -> None:
        existing = {str(item.path).lower() for item in self.files}
        added = 0
        for raw in paths:
            p = Path(raw)
            if p.is_file() and str(p).lower() not in existing:
                self.files.append(FileItem(p))
                existing.add(str(p).lower())
                added += 1
        if paths:
            self._remember_path(paths[0])
        self.status.showMessage(f"已添加 {added} 个文件")
        self._add_history(f"添加文件：{added} 个")
        if trigger_preview:
            self.refresh_preview(show_errors=False)
        else:
            self.file_count_label.setText(f"{len(self.files)} 个文件")

    def remove_selected(self) -> None:
        selection = self.table.selectionModel().selectedRows()
        rows = sorted({idx.row() for idx in selection}, reverse=True)
        if not rows:
            return
        selected_paths = {str(self.preview_rows[row].item.path).lower() for row in rows if 0 <= row < len(self.preview_rows)}
        if not selected_paths:
            return
        before = len(self.files)
        self.files = [item for item in self.files if str(item.path).lower() not in selected_paths]
        removed = before - len(self.files)
        if removed <= 0:
            return
        self._add_history(f"移除文件：{removed} 个")
        self.refresh_preview(show_errors=False)

    def clear_files(self) -> None:
        self.files.clear()
        self.preview_rows.clear()
        self.preview_summary = PreviewSummary(0, 0, 0, 0, 0)
        self.preview_target_map.clear()
        self._add_history("清空列表")
        self.refresh_preview(show_errors=False)

    def move_selected(self, delta: int) -> None:
        if self.sort_mode_combo.currentText() != '当前顺序' or self.sort_reverse_check.isChecked():
            QMessageBox.information(self, APP_TITLE, '启用排序后编号时，无法直接上移/下移。请先切回“当前顺序”并取消倒序。')
            return
        rows = sorted({idx.row() for idx in self.table.selectionModel().selectedRows()})
        if len(rows) != 1:
            QMessageBox.information(self, APP_TITLE, '请先选中一行再移动。')
            return
        row = rows[0]
        if not (0 <= row < len(self.preview_rows)):
            return
        selected_key = str(self.preview_rows[row].item.path).lower()
        real_index = next((idx for idx, item in enumerate(self.files) if str(item.path).lower() == selected_key), -1)
        if real_index < 0:
            return
        new_index = real_index + delta
        if new_index < 0 or new_index >= len(self.files):
            return
        self.files[real_index], self.files[new_index] = self.files[new_index], self.files[real_index]
        self.refresh_preview(show_errors=False)
        new_key = str(self.files[new_index].path).lower()
        for preview_index, preview_row in enumerate(self.preview_rows):
            if str(preview_row.item.path).lower() == new_key:
                self.table.selectRow(preview_index)
                break

    def _render_preview(self) -> None:
        self.preview_model.update_data(self.preview_rows, self.preview_target_map)
        if not self.preview_rows:
            self.status.showMessage("请选择文件、文件夹，或直接拖入窗口")
            self.home_info.setPlainText("还没有导入文件。\n\n你可以从左侧工作区进入‘批量重命名’，也可以在首页快速添加文件。")
            self._update_interaction_state()
            return

        self._apply_preview_column_layout()

        self.home_info.setPlainText(
            f"当前文件总数：{self.preview_summary.total}\n"
            f"可处理：{self.preview_summary.ready}\n"
            f"跳过：{self.preview_summary.skip}\n"
            f"重名冲突：{self.preview_summary.duplicate}\n"
            f"错误：{self.preview_summary.error}\n\n"
            "当前版本支持排序后再编号。"
        )
        self._update_interaction_state()


    def _apply_preview_column_layout(self) -> None:
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        if self.preview_summary.total <= 200:
            self.table.resizeColumnsToContents()
        elif not self._table_columns_initialized:
            self.table.setColumnWidth(0, 280)
            self.table.setColumnWidth(1, 300)
            self.table.setColumnWidth(2, 140)
            self.table.setColumnWidth(3, 90)
            self.table.setColumnWidth(4, 420)
            self._table_columns_initialized = True
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

    def _update_home_stats(self) -> None:
        self.card_total.set_value(str(self.preview_summary.total))
        self.card_ready.set_value(str(self.preview_summary.ready))
        self.card_dup.set_value(str(self.preview_summary.duplicate))
        self.card_err.set_value(str(self.preview_summary.error + self.preview_summary.skip))

    def _refresh_history_panel(self) -> None:
        self.history_list.clear()
        query = self.history_search_edit.text().strip().lower() if hasattr(self, 'history_search_edit') else ''
        visible: list[str] = []
        for text in self.history[::-1]:
            if query and query not in text.lower():
                continue
            visible.append(text)
            if len(visible) >= 200:
                break
        self.history_list.addItems(visible)
        total = len(self.history)
        shown = len(visible)
        if hasattr(self, 'history_meta_label'):
            suffix = f'，匹配 {shown} 条' if query else f'，显示最近 {shown} 条'
            self.history_meta_label.setText(f'{total} 条记录{suffix}')

    def _build_tasks_from_current_rules(self) -> tuple[list[tuple[FileItem, str]], list[str]]:
        if self._preview_thread is not None or self._preview_dirty:
            raise ValueError("预览尚未刷新完成，请等待当前预览更新后再执行。")
        if not self.preview_rows:
            raise ValueError("没有可执行的文件")

        todo: list[tuple[FileItem, str]] = []
        pre_errors: list[str] = []
        seen: set[str] = set()
        tolerate = self.continue_on_error_check.isChecked()

        for row in self.preview_rows:
            if row.state == "跳过":
                continue
            if not row.new_name:
                message = f"{row.item.name}：{row.state}"
                if tolerate:
                    pre_errors.append(message)
                    continue
                raise ValueError(message)

            target = str(row.item.folder / row.new_name).lower()
            if self.preview_target_map.get(target, 0) > 1 or target in seen:
                message = f"{row.item.name}：重名冲突 -> {row.new_name}"
                if tolerate:
                    pre_errors.append(message)
                    continue
                raise ValueError(f"存在重名冲突：{row.new_name}")

            seen.add(target)
            todo.append((row.item, row.new_name))

        if not todo:
            if pre_errors:
                raise ValueError("没有可执行的文件，全部项目都已被跳过或判定为无效。")
            raise ValueError("没有可执行的文件")
        return todo, pre_errors

    def execute(self) -> None:
        if self._execute_thread is not None:
            QMessageBox.information(self, APP_TITLE, "当前任务仍在执行中，请稍后。")
            return
        if self._scan_thread is not None:
            QMessageBox.information(self, APP_TITLE, "文件夹扫描仍在进行中，请稍后再执行。")
            return
        if self._preview_thread is not None or self._preview_dirty:
            QMessageBox.information(self, APP_TITLE, "预览仍在计算或尚未刷新完成，请稍后再执行。")
            return

        try:
            tasks, pre_errors = self._build_tasks_from_current_rules()
        except ValueError as exc:
            QMessageBox.critical(self, APP_TITLE, str(exc))
            return

        continue_on_error = self.continue_on_error_check.isChecked()
        mode = "copy" if self.copy_mode_radio.isChecked() else "rename"
        mode_text = "另存为副本" if mode == "copy" else "覆盖原文件"
        extra = "\n容错模式：已开启" if continue_on_error else ""
        if QMessageBox.question(self, APP_TITLE, f"确认开始处理吗？\n\n文件数量：{len(tasks)}\n执行方式：{mode_text}{extra}") != QMessageBox.Yes:
            return

        total_steps = len(tasks) if mode == "copy" else max(len(tasks) * 2, 1)
        self.progress_bar.setRange(0, total_steps)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat(f"0/{total_steps}")
        if continue_on_error and pre_errors:
            self.progress_label.setText(f"任务已开始，已预跳过 {len(pre_errors)} 项，正在后台处理…")
        else:
            self.progress_label.setText("任务已开始，正在后台处理…")
        self.status.showMessage(f"开始执行：{len(tasks)} 个文件，模式={mode_text}")
        self._add_history(f"开始执行：{len(tasks)} 个文件，模式={mode_text}，容错={'开' if continue_on_error else '关'}")
        self._cancel_requested = False
        self._set_execute_busy(True)

        self._execute_thread = QThread(self)
        self._execute_worker = RenameWorker(tasks, mode, continue_on_error=continue_on_error, pre_errors=pre_errors)
        self._execute_worker.moveToThread(self._execute_thread)
        self._execute_thread.started.connect(self._execute_worker.run)
        self._execute_worker.progress.connect(self._on_execute_progress)
        self._execute_worker.finished.connect(self._on_execute_finished)
        self._execute_worker.finished.connect(self._execute_thread.quit)
        self._execute_worker.failed.connect(self._on_execute_failed)
        self._execute_worker.failed.connect(self._execute_thread.quit)
        self._execute_thread.finished.connect(self._cleanup_execute_thread)
        self._execute_thread.start()

    def _on_execute_progress(self, current: int, total: int, message: str) -> None:
        self.progress_bar.setRange(0, max(total, 1))
        self.progress_bar.setValue(current)
        self.progress_bar.setFormat(f"{current}/{total}")
        self.progress_label.setText(message)
        self.status.showMessage(message)

    def _on_execute_finished(self, result: object) -> None:
        data = result if isinstance(result, dict) else {}
        updated_raw = data.get("updated", {})
        if isinstance(updated_raw, dict) and updated_raw:
            updated = {key: Path(value) for key, value in updated_raw.items()}
            self.files = [FileItem(updated.get(str(item.path).lower(), item.path)) for item in self.files]

        completed = int(data.get("completed", 0) or 0)
        failed = int(data.get("failed", 0) or 0)
        pre_failed = int(data.get("pre_failed", 0) or 0)
        total_failed = failed
        mode = str(data.get("mode", "rename"))
        mode_text = "另存为副本" if mode == "copy" else "覆盖原文件"
        failure_messages = data.get("failure_messages", [])
        continue_on_error = bool(data.get("continue_on_error", False))
        cancelled = bool(data.get("cancelled", False))

        self._set_execute_busy(False)
        self.progress_bar.setValue(self.progress_bar.maximum())
        self.progress_bar.setFormat(f"{self.progress_bar.maximum()}/{self.progress_bar.maximum()}")

        if cancelled:
            self._add_history(f"执行已取消：已完成 {completed} 个文件，失败/跳过 {total_failed}，模式={mode_text}")
            self.progress_label.setText(f"执行已取消：已完成 {completed}，失败/跳过 {total_failed}")
            self.status.showMessage(f"执行已取消：已完成 {completed}，失败/跳过 {total_failed}")
        elif continue_on_error and total_failed > 0:
            self._add_history(f"执行完成：成功 {completed}，失败/跳过 {total_failed}，模式={mode_text}")
            self.progress_label.setText(f"处理完成：成功 {completed}，失败/跳过 {total_failed}")
            self.status.showMessage(f"处理完成：成功 {completed}，失败/跳过 {total_failed}")
        else:
            self._add_history(f"执行完成：{completed} 个文件，模式={mode_text}")
            self.progress_label.setText(f"处理完成：{completed} 个文件")
            self.status.showMessage(f"处理完成，共 {completed} 个文件。")

        if isinstance(failure_messages, list) and failure_messages:
            for detail in failure_messages[:50]:
                self._add_history(f"失败明细：{detail}", refresh=False)
            self._refresh_history_panel()

        self.refresh_preview(show_errors=False)

        if cancelled:
            preview_lines = [f"已完成：{completed} 项", f"失败/跳过：{total_failed} 项"]
            if pre_failed > 0:
                preview_lines.insert(0, f"预检查跳过：{pre_failed} 项")
            QMessageBox.information(self, APP_TITLE, "\n".join(["任务已取消。", *preview_lines]))
        elif continue_on_error and total_failed > 0:
            preview_lines = []
            if pre_failed > 0:
                preview_lines.append(f"预检查跳过：{pre_failed} 项")
            preview_lines.append(f"实际成功：{completed} 项")
            preview_lines.append(f"失败/跳过：{total_failed} 项")
            details = failure_messages[:12] if isinstance(failure_messages, list) else []
            if details:
                preview_lines.append("")
                preview_lines.append("部分失败明细：")
                preview_lines.extend(details)
                if len(failure_messages) > len(details):
                    preview_lines.append(f"……其余 {len(failure_messages) - len(details)} 项请查看历史记录")
            QMessageBox.warning(self, APP_TITLE, "\n".join(preview_lines))
        else:
            QMessageBox.information(self, APP_TITLE, f"处理完成，共 {completed} 个文件。")

    def _on_execute_failed(self, error_text: str) -> None:
        self._set_execute_busy(False)
        self.progress_label.setText(f"处理失败：{error_text}")
        self.status.showMessage(f"处理失败：{error_text}")
        self._add_history(f"执行失败：{error_text}")
        self.refresh_preview(show_errors=False)
        QMessageBox.critical(self, APP_TITLE, f"处理失败：{error_text}")

    def _cleanup_execute_thread(self) -> None:
        if self._execute_worker is not None:
            self._execute_worker.deleteLater()
        if self._execute_thread is not None:
            self._execute_thread.deleteLater()
        self._execute_worker = None
        self._execute_thread = None
        self._cancel_requested = False
        self._set_execute_busy(False)

    def export_list(self) -> None:
        if not self.preview_rows:
            QMessageBox.information(self, APP_TITLE, "当前没有可导出的内容。")
            return

        default_path = str(Path(self._dialog_start_dir()) / "rename_preview.csv")
        save_path, _ = QFileDialog.getSaveFileName(self, "导出当前列表", default_path, "CSV Files (*.csv);;Text Files (*.txt)")
        if not save_path:
            return
        self._remember_path(save_path)

        try:
            FileManager.export_preview(self.preview_rows, self.preview_target_map, Path(save_path))
            QMessageBox.information(self, APP_TITLE, "导出完成。")
            self._add_history(f"导出列表：{save_path}")
        except Exception as exc:
            QMessageBox.critical(self, APP_TITLE, f"导出失败：{exc}")


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setApplicationDisplayName(f"{APP_TITLE} V{APP_VERSION}")
    app.setStyle("Fusion")
    window = RenamerWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
