# Changelog

## 1.0.6

- 预览表格切换为 `QTableView + QAbstractTableModel`
- 文件夹扫描改为后台线程执行
- 执行阶段直接复用当前预览结果，不再同步重算规则
- 新增 `workers.py`，进一步分离 Worker 与文件管理逻辑
- 打包脚本与 spec 增加 `styles/` 资源

## 1.0.5

- 正式拆分为 `rule_engine.py`、`file_manager.py`、`ui_main.py`
- `遇错继续` 进入单文件容错模式
- 文件操作进一步下沉到 `FileManager`

## 1.0

- 整理为可直接上传 GitHub 的源码结构
- 统一版本号为 1.0
- 清理本机绝对路径与构建日志残留
- 重写 `free_rename.spec` 为相对路径
- 新增 `.gitignore`、`README.md`、`version_info.txt`
- 保留图标资源与 Windows 运行 / 打包脚本
