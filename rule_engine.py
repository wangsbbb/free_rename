from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

INVALID_CHARS = set('\\/:*?"<>|')
MAX_SAFE_PATH_LEN = 240
WINDOWS_RESERVED_NAMES = {
    'CON', 'PRN', 'AUX', 'NUL',
    'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
    'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9',
}


@dataclass(frozen=True)
class FileItem:
    path: Path

    @property
    def folder(self) -> Path:
        return self.path.parent

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def ext(self) -> str:
        return self.path.suffix


@dataclass(frozen=True)
class RuleConfig:
    base_name: str
    start_num: int
    step: int
    digits: int
    position: str
    separator: str
    keep_ext: bool
    insert_enabled: bool
    insert_text: str
    insert_mode: str
    insert_index: int
    replace_enabled: bool
    replace_find: str
    replace_to: str
    replace_case_sensitive: bool
    replace_first_only: bool
    delete_enabled: bool
    delete_mode: str
    delete_text: str
    delete_start: int
    delete_length: int
    delete_prefix_count: int
    delete_suffix_count: int
    regex_enabled: bool
    regex_pattern: str
    regex_replace: str
    regex_ignore_case: bool
    filter_enabled: bool
    filter_ext_text: str
    filter_mode: str


@dataclass(frozen=True)
class PreviewRow:
    item: FileItem
    new_name: Optional[str]
    state: str
    ext: str
    folder: str


@dataclass(frozen=True)
class PreviewSummary:
    total: int
    ready: int
    skip: int
    duplicate: int
    error: int


