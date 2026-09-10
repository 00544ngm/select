# Desktop Phase 1 SQLite Data Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让现有后端在 PostgreSQL 与 SQLite 上遵守同一数据契约，并提供不修改旧库的迁移、校验和原子切换工具。

**Architecture:** 将数据库引擎创建从模块级全局变量提取为可注入工厂；模型继续使用 SQLAlchemy 跨方言类型。迁移工具从 PostgreSQL 只读导出到临时 SQLite，校验通过后才原子替换正式数据库。

**Tech Stack:** SQLAlchemy asyncio、asyncpg、aiosqlite、Alembic、Pydantic Settings、Pytest

---

### Task 1: 数据库运行模式与用户数据路径

**Files:**
- Create: `backend/desktop/__init__.py`
- Create: `backend/desktop/paths.py`
- Modify: `backend/config.py`
- Test: `backend/tests/test_desktop_paths.py`

- [ ] **Step 1: 写失败测试**

```python
def test_desktop_paths_use_local_app_data(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    paths = DesktopPaths.for_current_user()
    assert paths.data_dir == tmp_path / "组合选品控制台"
    assert paths.database_file == paths.data_dir / "data" / "bundling.db"
    assert paths.backup_dir == paths.data_dir / "backups"
```

- [ ] **Step 2: 验证 RED**

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_desktop_paths.py -q
```

预期：因 `backend.desktop.paths` 不存在而失败。

- [ ] **Step 3: 最小实现**

```python
@dataclass(frozen=True)
class DesktopPaths:
    data_dir: Path

    @classmethod
    def for_current_user(cls) -> "DesktopPaths":
        root = Path(os.environ["LOCALAPPDATA"]) / "组合选品控制台"
        return cls(data_dir=root)

    @property
    def database_file(self) -> Path:
        return self.data_dir / "data" / "bundling.db"

    @property
    def backup_dir(self) -> Path:
        return self.data_dir / "backups"
```

在 `BackendSettings` 增加 `runtime_mode: Literal["server", "desktop"] = "server"`；桌面入口显式传入 SQLite URL，不改变现有服务端默认值。

- [ ] **Step 4: 验证 GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_desktop_paths.py backend/tests/test_security.py -q
```

预期：通过。

- [ ] **Step 5: 写检查点记录**

在 `docs/优化迭代记录.md` 记录路径契约、测试结果和任何失败；不执行 Git 提交。

### Task 2: 可注入数据库引擎与 SQLite PRAGMA

**Files:**
- Create: `backend/db/engine.py`
- Modify: `backend/db/session.py`
- Test: `backend/tests/test_database_engine.py`

- [ ] **Step 1: 写失败测试**

```python
@pytest.mark.asyncio
async def test_sqlite_engine_enables_required_pragmas(tmp_path):
    engine = create_database_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with engine.connect() as connection:
        foreign_keys = await connection.scalar(text("PRAGMA foreign_keys"))
        journal_mode = await connection.scalar(text("PRAGMA journal_mode"))
        busy_timeout = await connection.scalar(text("PRAGMA busy_timeout"))
    assert foreign_keys == 1
    assert str(journal_mode).lower() == "wal"
    assert int(busy_timeout) >= 5000
```

- [ ] **Step 2: 验证 RED**

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_database_engine.py -q
```

预期：`create_database_engine` 尚不存在。

- [ ] **Step 3: 实现引擎工厂**

```python
def create_database_engine(url: str) -> AsyncEngine:
    engine = create_async_engine(url, pool_pre_ping=not url.startswith("sqlite"))
    if url.startswith("sqlite"):
        @event.listens_for(engine.sync_engine, "connect")
        def configure_sqlite(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()
    return engine
```

`backend/db/session.py` 用该工厂创建默认引擎，并提供 `create_session_factory(engine)` 给迁移工具和测试注入。

- [ ] **Step 4: 运行聚焦回归**

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_database_engine.py backend/tests/test_job_repository.py backend/tests/test_provider_repository.py -q
```

预期：SQLite PRAGMA 和现有 repository 测试通过。

### Task 3: SQLite Alembic 基线

**Files:**
- Modify: `backend/migrations/env.py`
- Create: `backend/desktop/migrations.py`
- Test: `backend/tests/test_sqlite_migrations.py`

- [ ] **Step 1: 写迁移失败测试**

```python
def test_upgrade_empty_sqlite_to_head_creates_all_tables(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'desktop.db'}"
    upgrade_database(url, "head")
    names = inspect_sqlite_tables(tmp_path / "desktop.db")
    assert {"analysis_jobs", "product_snapshots", "job_products", "artifacts",
            "provider_configurations", "provider_model_validations"} <= names
```

- [ ] **Step 2: 验证 RED**

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_sqlite_migrations.py -q
```

预期：升级帮助器不存在或 PostgreSQL 专属迁移不兼容。

- [ ] **Step 3: 实现可传 URL 的 Alembic 升级器**

```python
def upgrade_database(database_url: str, revision: str = "head") -> None:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, revision)
```

修正迁移中仅 PostgreSQL 支持的默认值或类型操作，但不得放宽字段、唯一约束和外键。

- [ ] **Step 4: 验证两种方言**

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_sqlite_migrations.py backend/tests/test_job_repository.py backend/tests/test_provider_repository.py -q
```

