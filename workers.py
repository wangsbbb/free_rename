from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from file_manager import FileManager
from rule_engine import FileItem, OperationCancelled, RuleConfig, RuleEngine


class PreviewWorker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, files: list[FileItem], config: RuleConfig) -> None:
        super().__init__()
        self.files = list(files)
        self.config = config
        self._cancel_requested = False

    def stop(self) -> None:
        self._cancel_requested = True

    def is_cancel_requested(self) -> bool:
        return self._cancel_requested

    def run(self) -> None:
        finished_emit = self.finished.emit
        failed_emit = self.failed.emit
        is_cancel_requested = self.is_cancel_requested
        progress_emit = self.progress.emit
        files = self.files
        config = self.config
        try:
            rows = RuleEngine.generate_preview(
                files,
                config,
                should_cancel=is_cancel_requested,
                progress=progress_emit,
            )
            finished_emit({'rows': rows, 'cancelled': False})
        except OperationCancelled:
            finished_emit({'rows': None, 'cancelled': True})
        except Exception as exc:
            failed_emit(str(exc))


class ScanWorker(QObject):
    progress = Signal(int, str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, paths: list[str], recursive: bool = False) -> None:
        super().__init__()
        self.paths = list(paths)
        self.recursive = recursive
        self._cancel_requested = False

    def stop(self) -> None:
        self._cancel_requested = True

    def is_cancel_requested(self) -> bool:
        return self._cancel_requested

    def _emit_progress(self, count: int, message: str) -> None:
        self.progress.emit(count, message)

    def run(self) -> None:
        finished_emit = self.finished.emit
        failed_emit = self.failed.emit
        progress_emit = self.progress.emit
        is_cancel_requested = self.is_cancel_requested
        recursive = self.recursive
        paths = self.paths
        try:
            results: list[str] = []
            seen: set[str] = set()
            append_result = results.append
            seen_add = seen.add
            seen_contains = seen.__contains__

            def add_file(path: Path) -> None:
                key = str(path).lower()
                if seen_contains(key):
                    return
                seen_add(key)
                append_result(str(path))
                result_count = len(results)
                if result_count == 1 or result_count % 200 == 0:
                    progress_emit(result_count, f"正在扫描，已发现 {result_count} 个文件…")

            for raw in paths:
                if is_cancel_requested():
                    finished_emit({'paths': results, 'cancelled': True})
                    return

                path = Path(raw)
                if path.is_file():
                    add_file(path)
                    continue
                if not path.is_dir():
                    continue

                progress_emit(len(results), f"正在扫描：{path.name}")
                iterator = path.rglob('*') if recursive else path.iterdir()
                for item in iterator:
                    if is_cancel_requested():
                        finished_emit({'paths': results, 'cancelled': True})
                        return
                    try:
                        if item.is_file():
                            add_file(item)
                    except OSError:
                        continue

            finished_emit({'paths': results, 'cancelled': False})
        except Exception as exc:
            failed_emit(str(exc))


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
        self._cancel_requested = False

    def stop(self) -> None:
        self._cancel_requested = True

    def is_cancel_requested(self) -> bool:
        return self._cancel_requested

    def run(self) -> None:
        finished_emit = self.finished.emit
        failed_emit = self.failed.emit
        progress_emit = self.progress.emit
        is_cancel_requested = self.is_cancel_requested
        tasks = self.tasks
        mode = self.mode
        continue_on_error = self.continue_on_error
        pre_errors = self.pre_errors
        try:
            result = FileManager.execute(
                tasks,
                mode,
                continue_on_error=continue_on_error,
                progress=progress_emit,
                pre_errors=pre_errors,
                should_cancel=is_cancel_requested,
            )
            finished_emit(result)
        except Exception as exc:
            failed_emit(str(exc))
