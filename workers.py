from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from file_manager import FileManager
from rule_engine import FileItem, RuleConfig, RuleEngine


class PreviewWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, files: list[FileItem], config: RuleConfig) -> None:
        super().__init__()
        self.files = list(files)
        self.config = config

    def run(self) -> None:
        try:
            rows = RuleEngine.generate_preview(self.files, self.config)
            self.finished.emit(rows)
        except Exception as exc:
            self.failed.emit(str(exc))


class ScanWorker(QObject):
    progress = Signal(int, str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, paths: list[str], recursive: bool = False) -> None:
        super().__init__()
        self.paths = list(paths)
        self.recursive = recursive

    def _emit_progress(self, count: int, message: str) -> None:
        self.progress.emit(count, message)

    def run(self) -> None:
        try:
            results: list[str] = []
            seen: set[str] = set()

            def add_file(path: Path) -> None:
                key = str(path).lower()
                if key in seen:
                    return
                seen.add(key)
                results.append(str(path))
                if len(results) == 1 or len(results) % 200 == 0:
                    self._emit_progress(len(results), f"正在扫描，已发现 {len(results)} 个文件…")

            for raw in self.paths:
                path = Path(raw)
                if path.is_file():
                    add_file(path)
                    continue
                if not path.is_dir():
                    continue

                self._emit_progress(len(results), f"正在扫描：{path.name}")
                iterator = path.rglob('*') if self.recursive else path.iterdir()
                for item in iterator:
                    try:
                        if item.is_file():
                            add_file(item)
                    except OSError:
                        continue

            self.finished.emit(results)
        except Exception as exc:
            self.failed.emit(str(exc))


class RenameWorker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        tasks: list[tuple[FileItem, str]],
        mode: str,
        continue_on_error: bool = False,
        pre_errors: list[str] | None = None,
    ) -> None:
        super().__init__()
        self.tasks = tasks
        self.mode = mode
        self.continue_on_error = continue_on_error
        self.pre_errors = list(pre_errors or [])

    def run(self) -> None:
        try:
            result = FileManager.execute(
                self.tasks,
                self.mode,
                continue_on_error=self.continue_on_error,
                progress=self.progress.emit,
                pre_errors=self.pre_errors,
            )
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))
