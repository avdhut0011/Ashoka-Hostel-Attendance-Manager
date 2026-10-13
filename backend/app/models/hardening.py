"""New supporting tables; no backfill of legacy application records."""
from datetime import datetime
from sqlalchemy import BigInteger, Integer, String, DateTime, Text, Index, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from backend.app.models.base import Base

class AttendanceRevision(Base):
    __tablename__ = 'AttendanceRevision'
    __table_args__ = {'schema': 'system'}
    RevisionId: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    Version: Mapped[int] = mapped_column(BigInteger, default=0)

class LoginThrottle(Base):
    __tablename__ = 'LoginThrottle'
    __table_args__ = (Index('IX_LoginThrottle_UpdatedAt', 'UpdatedAt'), {'schema': 'security'})
    BucketKey: Mapped[str] = mapped_column(String(64), primary_key=True)
    WindowStart: Mapped[datetime] = mapped_column(DateTime)
    Attempts: Mapped[int] = mapped_column(Integer)
    UpdatedAt: Mapped[datetime] = mapped_column(DateTime)

class RevokedToken(Base):
    __tablename__ = 'RevokedTokens'
    __table_args__ = (Index('IX_RevokedTokens_ExpiresAt', 'ExpiresAt'), {'schema': 'security'})
    TokenHash: Mapped[str] = mapped_column(String(64), primary_key=True)
    UserId: Mapped[int] = mapped_column(BigInteger, ForeignKey('security.Users.SystemUserId'))
    ExpiresAt: Mapped[datetime] = mapped_column(DateTime)

class SecurityAudit(Base):
    __tablename__ = 'SecurityAudit'
    __table_args__ = (Index('IX_SecurityAudit_CreatedAt', 'CreatedAt'), {'schema': 'security'})
    AuditId: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, 'sqlite'), primary_key=True, autoincrement=True)
    ActorId: Mapped[int] = mapped_column(BigInteger, ForeignKey('security.Users.SystemUserId'))
    TargetId: Mapped[int] = mapped_column(BigInteger, ForeignKey('security.Users.SystemUserId'))
    Action: Mapped[str] = mapped_column(String(60))
    Details: Mapped[str] = mapped_column(Text)
    CreatedAt: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
