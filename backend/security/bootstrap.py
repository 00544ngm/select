from __future__ import annotations

import logging
import secrets

from sqlalchemy import select

from backend.db.models import User
from backend.security.auth import hash_password

logger = logging.getLogger("backend")


async def ensure_seed_admin(session_factory, settings) -> None:
    """Create a first admin account when none exists (web/server mode only).

    The initial password comes from ``ADMIN_INITIAL_PASSWORD``; if unset, a
    random one is generated and logged once so the operator can log in and
    immediately change it.
    """
    if settings.runtime_mode == "desktop":
        return

    async with session_factory() as session:
        result = await session.execute(
            select(User).where(User.role == "admin").limit(1)
        )
        if result.scalars().first() is not None:
            return

        generated = not bool(settings.admin_initial_password)
        password = settings.admin_initial_password or secrets.token_urlsafe(12)
        password_hash, password_salt = hash_password(password)
        session.add(
            User(
                username="admin",
                password_hash=password_hash,
                password_salt=password_salt,
                role="admin",
                status="active",
                full_name="管理员",
                must_change_password=True,
            )
        )
        await session.commit()

    if generated:
        logger.warning(
            "已创建初始管理员账号 admin，随机初始密码为 %s（首次登录后请立即修改）",
            password,
        )


__all__ = ["ensure_seed_admin"]
