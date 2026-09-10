# Windows 桌面版 Phase 1 验证报告

## 结论

Phase 1 的 SQLite 数据契约、只读迁移、候选校验、WAL 一致备份和原子切换原语已完成。Task 5 第三轮独立规格复核通过。

## 自动化证据

- 后端全量：`592 passed, 9 skipped, 1 warning in 28.45s`。
- Task 5 最终聚焦与相关回归：72 项通过。
- Task 1-5 新增/修改 Python 文件限定 Ruff：通过。
- 限定 `git diff --check`：通过。
- 全仓库 Ruff：未通过，存在 81 项既有静态检查债务；未在本阶段进行无关批量重构。

## 数据与迁移契约

- 桌面 SQLite 使用外键、WAL 和 busy timeout。
- Alembic 可将空 SQLite 升级到 head，并保持六张既有业务表的字段、索引、唯一约束和外键。
- PostgreSQL 导出使用只读 repeatable-read 快照；源计数与六表读取处于同一事务。
- 候选数据库使用独占创建，不覆盖其他候选文件；失败候选保留用于诊断。
- Manifest 只公开文件名、计数、schema 版本和时间，不包含绝对路径、密钥或模型正文。
- 候选校验覆盖计数、SQLite quick check、外键、schema 版本和历史结果 JSON 可读性。
- 正式切换前使用 SQLite backup API 保存包含未 checkpoint WAL 提交的数据；备份不可覆盖。
- 校验后候选文件或 Sidecar 变化会阻断切换；替换、空间、备份或清理失败不宣称成功。

## 未删除旧数据的证据

- 自动化用例覆盖校验失败、空间不足、备份失败、替换失败和 Sidecar 变化，正式库均保持可恢复。
- 本阶段没有连接或修改用户 PostgreSQL 数据库，没有运行真实迁移，没有删除任何旧数据。

## 已知限制与下一阶段前置条件

- Windows 无法在仍持有 SQLite 文件句柄时执行 `os.replace`；实现使用全链路 `database_write_guard` 配合短生命周期 SQLite 写入检查。
- Phase 2/3 必须让所有桌面数据库写入口遵守同一 guard，或在切换前停止写入并关闭受控连接。
- 尚未在受控真实 PostgreSQL 环境执行迁移演练；当前 PostgreSQL 事务语义由隔离测试覆盖。
- readiness 用例仍有一条既有异步资源 warning；不影响本阶段测试结果，但保留为后续清理项。