class RuleEngine:
    @staticmethod
    def parse_exts(raw: str) -> set[str]:
        exts: set[str] = set()
        for part in raw.replace('；', ',').replace(' ', ',').split(','):
            item = part.strip().lower()
            if not item:
                continue
            if not item.startswith('.'):
                item = '.' + item
            exts.add(item)
        return exts

    @staticmethod
    def parse_int(value: str, field_name: str, minimum: Optional[int] = None) -> int:
        try:
            num = int(value)
        except ValueError as exc:
            raise ValueError(f'{field_name}必须是整数') from exc
        if minimum is not None and num < minimum:
            raise ValueError(f'{field_name}不能小于{minimum}')
        return num

    @staticmethod
    def sanitize_name(stem: str) -> str:
        cleaned = ''.join('_' if ch in INVALID_CHARS else ch for ch in stem)
        return cleaned.rstrip(' .')

    @staticmethod
    def is_windows_reserved_name(stem: str) -> bool:
        if not stem:
            return False
        return stem.upper() in WINDOWS_RESERVED_NAMES

    @staticmethod
    def get_compiled_regex(config: RuleConfig) -> Optional[tuple[re.Pattern[str], str]]:
        if not config.regex_enabled:
            return None
        pattern = config.regex_pattern.strip()
        if not pattern:
            return None
        flags = re.IGNORECASE if config.regex_ignore_case else 0
        return re.compile(pattern, flags), config.regex_replace

    @staticmethod
    def passes_filter(item: FileItem, config: RuleConfig) -> bool:
        if not config.filter_enabled:
            return True
        exts = RuleEngine.parse_exts(config.filter_ext_text)
        if not exts:
            return True
        matched = item.ext.lower() in exts
        return matched if config.filter_mode == '仅处理这些扩展名' else not matched

    @staticmethod
    def apply_insert(stem: str, config: RuleConfig) -> str:
        if not config.insert_enabled or not config.insert_text:
            return stem
        if config.insert_mode == '前面':
            return config.insert_text + stem
        if config.insert_mode == '后面':
            return stem + config.insert_text
        pos = max(0, min(len(stem), config.insert_index - 1))
        return stem[:pos] + config.insert_text + stem[pos:]

    @staticmethod
    def apply_replace(stem: str, config: RuleConfig) -> str:
        if not config.replace_enabled or config.replace_find == '':
            return stem
        if config.replace_case_sensitive:
            if config.replace_first_only:
                return stem.replace(config.replace_find, config.replace_to, 1)
            return stem.replace(config.replace_find, config.replace_to)
        pattern = re.escape(config.replace_find)
        count = 1 if config.replace_first_only else 0
        return re.sub(pattern, config.replace_to, stem, count=count, flags=re.IGNORECASE)

    @staticmethod
    def apply_delete(stem: str, config: RuleConfig) -> str:
        if not config.delete_enabled:
            return stem
        mode = config.delete_mode.strip()
        if mode == '删除文本':
            return stem.replace(config.delete_text, '') if config.delete_text else stem
        if mode == '按区间删除':
            start = max(config.delete_start - 1, 0)
            end = start + config.delete_length
            return stem[:start] + stem[end:]
        if mode == '删除前缀':
            return stem[config.delete_prefix_count:]
        if mode == '删除后缀':
            return stem[:-config.delete_suffix_count] if config.delete_suffix_count > 0 else stem
        return stem

    @staticmethod
    def apply_regex(stem: str, regex_rule: Optional[tuple[re.Pattern[str], str]]) -> str:
        if regex_rule is None:
            return stem
        compiled, repl = regex_rule
        return compiled.sub(repl, stem)

    @staticmethod
    def build_final_name(item: FileItem, seq_num: int, config: RuleConfig, regex_rule: Optional[tuple[re.Pattern[str], str]]) -> str:
        number_text = str(seq_num).zfill(config.digits)
        if config.base_name:
            if config.position == '前面':
                stem = f'{number_text}{config.separator}{config.base_name}'
            else:
                stem = f'{config.base_name}{config.separator}{number_text}'
        else:
            stem = number_text

        stem = RuleEngine.apply_insert(stem, config)
        stem = RuleEngine.apply_replace(stem, config)
        stem = RuleEngine.apply_delete(stem, config)
        stem = RuleEngine.apply_regex(stem, regex_rule)
        stem = RuleEngine.sanitize_name(stem)

        if not stem:
            raise ValueError('生成的新文件名为空')
        if RuleEngine.is_windows_reserved_name(stem):
            raise ValueError('目标文件名是 Windows 保留名称')

        final_name = stem + (item.ext if config.keep_ext else '')
        if len(str(item.folder / final_name)) >= MAX_SAFE_PATH_LEN:
            raise ValueError('目标路径过长')
        return final_name

    @staticmethod
    def generate_preview(files: list[FileItem], config: RuleConfig) -> list[PreviewRow]:
        regex_rule = RuleEngine.get_compiled_regex(config)
        rows: list[PreviewRow] = []
        seq_index = 0
        for item in files:
            if not RuleEngine.passes_filter(item, config):
                rows.append(PreviewRow(item=item, new_name=None, state='跳过', ext=item.ext or '-', folder=str(item.folder)))
                continue
            try:
                seq_num = config.start_num + seq_index * config.step
                new_name = RuleEngine.build_final_name(item, seq_num, config, regex_rule)
                state = '待处理'
                if new_name == item.name:
                    state = '跳过'
                rows.append(PreviewRow(item=item, new_name=new_name, state=state, ext=item.ext or '-', folder=str(item.folder)))
                seq_index += 1
            except Exception as exc:
                rows.append(PreviewRow(item=item, new_name=None, state=f'错误：{exc}', ext=item.ext or '-', folder=str(item.folder)))
        return rows

    @staticmethod
    def summarize(rows: list[PreviewRow]) -> tuple[PreviewSummary, dict[str, int]]:
        target_map: dict[str, int] = {}
        for row in rows:
            if row.new_name and row.state != '跳过':
                target = str(row.item.folder / row.new_name).lower()
                target_map[target] = target_map.get(target, 0) + 1

        ready = skip = duplicate = error = 0
        for row in rows:
            if row.new_name and row.state != '跳过' and target_map.get(str(row.item.folder / row.new_name).lower(), 0) > 1:
                duplicate += 1
            elif row.state == '跳过':
                skip += 1
            elif row.state.startswith('错误'):
                error += 1
            else:
                ready += 1
        return PreviewSummary(total=len(rows), ready=ready, skip=skip, duplicate=duplicate, error=error), target_map
