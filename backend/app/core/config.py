from pathlib import Path
from typing import Optional
import re
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(Path(__file__).resolve().parents[2] / '.env'), extra='ignore')
    APP_ENV: str = 'development'
    PROJECT_NAME: str = 'Hostel Attendance Management System'
    SOURCE_DB_HOST: str = ''
    SOURCE_DB_PORT: int = 1433
    SOURCE_DB_NAME: str = 'Epush'
    SOURCE_DB_USER: str = ''
    SOURCE_DB_PASSWORD: str = ''
    SOURCE_TABLE: str = 'Devicelogs_Processed'
    SOURCE_DATABASE_URL: Optional[str] = None
    TARGET_DB_HOST: str = r'MISISC\SQLEXPRESS'
    TARGET_DB_PORT: int = 1433
    TARGET_DB_NAME: str = 'HostelAttendance'
    TARGET_DB_USER: str = ''
    TARGET_DB_PASSWORD: str = ''
    TARGET_DATABASE_URL: Optional[str] = None
    SYNC_INTERVAL_SECONDS: int = 10
    DUPLICATE_WINDOW_SECONDS: int = 45
    SYNC_STALE_SECONDS: int = 120
    APP_TIMEZONE: str = 'Asia/Kolkata'
    SOURCE_TIMEZONE: str = 'Asia/Kolkata'
    TEST_DATABASE_DIR: Optional[str] = None
    ISOLATED_TEST_DATABASE: Optional[str] = None
    JWT_SECRET: str = ''
    JWT_ALGORITHM: str = 'HS256'
    JWT_EXPIRATION_MINUTES: int = 1440
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 5
    DB_POOL_TIMEOUT_SECONDS: int = 15
    DB_QUERY_TIMEOUT_SECONDS: int = 30
    REPORT_CONCURRENCY: int = 1
    MAX_FUTURE_PUNCH_SECONDS: int = 300
    ALLOWED_HOSTS: str = '*'
    DB_ENCRYPT: str = 'yes'
    DB_TRUST_SERVER_CERTIFICATE: str = 'no'
    ALLOWED_ORIGINS: str = 'http://localhost:5173,http://localhost:3000,http://127.0.0.1:3000'

    @model_validator(mode='after')
    def validate_settings(self):
        for field in ('APP_TIMEZONE', 'SOURCE_TIMEZONE'):
            if getattr(self, field) not in ('Asia/Kolkata', 'Asia/Calcutta'):
                raise ValueError('Attendance and biometric timestamps must use Asia/Kolkata')
            setattr(self, field, 'Asia/Kolkata')
        if len(self.JWT_SECRET) < 32:
            raise ValueError('JWT_SECRET must be supplied and contain at least 32 characters')
        if self.SYNC_INTERVAL_SECONDS < 1 or self.DUPLICATE_WINDOW_SECONDS < 0:
            raise ValueError('Invalid synchronization or duplicate interval')
        if min(self.DB_POOL_SIZE, self.DB_POOL_TIMEOUT_SECONDS, self.DB_QUERY_TIMEOUT_SECONDS, self.REPORT_CONCURRENCY) < 1 or min(self.DB_MAX_OVERFLOW, self.MAX_FUTURE_PUNCH_SECONDS) < 0:
            raise ValueError('Invalid database/concurrency limits')
        if self.JWT_ALGORITHM != 'HS256':
            raise ValueError('This deployment supports HS256 tokens only')
        if self.APP_ENV == 'production' and any(marker in self.JWT_SECRET.lower() for marker in ('super_secret', 'change_me', 'change_in_prod')):
            raise ValueError('Production requires a randomly generated JWT_SECRET')
        if self.APP_ENV == 'production' and ('*' in [value.strip() for value in self.ALLOWED_HOSTS.split(',')]
                or '*' in self.get_allowed_origins()):
            raise ValueError('Production requires explicit allowed hosts and origins')
        target = make_url(self.get_target_db_url())
        if target.get_backend_name() != 'sqlite' and (target.database or '').lower() != 'hostelattendance':
            isolated = (self.APP_ENV == 'sqlserver_test' and self.ISOLATED_TEST_DATABASE == target.database
                        and re.fullmatch(r'HostelAttendance_Test_[0-9a-f]{32}', target.database or '')
                        and (target.host or '').lower() != '192.168.9.6')
            if not isolated:
                raise ValueError('Target must be HostelAttendance or an explicitly named disposable SQL Server test database')
        if self.APP_ENV == 'sqlserver_test':
            if (not re.fullmatch(r'HostelAttendance_Test_[0-9a-f]{32}', self.ISOLATED_TEST_DATABASE or '')
                    or target.database != self.ISOLATED_TEST_DATABASE):
                raise ValueError('SQL Server test mode must never target HostelAttendance or an existing production database')
            source = make_url(self.get_source_db_url())
            if source.database != self.ISOLATED_TEST_DATABASE or source.host != target.host:
                raise ValueError('Isolated SQL Server tests require source and target in the same disposable database')
        return self

    def get_allowed_origins(self):
        return [value.strip() for value in self.ALLOWED_ORIGINS.split(',') if value.strip()]

    def _url(self, source):
        prefix = 'SOURCE' if source else 'TARGET'
        supplied = getattr(self, prefix + '_DATABASE_URL')
        if supplied:
            return supplied
        user = getattr(self, prefix + '_DB_USER') or None
        host = getattr(self, prefix + '_DB_HOST')
        return URL.create('mssql+pyodbc', username=user,
            password=getattr(self, prefix + '_DB_PASSWORD') if user else None,
            host=host, port=None if '\\' in host else getattr(self, prefix + '_DB_PORT'),
            database=getattr(self, prefix + '_DB_NAME'),
            query={'driver': 'ODBC Driver 17 for SQL Server', 'Encrypt': self.DB_ENCRYPT, 'TrustServerCertificate': self.DB_TRUST_SERVER_CERTIFICATE,
                   **({'trusted_connection': 'yes'} if not user else {})}).render_as_string(hide_password=False)

    def get_target_db_url(self):
        return self._url(False)

    def get_source_db_url(self):
        return self._url(True)

settings = Settings()
