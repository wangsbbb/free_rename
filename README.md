# free_rename

一款开源的批量重命名软件，轻量，便捷，持续优化更新中。

当前版本：**1.0**

## 功能特点

- 批量导入文件、文件夹、递归导入
- 实时预览重命名结果
- 支持覆盖原文件名 / 另存为副本
- 检测重名冲突与非法文件名
- 支持导出预览列表
- 内置历史记录页面
- 自带 Windows 打包脚本与图标资源

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

## 上传到 GitHub 前后建议

1. 新建仓库后，把 `free_rename.py` 里的 `PROJECT_URL` 改成你的 GitHub 仓库地址。
2. 首次上传建议包含：源码、assets、README、requirements、bat 脚本。
3. `build/`、`dist/`、虚拟环境等目录已经在 `.gitignore` 中排除。

## 项目结构

```text
free_rename/
├─ assets/
│  └─ icons/
├─ free_rename.py
├─ free_rename.spec
├─ requirements_free_rename.txt
├─ run_free_rename.bat
├─ build_free_rename_exe.bat
├─ version_info.txt
├─ .gitignore
└─ README.md
```

## 说明

- 这个版本是整理后的 **GitHub 上传版 1.0**。
- 已去除原始打包日志里的本机路径信息。
- `free_rename.spec` 已改成相对路径写法，更适合仓库协作。

