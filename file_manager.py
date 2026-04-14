from __future__ import annotations

import csv
import os
import shutil
from pathlib import Path
from typing import Callable, Optional


from rule_engine import FileItem, PreviewRow

TEMP_PREFIX = '.__batchrename_temp__'


def safe_move_path(source: Path, target: Path) -> None:
    try:
        os.rename(source, target)
    except OSError:
        shutil.move(str(source), str(target))


class FileManager:
    @staticmethod
    def export_preview(rows: list[PreviewRow], target_map: dict[str, int], path: Path) -> None:
        if path.suffix.lower() == '.csv':
            with path.open('w', encoding='utf-8-sig', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['原文件名', '预览新文件名', '状态', '扩展名', '所在目录'])
                for row in rows:
                    state = row.state
                    if row.new_name and row.state != '跳过' and target_map.get(str(row.item.folder / row.new_name).lower(), 0) > 1:
                        state = '重名冲突'
                    writer.writerow([row.item.name, row.new_name or '', state, row.ext, row.folder])
            return

        parts: list[str] = []
        for row in rows:
            state = row.state
            if row.new_name and row.state != '跳过' and target_map.get(str(row.item.folder / row.new_name).lower(), 0) > 1:
                state = '重名冲突'
            parts.append(
                f"原文件名：{row.item.name}\n"
                f"预览新文件名：{row.new_name or '-'}\n"
                f"状态：{state}\n"
                f"扩展名：{row.ext}\n"
                f"所在目录：{row.folder}\n{'-' * 60}"
            )
        path.write_text('\n'.join(parts), encoding='utf-8')

    @staticmethod
    def _normalize_failure(item: FileItem, new_name: str, exc: Exception) -> str:
        return f'{item.name} -> {new_name}：{exc}'

    @staticmethod
    def _run_copy(
        tasks: list[tuple[FileItem, str]],
        continue_on_error: bool,
        progress: Optional[Callable[[int, int, str], None]],
        failure_messages: list[str],
    ) -> dict[str, object]:
        total = max(len(tasks), 1)
        completed = 0
        for index, (item, new_name) in enumerate(tasks, start=1):
            try:
                target = item.folder / new_name
                if target.exists():
                    raise FileExistsError(f'目标文件已存在：{target}')
                shutil.copy2(item.path, target)
                completed += 1
            except Exception as exc:
                if not continue_on_error:
                    raise
                failure_messages.append(FileManager._normalize_failure(item, new_name, exc))
            finally:
                if progress is not None:
                    progress(index, total, f'正在复制：{item.name}')
        return {'mode': 'copy', 'completed': completed, 'updated': {}, 'failed': len(failure_messages)}

    @staticmethod
    def _run_rename_strict(
        tasks: list[tuple[FileItem, str]],
        progress: Optional[Callable[[int, int, str], None]],
    ) -> dict[str, object]:
        total = max(len(tasks) * 2, 1)
        current = 0
        temp_pairs: list[tuple[FileItem, Path, str]] = []
        for idx, (item, new_name) in enumerate(tasks):
            temp_path = item.folder / f'{TEMP_PREFIX}{idx}__{item.name}'
            if temp_path.exists():
                raise FileExistsError(f'临时文件名已存在：{temp_path}')
            safe_move_path(item.path, temp_path)
            temp_pairs.append((item, temp_path, new_name))
            current += 1
            if progress is not None:
                progress(current, total, f'准备重命名：{item.name}')
        try:
            updated: dict[str, Path] = {}
            for item, temp_path, new_name in temp_pairs:
                final_path = item.folder / new_name
                if final_path.exists():
                    raise FileExistsError(f'目标文件已存在：{final_path}')
                safe_move_path(temp_path, final_path)
                updated[str(item.path).lower()] = final_path
                current += 1
                if progress is not None:
                    progress(current, total, f'正在写入：{final_path.name}')
            return {'mode': 'rename', 'completed': len(tasks), 'updated': {k: str(v) for k, v in updated.items()}, 'failed': 0}
        except Exception:
            for item, temp_path, new_name in temp_pairs:
                original = item.path
                final_path = item.folder / new_name
                try:
                    if temp_path.exists():
                        safe_move_path(temp_path, original)
                    elif final_path.exists() and final_path != original:
                        safe_move_path(final_path, original)
                except Exception:
                    pass
            raise

    @staticmethod
    def _run_rename_tolerant(
        tasks: list[tuple[FileItem, str]],
        progress: Optional[Callable[[int, int, str], None]],
        failure_messages: list[str],
    ) -> dict[str, object]:
        total = max(len(tasks) * 2, 1)
        current = 0
        staged: list[tuple[FileItem, Path, str]] = []
        updated: dict[str, Path] = {}

        for idx, (item, new_name) in enumerate(tasks):
            temp_path = item.folder / f'{TEMP_PREFIX}{idx}__{item.name}'
            try:
                if temp_path.exists():
                    raise FileExistsError(f'临时文件名已存在：{temp_path}')
                safe_move_path(item.path, temp_path)
                staged.append((item, temp_path, new_name))
            except Exception as exc:
                failure_messages.append(FileManager._normalize_failure(item, new_name, exc))
            current += 1
            if progress is not None:
                progress(current, total, f'准备重命名：{item.name}')

        for item, temp_path, new_name in staged:
            final_path = item.folder / new_name
            try:
                if final_path.exists():
                    raise FileExistsError(f'目标文件已存在：{final_path}')
                safe_move_path(temp_path, final_path)
                updated[str(item.path).lower()] = final_path
            except Exception as exc:
                failure_messages.append(FileManager._normalize_failure(item, new_name, exc))
                try:
                    if temp_path.exists():
                        safe_move_path(temp_path, item.path)
                    elif final_path.exists() and final_path != item.path and str(item.path).lower() not in updated:
                        safe_move_path(final_path, item.path)
                except Exception:
                    pass
            current += 1
            if progress is not None:
                progress(current, total, f'正在写入：{new_name}')

        return {
            'mode': 'rename',
            'completed': len(updated),
            'updated': {k: str(v) for k, v in updated.items()},
            'failed': len(failure_messages),
        }

    @staticmethod
    def execute(
        tasks: list[tuple[FileItem, str]],
        mode: str,
        continue_on_error: bool,
        progress: Optional[Callable[[int, int, str], None]] = None,
        pre_errors: Optional[list[str]] = None,
    ) -> dict[str, object]:
        failure_messages = list(pre_errors or [])
        if mode == 'copy':
            result = FileManager._run_copy(tasks, continue_on_error, progress, failure_messages)
        elif continue_on_error:
            result = FileManager._run_rename_tolerant(tasks, progress, failure_messages)
        else:
            result = FileManager._run_rename_strict(tasks, progress)

        result['continue_on_error'] = continue_on_error
        result['pre_failed'] = len(pre_errors or [])
        result['failure_messages'] = failure_messages
        result['failed'] = len(failure_messages)
        return result

