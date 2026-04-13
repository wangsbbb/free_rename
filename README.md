# free_rename

一款开源的批量重命名软件，轻量，便捷，持续优化更新中。

当前版本：**1.0.1**

## 功能特点

- 批量导入文件、文件夹、递归导入
- 实时预览重命名结果
- 支持覆盖原文件名 / 另存为副本
- 支持“遇错继续”，跳过冲突和无效项继续处理
- 自动识别未变化文件，并默认跳过
- 检测重名冲突、目标已存在、Windows 保留名称等风险
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

## 1.0.1 更新内容

- 接通“遇错继续”逻辑
- 首页统计拆分为可处理 / 跳过 / 冲突 / 错误
- 新增“未变化”状态，默认不重复处理
- 新增 Windows 保留名称校验
- 预览配置错误改为界面内提示，减少频繁弹窗

