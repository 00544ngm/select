from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import ApiGroup, User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_username(self, username: str) -> User | None:
        result = await self._session.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()

    async def get(self, user_id: UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def list_all(self) -> list[User]:
        result = await self._session.execute(
            select(User).order_by(User.created_at, User.username)
        )
        return list(result.scalars().all())

    async def count_active_admins(self, exclude_id: UUID | None = None) -> int:
        statement = select(func.count()).where(
            User.role == "admin", User.status == "active"
        )
        if exclude_id is not None:
            statement = statement.where(User.id != exclude_id)
        result = await self._session.execute(statement)
        return int(result.scalar_one())

    async def add(self, user: User) -> User:
        self._session.add(user)
        await self._session.commit()
        await self._session.refresh(user)
        return user

    async def save(self, user: User) -> User:
        await self._session.commit()
        await self._session.refresh(user)
        return user

    async def delete(self, user: User) -> None:
        await self._session.delete(user)
        await self._session.commit()


class ApiGroupRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, group_id: UUID) -> ApiGroup | None:
        return await self._session.get(ApiGroup, group_id)

    async def list_all(self) -> list[ApiGroup]:
        result = await self._session.execute(
            select(ApiGroup).order_by(ApiGroup.created_at, ApiGroup.name)
        )
        return list(result.scalars().all())

    async def add(self, group: ApiGroup) -> ApiGroup:
        self._session.add(group)
        await self._session.commit()
        await self._session.refresh(group)
        return group

    async def save(self, group: ApiGroup) -> ApiGroup:
        await self._session.commit()
        await self._session.refresh(group)
        return group


__all__ = ["ApiGroupRepository", "UserRepository"]