预期：SQLite 测试通过；现有 PostgreSQL 测试行为不变。

### Task 4: 只读导出与写入临时 SQLite

**Files:**
- Create: `backend/desktop/migration/__init__.py`
- Create: `backend/desktop/migration/exporter.py`
- Create: `backend/desktop/migration/importer.py`
- Create: `backend/desktop/migration/manifest.py`
- Test: `backend/tests/test_desktop_migration.py`

- [ ] **Step 1: 写失败测试**

```python
@pytest.mark.asyncio
async def test_migration_preserves_counts_ids_and_payloads(source_db, tmp_path):
    target = tmp_path / "candidate.db"
    manifest = await migrate_read_only(source_db.url, target)
    assert manifest.source_counts == manifest.target_counts
    assert manifest.target_counts["analysis_jobs"] == 2
    assert await read_result_payload(target, KNOWN_JOB_ID) == KNOWN_PAYLOAD
```

- [ ] **Step 2: 验证 RED**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_desktop_migration.py -q
```

预期：迁移模块不存在。

- [ ] **Step 3: 实现显式表顺序迁移**

```python
TABLE_ORDER = (
    "analysis_jobs",
    "product_snapshots",
    "job_products",
    "artifacts",
    "provider_configurations",
    "provider_model_validations",
)

async def migrate_read_only(source_url: str, target_file: Path) -> MigrationManifest:
    candidate = target_file.with_suffix(".candidate.db")
    upgrade_database(sqlite_url(candidate))
    async with source_session(source_url, readonly=True) as source, target_session(candidate) as target:
        for table in TABLE_ORDER:
            rows = await export_rows(source, table)
            await import_rows(target, table, rows)
        await target.commit()
    return await build_manifest(source_url, candidate)
```

导出和报告必须屏蔽 `encrypted_api_key`，密钥重加密由阶段四处理；迁移工具不得输出请求正文或模型完整回复。

- [ ] **Step 4: 验证正常、重复和中断场景**

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_desktop_migration.py -q
```

预期：正常迁移、目标已存在、导入中断和数量不一致用例全部通过。

### Task 5: 校验、备份与原子切换

**Files:**
- Create: `backend/desktop/migration/validator.py`
- Create: `backend/desktop/backup.py`
- Modify: `backend/desktop/migration/importer.py`
- Test: `backend/tests/test_desktop_backup.py`

- [ ] **Step 1: 写失败测试**

```python
def test_candidate_replaces_live_database_only_after_validation(tmp_path):
    live = tmp_path / "bundling.db"
    candidate = tmp_path / "bundling.candidate.db"
    live.write_bytes(b"old")
    candidate.write_bytes(b"new")
    promote_candidate(candidate, live, validation=ValidationResult(ok=False))
    assert live.read_bytes() == b"old"
```

- [ ] **Step 2: 验证 RED 后实现原子切换**

```python
def promote_candidate(candidate: Path, live: Path, validation: ValidationResult) -> None:
    if not validation.ok:
        raise MigrationValidationError(validation.errors)
    backup = live.with_suffix(".pre-migration.db")
    if live.exists():
        shutil.copy2(live, backup)
    os.replace(candidate, live)
```

- [ ] **Step 3: 验证失败绝不覆盖旧库**

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_desktop_backup.py backend/tests/test_desktop_migration.py -q
```

预期：校验失败、磁盘空间不足和替换失败均保留原库。

### Task 6: 阶段一全量门禁

**Files:**
- Create: `docs/verification/2026-08-02-desktop-phase-1.md`
- Modify: `docs/优化迭代记录.md`

- [ ] **Step 1: 运行全量验证**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check backend app tests
git diff --check
```

预期：测试和 Ruff 退出码 0；`git diff --check` 无空白错误。既有非阻断 warning 原样记录。

- [ ] **Step 2: 写验证报告**

报告必须列出 SQLite/PostgreSQL 契约、迁移计数、失败回滚测试和未删除旧数据的证据；不得包含密钥或模型正文。

