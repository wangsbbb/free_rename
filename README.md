# free_rename

一款开源的批量重命名软件，轻量，便捷，持续优化更新中。

当前版本：**1.0.2**

## 功能特点

- 批量导入文件、文件夹、递归导入
- 实时预览重命名结果
- 支持覆盖原文件名 / 另存为副本
- 支持“遇错继续”，跳过冲突和无效项继续处理
- 自动识别未变化文件，并默认跳过
- 检测重名冲突、目标已存在、Windows 保留名称等风险
- 支持排序后再编号（当前顺序 / 文件名 / 修改时间 / 创建时间 / 扩展名）
- 支持导出预览列表
- 内置历史记录与设置页（默认主界面不展示侧边导航）
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
## 1.0.3 更新内容
1、预览防抖
-把原来“每次击键立刻全量预览”改成了 QTimer 防抖，默认 350ms。
-现在输入时不会每敲一个字就重算，参数暂时无效时也不会一直弹警告框。
2、执行放到后台线程
-新增 RenameWorker + QThread，重命名/复制不再阻塞主线程。
-界面现在会保持响应，并且加了进度条和状态文字。
3、执行中的交互保护
-任务执行时会禁用预览按钮、导出按钮、规则页和文件表格，避免处理中误操作。
-窗口关闭时如果任务还没结束，会拦截关闭并提示。
4、设置持久化
用了 QSettings 保存这些内容：
-主题模式
-窗口几何信息
-上次打开目录
-文件选择和导出现在会记住上一次路径。
5、类型提示顺手整理
-把 List[...] / Dict[...] / Tuple[...] 改成了内置 list[...] / dict[...] / tuple[...] 写法，兼容你现在这个 __future__ 版本。


## 1.0.2 更新内容

1、正则预编译
新增 _get_compiled_regex()，在 generate_preview() 开始时先编译一次，再传给每个文件的生成流程，避免对每个文件重复编译正则。
2、重命名更稳
新增 _move_path()，优先 os.rename()，失败后自动降级到 shutil.move()。这样即使后续出现跨盘、特殊文件系统、或某些 rename 失败场景，也更稳。重命名主流程和回滚流程都改成统一走这个封装了。
3、CSV 导出改为标准库
不再手拼引号，改用 csv.writer，能正确处理逗号、双引号、换行。