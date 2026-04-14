from __future__ import annotations

import csv
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, Signal, QSize, QUrl
from PySide6.QtGui import QAction, QColor, QDesktopServices, QDragEnterEvent, QDropEvent, QFont, QIcon, QPixmap
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
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

APP_NAME = "free_rename"
APP_VERSION = "1.0"
APP_TITLE = APP_NAME
PROJECT_URL = ""  # 上传到 GitHub 后，把这里改成你的仓库地址
TEMP_PREFIX = ".__batchrename_temp__"
INVALID_CHARS = set('\\/:*?"<>|')
MAX_SAFE_PATH_LEN = 240


def resource_path(relative_path: str) -> str:
    base_path = getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)
    return str(Path(base_path) / relative_path)


def find_asset(candidates: List[str]) -> Optional[Path]:
    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
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

@dataclass
class FileItem:
    path: Path

    @property
    def folder(self) -> Path:
        return self.path.parent

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def stem(self) -> str:
        return self.path.stem

    @property
    def ext(self) -> str:
        return self.path.suffix


class DropTable(QTableWidget):
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

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        paths: List[str] = []
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


class RenamerWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.files: List[FileItem] = []
        self.preview_rows: List[Tuple[FileItem, Optional[str], str, str, str]] = []
        self.history: List[str] = []
        self.current_theme = "light"
        self._build_window()
        self._apply_icon()
        self._setup_stylesheet("light")
        self.refresh_preview()

    def _std_icon(self, which: QStyle.StandardPixmap) -> QIcon:
        return self.style().standardIcon(which)

    def _asset_icon(self, names: List[str], fallback: QStyle.StandardPixmap) -> QIcon:
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
        self.nav_buttons: List[SidebarButton] = []
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

    def _make_page_shell(self, title: str, subtitle: str) -> Tuple[QWidget, QVBoxLayout]:
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
        for text, cb in [
            ("➕ 添加文件", self.add_files),
            ("📁 添加文件夹", self.add_folder),
            ("🔁 递归添加", self.add_folder_recursive),
            ("🚀 转到批量重命名", lambda: self._switch_page(1)),
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(cb)
            ql.addWidget(btn)
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
        for text, cb in [
            ("➕ 添加文件", self.add_files),
            ("📁 文件夹", self.add_folder),
            ("🔁 递归", self.add_folder_recursive),
            ("🗑 移除", self.remove_selected),
            ("🧹 清空", self.clear_files),
            ("⬆ 上移", lambda: self.move_selected(-1)),
            ("⬇ 下移", lambda: self.move_selected(1)),
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(cb)
            toolbar.addWidget(btn)
        toolbar.addStretch(1)
        left_layout.addLayout(toolbar)

        self.table = DropTable()
        self.table.filesDropped.connect(self.on_files_dropped)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["原文件名", "预览新文件名", "状态", "扩展名", "所在目录"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(False)
        self.table.horizontalHeader().setStretchLastSection(True)
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
        title = QLabel("最近操作")
        title.setObjectName("CardTitle")
        self.history_list = QListWidget()
        box.addWidget(title)
        box.addWidget(self.history_list)
        layout.addWidget(card, 1)
        return page

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
        note = QLabel("这版采用 PySide6 + QSS 实现现代桌面风格，更适合做成正式软件。")
        note.setWordWrap(True)
        note.setObjectName("MutedLabel")
        box.addWidget(note)
        layout.addWidget(card)
        layout.addStretch(1)
        return page

    def _make_group(self, title: str) -> Tuple[QGroupBox, QGridLayout]:
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
        mode_row.addWidget(self.rename_mode_radio)
        mode_row.addWidget(self.copy_mode_radio)
        mode_row.addWidget(self.continue_on_error_check)
        mode_row.addStretch(1)
        layout.addLayout(mode_row)

        btn_row = QHBoxLayout()
        self.refresh_btn = QPushButton("刷新预览")
        self.export_btn = QPushButton("导出当前列表")
        self.execute_btn = QPushButton("开始重命名")
        self.execute_btn.setObjectName("PrimaryButton")
        self.refresh_btn.clicked.connect(self.refresh_preview)
        self.export_btn.clicked.connect(self.export_list)
        self.execute_btn.clicked.connect(self.execute)
        btn_row.addWidget(self.refresh_btn)
        btn_row.addWidget(self.export_btn)
        btn_row.addWidget(self.execute_btn)
        layout.addLayout(btn_row)
        return box

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

        self.current_theme = theme
        qss = f"""
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
        QPushButton#UnusedHeaderLinkButton {{
            background: transparent;
            border: 1px solid transparent;
            border-radius: 12px;
            padding: 8px 14px;
            color: {text};
            font-weight: 600;
        }}
        QPushButton#HeaderLinkButton:hover {{
            background: rgba(59,130,246,0.10);
            border-color: rgba(59,130,246,0.20);
            color: {accent};
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
        }}
        QTextEdit, QListWidget {{
            background: {card};
            border: 1px solid {border};
            border-radius: 12px;
        }}
        QTabWidget::pane {{
            background: transparent;
            border: none;
        }}
        QLineEdit, QComboBox {{
            padding: 9px 12px;
            min-height: 20px;
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
        QTableWidget {{
            background: {card};
            alternate-background-color: {table_alt};
            border: 1px solid {border};
            border-radius: 14px;
            gridline-color: {border};
        }}
        QTableWidget::item {{
            padding: 8px;
        }}
        QTableWidget::item:selected {{
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
        self.setStyleSheet(qss)

    def _on_theme_changed(self, text: str) -> None:
        self._setup_stylesheet("dark" if text == "深色" else "light")

    def _watch_fields(self) -> List[QWidget]:
        return [
            self.base_name_edit, self.start_num_edit, self.step_edit, self.digits_combo,
            self.sep_edit, self.position_combo, self.keep_ext_check, self.insert_enabled,
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
        if not hasattr(self, "_signals_bound"):
            for widget in self._watch_fields():
                if isinstance(widget, QLineEdit):
                    widget.textChanged.connect(self.refresh_preview)
                elif isinstance(widget, QComboBox):
                    widget.currentTextChanged.connect(self.refresh_preview)
                elif isinstance(widget, (QCheckBox, QRadioButton)):
                    widget.toggled.connect(self.refresh_preview)
            self._signals_bound = True

    def add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "选择文件")
        self._append_paths(paths)

    def add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if folder:
            self._append_paths([str(p) for p in Path(folder).iterdir() if p.is_file()])

    def add_folder_recursive(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹（递归添加）")
        if folder:
            self._append_paths([str(p) for p in Path(folder).rglob("*") if p.is_file()])

    def on_files_dropped(self, paths: List[str]) -> None:
        expanded: List[str] = []
        for raw in paths:
            p = Path(raw)
            if p.is_dir():
                expanded.extend([str(x) for x in p.iterdir() if x.is_file()])
            elif p.is_file():
                expanded.append(str(p))
        self._append_paths(expanded)

    def _append_paths(self, paths: List[str]) -> None:
        existing = {str(item.path).lower() for item in self.files}
        added = 0
        for raw in paths:
            p = Path(raw)
            if p.is_file() and str(p).lower() not in existing:
                self.files.append(FileItem(p))
                existing.add(str(p).lower())
                added += 1
        self.status.showMessage(f"已添加 {added} 个文件")
        self.history.append(f"添加文件：{added} 个")
        self.refresh_preview()

    def remove_selected(self) -> None:
        rows = sorted({idx.row() for idx in self.table.selectionModel().selectedRows()}, reverse=True)
        if not rows:
            return
        for row in rows:
            if 0 <= row < len(self.files):
                del self.files[row]
        self.history.append(f"移除文件：{len(rows)} 个")
        self.refresh_preview()

    def clear_files(self) -> None:
        self.files.clear()
        self.preview_rows.clear()
        self.history.append("清空列表")
        self.refresh_preview()

    def move_selected(self, delta: int) -> None:
        rows = sorted({idx.row() for idx in self.table.selectionModel().selectedRows()})
        if len(rows) != 1:
            QMessageBox.information(self, APP_TITLE, "请先选中一行再移动。")
            return
        row = rows[0]
        new_row = row + delta
        if new_row < 0 or new_row >= len(self.files):
            return
        self.files[row], self.files[new_row] = self.files[new_row], self.files[row]
        self.refresh_preview()
        self.table.selectRow(new_row)

    def _parse_int(self, value: str, field_name: str, minimum: Optional[int] = None) -> int:
        try:
            num = int(value)
        except ValueError as exc:
            raise ValueError(f"{field_name}必须是整数") from exc
        if minimum is not None and num < minimum:
            raise ValueError(f"{field_name}不能小于{minimum}")
        return num

    def _parse_exts(self, raw: str) -> set[str]:
        exts = set()
        for part in raw.replace("；", ",").replace(" ", ",").split(","):
            item = part.strip().lower()
            if not item:
                continue
            if not item.startswith("."):
                item = "." + item
            exts.add(item)
        return exts

    def _passes_filter(self, item: FileItem) -> bool:
        if not self.filter_enabled.isChecked():
            return True
        exts = self._parse_exts(self.filter_ext_edit.text())
        if not exts:
            return True
        matched = item.ext.lower() in exts
        return matched if self.filter_mode_combo.currentText() == "仅处理这些扩展名" else not matched

    def _sanitize_name(self, stem: str) -> str:
        cleaned = "".join("_" if ch in INVALID_CHARS else ch for ch in stem)
        return cleaned.rstrip(" .")

    def _apply_insert(self, stem: str) -> str:
        if not self.insert_enabled.isChecked():
            return stem
        text = self.insert_text_edit.text()
        if not text:
            return stem
        mode = self.insert_mode_combo.currentText().strip()
        if mode == "前面":
            return text + stem
        if mode == "后面":
            return stem + text
        index = self._parse_int(self.insert_index_edit.text().strip(), "插入位置", minimum=1)
        pos = max(0, min(len(stem), index - 1))
        return stem[:pos] + text + stem[pos:]

    def _apply_replace(self, stem: str) -> str:
        if not self.replace_enabled.isChecked():
            return stem
        old = self.replace_find_edit.text()
        new = self.replace_to_edit.text()
        if old == "":
            return stem
        if self.replace_case_check.isChecked():
            return stem.replace(old, new, 1) if self.replace_first_only_check.isChecked() else stem.replace(old, new)
        pattern = re.escape(old)
        count = 1 if self.replace_first_only_check.isChecked() else 0
        return re.sub(pattern, new, stem, count=count, flags=re.IGNORECASE)

    def _apply_delete(self, stem: str) -> str:
        if not self.delete_enabled.isChecked():
            return stem
        mode = self.delete_mode_combo.currentText().strip()
        if mode == "删除文本":
            text = self.delete_text_edit.text()
            return stem.replace(text, "") if text else stem
        if mode == "按区间删除":
            start = self._parse_int(self.delete_start_edit.text().strip(), "删除起始位置", minimum=1)
            length = self._parse_int(self.delete_len_edit.text().strip(), "删除长度", minimum=0)
            s = start - 1
            e = s + length
            return stem[:s] + stem[e:]
        if mode == "删除前缀":
            count = self._parse_int(self.delete_prefix_count_edit.text().strip(), "前缀删除数量", minimum=0)
            return stem[count:]
        if mode == "删除后缀":
            count = self._parse_int(self.delete_suffix_count_edit.text().strip(), "后缀删除数量", minimum=0)
            return stem[:-count] if count > 0 else stem
        return stem

    def _get_compiled_regex(self) -> Optional[tuple[re.Pattern[str], str]]:
        if not self.regex_enabled.isChecked():
            return None
        pattern = self.regex_pattern_edit.text().strip()
        if not pattern:
            return None
        flags = re.IGNORECASE if self.regex_ignore_case_check.isChecked() else 0
        compiled = re.compile(pattern, flags)
        return compiled, self.regex_replace_edit.text()

    def _apply_regex(self, stem: str, regex_rule: Optional[tuple[re.Pattern[str], str]] = None) -> str:
        if regex_rule is None:
            regex_rule = self._get_compiled_regex()
        if regex_rule is None:
            return stem
        compiled, repl = regex_rule
        return compiled.sub(repl, stem)

    def _build_final_name(self, item: FileItem, seq_num: int, regex_rule: Optional[tuple[re.Pattern[str], str]] = None) -> str:
        digits = self._parse_int(self.digits_combo.currentText().strip(), "位数", minimum=1)
        number_text = str(seq_num).zfill(digits)
        base_name = self.base_name_edit.text().strip()
        sep = self.sep_edit.text()
        position = self.position_combo.currentText().strip()
        stem = f"{number_text}{sep}{base_name}" if base_name and position == "前面" else f"{base_name}{sep}{number_text}" if base_name else number_text
        stem = self._apply_insert(stem)
        stem = self._apply_replace(stem)
        stem = self._apply_delete(stem)
        stem = self._apply_regex(stem, regex_rule)
        stem = self._sanitize_name(stem)
        if not stem:
            raise ValueError("生成的新文件名为空")
        final_name = stem + (item.ext if self.keep_ext_check.isChecked() else "")
        if len(str(item.folder / final_name)) >= MAX_SAFE_PATH_LEN:
            raise ValueError("目标路径过长")
        return final_name

    def generate_preview(self) -> List[Tuple[FileItem, Optional[str], str, str, str]]:
        start_num = self._parse_int(self.start_num_edit.text().strip(), "起始编号")
        step = self._parse_int(self.step_edit.text().strip(), "递增量", minimum=1)
        regex_rule = self._get_compiled_regex()
        preview: List[Tuple[FileItem, Optional[str], str, str, str]] = []
        seq_index = 0
        for item in self.files:
            if not self._passes_filter(item):
                preview.append((item, None, "跳过", item.ext or "-", str(item.folder)))
                continue
            try:
                seq_num = start_num + seq_index * step
                new_name = self._build_final_name(item, seq_num, regex_rule)
                preview.append((item, new_name, "待处理", item.ext or "-", str(item.folder)))
                seq_index += 1
            except Exception as exc:
                preview.append((item, None, f"错误：{exc}", item.ext or "-", str(item.folder)))
        return preview

    def refresh_preview(self) -> None:
        self.file_count_label.setText(f"{len(self.files)} 个文件")
        try:
            self.preview_rows = self.generate_preview() if self.files else []
        except Exception as exc:
            QMessageBox.warning(self, APP_TITLE, str(exc))
            self.preview_rows = []
        self._render_preview()
        self._update_home_stats()
        self._refresh_history_panel()

    def _render_preview(self) -> None:
        self.table.setRowCount(0)
        if not self.preview_rows:
            self.status.showMessage("请选择文件、文件夹，或直接拖入窗口")
            self.home_info.setPlainText("还没有导入文件。\n\n你可以从左侧工作区进入‘批量重命名’，也可以在首页快速添加文件。")
            return

        target_map: Dict[str, int] = {}
        for item, new_name, _state, _ext, _folder in self.preview_rows:
            if new_name:
                target = str(item.folder / new_name).lower()
                target_map[target] = target_map.get(target, 0) + 1

        dup_count = err_count = skip_count = 0
        self.table.setRowCount(len(self.preview_rows))
        for row, (item, new_name, state, ext, folder) in enumerate(self.preview_rows):
            show_name = new_name or "-"
            bg = None
            if new_name and target_map.get(str(item.folder / new_name).lower(), 0) > 1:
                state = "重名冲突"
                dup_count += 1
                bg = QColor("#fee2e2")
            elif state.startswith("错误"):
                err_count += 1
                bg = QColor("#ffedd5")
            elif state == "跳过":
                skip_count += 1
                bg = QColor("#f3f4f6")

            values = [item.name, show_name, state, ext, folder]
            for col, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if bg:
                    cell.setBackground(bg)
                self.table.setItem(row, col, cell)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

        ok_count = len(self.preview_rows) - dup_count - err_count - skip_count
        self.status.showMessage(f"共 {len(self.preview_rows)} 个文件，可处理 {ok_count} 个，跳过 {skip_count} 个，冲突 {dup_count} 个，错误 {err_count} 个")
        self.home_info.setPlainText(
            f"当前文件总数：{len(self.preview_rows)}\n"
            f"可处理：{ok_count}\n跳过：{skip_count}\n重名冲突：{dup_count}\n错误：{err_count}\n\n"
            "界面已经切换为 PySide6 仪表盘风格。"
        )

    def _update_home_stats(self) -> None:
        total = len(self.preview_rows)
        ready = dup = err = 0
        target_map: Dict[str, int] = {}
        for item, new_name, _state, _ext, _folder in self.preview_rows:
            if new_name:
                target = str(item.folder / new_name).lower()
                target_map[target] = target_map.get(target, 0) + 1
        for item, new_name, state, *_ in self.preview_rows:
            if new_name and target_map.get(str(item.folder / new_name).lower(), 0) > 1:
                dup += 1
            elif state.startswith("错误") or state == "跳过":
                err += 1
            else:
                ready += 1
        self.card_total.set_value(str(total))
        self.card_ready.set_value(str(ready))
        self.card_dup.set_value(str(dup))
        self.card_err.set_value(str(err))

    def _refresh_history_panel(self) -> None:
        self.history_list.clear()
        for text in self.history[-100:][::-1]:
            self.history_list.addItem(text)

    def validate_execute(self) -> List[Tuple[FileItem, str]]:
        if not self.preview_rows:
            raise ValueError("没有可处理的文件")
        todo: List[Tuple[FileItem, str]] = []
        seen: set[str] = set()
        for item, new_name, state, _ext, _folder in self.preview_rows:
            if state == "跳过":
                continue
            if not new_name:
                raise ValueError(f"文件 {item.name} 无法生成新文件名")
            target = str(item.folder / new_name).lower()
            if target in seen:
                raise ValueError(f"存在重名冲突：{new_name}")
            seen.add(target)
            todo.append((item, new_name))
        if not todo:
            raise ValueError("没有可执行的文件")
        return todo

    def _move_path(self, source: Path, target: Path) -> None:
        try:
            os.rename(source, target)
        except OSError:
            shutil.move(str(source), str(target))

    def execute(self) -> None:
        try:
            self.refresh_preview()
            tasks = self.validate_execute()
        except ValueError as exc:
            QMessageBox.critical(self, APP_TITLE, str(exc))
            return
        mode_text = "另存为副本" if self.copy_mode_radio.isChecked() else "覆盖原文件"
        if QMessageBox.question(self, APP_TITLE, f"确认开始处理吗？\n\n文件数量：{len(tasks)}\n执行方式：{mode_text}") != QMessageBox.Yes:
            return
        try:
            if self.copy_mode_radio.isChecked():
                self._execute_copy(tasks)
            else:
                self._execute_rename(tasks)
        except Exception as exc:
            QMessageBox.critical(self, APP_TITLE, f"处理失败：{exc}")
            self.history.append(f"执行失败：{exc}")
            self.refresh_preview()
            return
        self.history.append(f"执行完成：{len(tasks)} 个文件，模式={mode_text}")
        self.refresh_preview()
        QMessageBox.information(self, APP_TITLE, f"处理完成，共 {len(tasks)} 个文件。")

    def _execute_copy(self, tasks: List[Tuple[FileItem, str]]) -> None:
        for item, new_name in tasks:
            target = item.folder / new_name
            if target.exists():
                raise FileExistsError(f"目标文件已存在：{target}")
        for item, new_name in tasks:
            shutil.copy2(item.path, item.folder / new_name)

    def _execute_rename(self, tasks: List[Tuple[FileItem, str]]) -> None:
        temp_pairs: List[Tuple[FileItem, Path, str]] = []
        for idx, (item, new_name) in enumerate(tasks):
            temp_path = item.folder / f"{TEMP_PREFIX}{idx}__{item.name}"
            if temp_path.exists():
                raise FileExistsError(f"临时文件名已存在：{temp_path}")
            self._move_path(item.path, temp_path)
            temp_pairs.append((item, temp_path, new_name))
        try:
            updated: Dict[str, Path] = {}
            for item, temp_path, new_name in temp_pairs:
                final_path = item.folder / new_name
                if final_path.exists():
                    raise FileExistsError(f"目标文件已存在：{final_path}")
                self._move_path(temp_path, final_path)
                updated[str(item.path).lower()] = final_path
            self.files = [FileItem(updated.get(str(item.path).lower(), item.path)) for item in self.files]
        except Exception:
            for item, temp_path, new_name in temp_pairs:
                original = item.path
                final_path = item.folder / new_name
                try:
                    if temp_path.exists():
                        self._move_path(temp_path, original)
                    elif final_path.exists() and final_path != original:
                        self._move_path(final_path, original)
                except Exception:
                    pass
            raise

    def export_list(self) -> None:
        if not self.preview_rows:
            QMessageBox.information(self, APP_TITLE, "当前没有可导出的内容。")
            return
        save_path, _ = QFileDialog.getSaveFileName(self, "导出当前列表", str(Path.home() / "rename_preview.csv"), "CSV Files (*.csv);;Text Files (*.txt)")
        if not save_path:
            return
        try:
            path = Path(save_path)
            if path.suffix.lower() == ".csv":
                with path.open("w", encoding="utf-8-sig", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(["原文件名", "预览新文件名", "状态", "扩展名", "所在目录"])
                    for item, new_name, state, ext, folder in self.preview_rows:
                        writer.writerow([item.name, new_name or "", state, ext, folder])
            else:
                parts = []
                for item, new_name, state, ext, folder in self.preview_rows:
                    parts.append(f"原文件名：{item.name}\n预览新文件名：{new_name or '-'}\n状态：{state}\n扩展名：{ext}\n所在目录：{folder}\n{'-' * 60}")
                path.write_text("\n".join(parts), encoding="utf-8")
            QMessageBox.information(self, APP_TITLE, "导出完成。")
            self.history.append(f"导出列表：{path}")
            self._refresh_history_panel()
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
