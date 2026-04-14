# free_rename

一款开源的批量重命名软件，轻量，便捷，持续优化更新中。

当前版本：**1.0.5**

## 功能特点

- 批量导入文件、文件夹、递归导入
- 预览计算放入后台线程，连续输入会自动合并刷新请求
- 支持覆盖原文件名 / 另存为副本
- 支持“遇错继续”，跳过无效项和单文件失败项继续处理
- 自动识别未变化文件，并默认跳过
- 检测重名冲突、目标已存在、Windows 保留名称等风险
- 支持导出预览列表
- 主题、窗口状态、规则参数会自动记忆
- 支持外部 `styles/light.qss` 与 `styles/dark.qss`

## 运行环境

- Python 3.10 及以上
- Windows 10 / 11

## 本地运行

```bash
pip install -r requirements_free_rename.txt
python free_rename.py
```

Windows 下也可以直接双击：

- `run_free_rename.bat`

## 打包 EXE

项目内已附带 PyInstaller 打包脚本：

- `build_free_rename_exe.bat`

双击运行后，会在 `dist/` 目录生成：

- `free_rename.exe`

## 项目结构

```text
free_rename/
├─ assets/
│  └─ icons/
├─ styles/
│  ├─ light.qss
│  └─ dark.qss
├─ free_rename.py
├─ ui_main.py
├─ rule_engine.py
├─ file_manager.py
├─ free_rename.spec
├─ requirements_free_rename.txt
├─ run_free_rename.bat
├─ build_free_rename_exe.bat
├─ version_info.txt
├─ .gitignore
└─ README.md
```

## 1.0.5 更新内容
1. **工程结构拆分**：正式拆分为 `rule_engine.py`、`file_manager.py`、`ui_main.py`，主入口 `free_rename.py` 仅负责启动。
2. **单文件容错模式**：`遇错继续` 已真正接入执行流程，支持跳过预检查无效项，以及执行阶段单文件失败项。
3. **文件管理逻辑下沉**：导出列表、复制/重命名执行、跨盘移动降级逻辑统一放入 `FileManager`。
4. **规则引擎增强**：新增未变化文件自动跳过、Windows 保留名称校验。
5. **界面交互补强**：任务执行中会额外锁定模式切换和容错开关，避免处理中误改状态。

## 1.0.4 更新内容
1. **预览后台线程**：预览计算放入后台线程，文件较多时界面仍可保持响应。
2. **预览请求合并**：连续修改规则时自动合并多次预览请求，避免重复计算。
3. **规则结构拆分**：新增 `RuleConfig`、`PreviewRow`、`PreviewSummary`、`RuleEngine`，便于后续维护与扩展。
4. **规则持久化增强**：除主题和窗口信息外，规则参数也支持自动保存与恢复。
5. **QSS 外部化**：支持从 `styles/light.qss` 和 `styles/dark.qss` 读取样式，便于独立调整界面风格。
