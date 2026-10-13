-- Empty database setup only. Existing production upgrades use database.migrate_production.
GO
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'attendance') EXEC('CREATE SCHEMA [attendance]');
GO
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'integration') EXEC('CREATE SCHEMA [integration]');
GO
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'master') EXEC('CREATE SCHEMA [master]');
GO
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'security') EXEC('CREATE SCHEMA [security]');
GO
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'system') EXEC('CREATE SCHEMA [system]');
GO

CREATE TABLE integration.[QuarantinedPunches] (
	[QuarantineId] BIGINT NOT NULL IDENTITY, 
	[SourceDeviceLogId] BIGINT NOT NULL, 
	[DeviceId] INTEGER NULL, 
	[UserId] VARCHAR(50) NULL, 
	[LogDate] DATETIME NULL, 
	[DownloadDate] DATETIME NULL, 
	[RawPayload] VARCHAR(1000) NULL, 
	[ErrorType] VARCHAR(50) NOT NULL, 
	[ErrorMessage] VARCHAR(2000) NOT NULL, 
	[QuarantinedAt] DATETIME NOT NULL, 
	[ResolvedStatus] VARCHAR(20) NOT NULL, 
	[ResolvedAt] DATETIME NULL, 
	[ResolvedBy] VARCHAR(100) NULL, 
	PRIMARY KEY ([QuarantineId])
)


GO
CREATE INDEX [ix_integration_QuarantinedPunches_SourceDeviceLogId] ON integration.[QuarantinedPunches] ([SourceDeviceLogId])
GO

CREATE TABLE integration.[RawPunches] (
	[RawPunchId] BIGINT NOT NULL IDENTITY, 
	[SourceDeviceLogId] BIGINT NOT NULL, 
	[DeviceId] INTEGER NOT NULL, 
	[UserId] VARCHAR(50) NOT NULL, 
	[LogDate] DATETIME NOT NULL, 
	[DownloadDate] DATETIME NULL, 
	[ReceivedAt] DATETIME NOT NULL, 
	PRIMARY KEY ([RawPunchId])
)


GO
CREATE INDEX [IX_RawPunches_UserId_LogDate] ON integration.[RawPunches] ([UserId], [LogDate])
GO
CREATE UNIQUE INDEX [ix_integration_RawPunches_SourceDeviceLogId] ON integration.[RawPunches] ([SourceDeviceLogId])
GO

CREATE TABLE integration.[RecoveryScans] (
	[ScanId] BIGINT NOT NULL IDENTITY, 
	[StartDate] DATETIME NOT NULL, 
	[EndDate] DATETIME NOT NULL, 
	[SourceWatermark] BIGINT NOT NULL, 
	[LastScannedSourceId] BIGINT NOT NULL, 
	[ScannedCount] INTEGER NOT NULL, 
	[CandidateCount] INTEGER NOT NULL, 
	[UnknownStudentCount] INTEGER NOT NULL, 
	[Status] VARCHAR(20) NOT NULL, 
	[RequestedBy] VARCHAR(100) NOT NULL, 
	[CreatedAt] DATETIME NOT NULL, 
	[CompletedAt] DATETIME NULL, 
	PRIMARY KEY ([ScanId])
)


GO

CREATE TABLE integration.[SyncCheckpoint] (
	[SyncId] INTEGER NOT NULL IDENTITY, 
	[SourceName] VARCHAR(100) NOT NULL, 
	[LastSourceDeviceLogId] BIGINT NOT NULL, 
	[LastSyncStartedAt] DATETIME NULL, 
	[LastSyncCompletedAt] DATETIME NULL, 
	[LastSyncStatus] VARCHAR(20) NULL, 
	[LastError] VARCHAR(2000) NULL, 
	[UpdatedAt] DATETIME NOT NULL, 
	PRIMARY KEY ([SyncId]), 
	UNIQUE ([SourceName])
)


GO

CREATE TABLE master.[Hostels] (
	[HostelId] INTEGER NOT NULL IDENTITY, 
	[HostelName] VARCHAR(100) NOT NULL, 
	[HostelCode] VARCHAR(50) NULL, 
	[IsActive] BIT NOT NULL, 
	[CreatedAt] DATETIME NOT NULL, 
	[UpdatedAt] DATETIME NOT NULL, 
	PRIMARY KEY ([HostelId])
)


GO

CREATE TABLE security.[LoginThrottle] (
	[BucketKey] VARCHAR(64) NOT NULL, 
	[WindowStart] DATETIME NOT NULL, 
	[Attempts] INTEGER NOT NULL, 
	[UpdatedAt] DATETIME NOT NULL, 
	PRIMARY KEY ([BucketKey])
)


GO
CREATE INDEX [IX_LoginThrottle_UpdatedAt] ON security.[LoginThrottle] ([UpdatedAt])
GO

CREATE TABLE system.[AttendanceChanges] (
	[ChangeId] BIGINT NOT NULL IDENTITY, 
	[CreatedAt] DATETIME NOT NULL, 
	PRIMARY KEY ([ChangeId])
)


GO

CREATE TABLE system.[AttendanceRevision] (
	[RevisionId] INTEGER NOT NULL, 
	[Version] BIGINT NOT NULL, 
	PRIMARY KEY ([RevisionId])
)


GO

CREATE TABLE system.[SystemEvents] (
	[EventId] BIGINT NOT NULL IDENTITY, 
	[EventType] VARCHAR(100) NOT NULL, 
	[Description] VARCHAR(1000) NULL, 
	[CreatedAt] DATETIME NOT NULL, 
	[CreatedBy] VARCHAR(100) NULL, 
	PRIMARY KEY ([EventId])
)


GO

CREATE TABLE integration.[PunchCorrections] (
	[CorrectionId] BIGINT NOT NULL IDENTITY, 
	[RawPunchId] BIGINT NOT NULL, 
	[UserId] VARCHAR(50) NOT NULL, 
	[DeviceId] INTEGER NOT NULL, 
	[LogDate] DATETIME NOT NULL, 
	[Reason] VARCHAR(500) NOT NULL, 
	[CreatedBy] VARCHAR(100) NOT NULL, 
	[CreatedAt] DATETIME NOT NULL, 
	PRIMARY KEY ([CorrectionId]), 
	FOREIGN KEY([RawPunchId]) REFERENCES integration.[RawPunches] ([RawPunchId])
)


GO
CREATE INDEX [ix_integration_PunchCorrections_RawPunchId] ON integration.[PunchCorrections] ([RawPunchId])
GO

CREATE TABLE master.[Devices] (
	[DeviceId] INTEGER NOT NULL, 
	[DeviceName] VARCHAR(100) NOT NULL, 
	[HostelId] INTEGER NULL, 
	[IsActive] BIT NOT NULL, 
	[CreatedAt] DATETIME NOT NULL, 
	[UpdatedAt] DATETIME NOT NULL, 
	PRIMARY KEY ([DeviceId]), 
	FOREIGN KEY([HostelId]) REFERENCES master.[Hostels] ([HostelId])
)


GO

CREATE TABLE master.[Students] (
	[StudentId] BIGINT NOT NULL IDENTITY, 
	[UserId] VARCHAR(50) NOT NULL, 
	[StudentName] VARCHAR(150) NULL, 
	[HostelId] INTEGER NULL, 
	[RoomNo] VARCHAR(50) NULL, 
	[RegistrationDate] DATETIME NOT NULL, 
	[RegistrationStatus] VARCHAR(20) NOT NULL, 
	[EnrolledAt] DATETIME NULL, 
	[DeactivatedAt] DATETIME NULL, 
	[DeactivationReason] VARCHAR(500) NULL, 
	[CreatedAt] DATETIME NOT NULL, 
	[UpdatedAt] DATETIME NOT NULL, 
	PRIMARY KEY ([StudentId]), 
	FOREIGN KEY([HostelId]) REFERENCES master.[Hostels] ([HostelId])
)


GO
CREATE UNIQUE INDEX [ix_master_Students_UserId] ON master.[Students] ([UserId])
GO

CREATE TABLE security.[Users] (
	[SystemUserId] BIGINT NOT NULL IDENTITY, 
	[Username] VARCHAR(100) NOT NULL, 
	[PasswordHash] VARCHAR(500) NOT NULL, 
	[Role] VARCHAR(30) NOT NULL, 
	[HostelId] INTEGER NULL, 
	[IsActive] BIT NOT NULL, 
	[CreatedAt] DATETIME NOT NULL, 
	[UpdatedAt] DATETIME NOT NULL, 
	[TokenVersion] INTEGER NULL, 
	PRIMARY KEY ([SystemUserId]), 
	FOREIGN KEY([HostelId]) REFERENCES master.[Hostels] ([HostelId])
)


GO
CREATE UNIQUE INDEX [ix_security_Users_Username] ON security.[Users] ([Username])
GO

CREATE TABLE attendance.[AttendanceOverrides] (
	[OverrideId] BIGINT NOT NULL IDENTITY, 
	[StudentId] BIGINT NOT NULL, 
	[PreviousStatus] VARCHAR(20) NOT NULL, 
	[CurrentStatus] VARCHAR(20) NOT NULL, 
	[EffectiveAt] DATETIME NOT NULL, 
	[Reason] VARCHAR(500) NOT NULL, 
	[CreatedBy] VARCHAR(100) NOT NULL, 
	[CreatedAt] DATETIME NOT NULL, 
	[HostelIdSnapshot] INTEGER NULL, 
	[RoomNoSnapshot] VARCHAR(50) NULL, 
	PRIMARY KEY ([OverrideId]), 
	FOREIGN KEY([StudentId]) REFERENCES master.[Students] ([StudentId])
)


GO
CREATE INDEX [IX_AttendanceOverrides_Student_Time] ON attendance.[AttendanceOverrides] ([StudentId], [EffectiveAt])
GO

CREATE TABLE attendance.[ProcessedPunches] (
	[PunchId] BIGINT NOT NULL IDENTITY, 
	[RawPunchId] BIGINT NOT NULL, 
	[StudentId] BIGINT NULL, 
	[UserId] VARCHAR(50) NOT NULL, 
	[DeviceId] INTEGER NOT NULL, 
	[LogDate] DATETIME NOT NULL, 
	[PunchType] VARCHAR(20) NULL, 
	[ProcessingStatus] VARCHAR(30) NOT NULL, 
	[IsFirstEverPunch] BIT NOT NULL, 
	[IsFirstValidPunchOfDay] BIT NOT NULL, 
	[PreviousStatus] VARCHAR(20) NULL, 
	[Reason] VARCHAR(500) NULL, 
	[ProcessedAt] DATETIME NOT NULL, 
	[HostelIdSnapshot] INTEGER NULL, 
	[RoomNoSnapshot] VARCHAR(50) NULL, 
	PRIMARY KEY ([PunchId]), 
	FOREIGN KEY([RawPunchId]) REFERENCES integration.[RawPunches] ([RawPunchId]), 
	FOREIGN KEY([StudentId]) REFERENCES master.[Students] ([StudentId])
)


GO
CREATE INDEX [IX_ProcessedPunches_LogDate] ON attendance.[ProcessedPunches] ([LogDate])
GO
CREATE INDEX [IX_ProcessedPunches_StudentId_LogDate] ON attendance.[ProcessedPunches] ([StudentId], [LogDate])
GO
CREATE INDEX [IX_Punches_Hostel_Time_Id] ON attendance.[ProcessedPunches] ([HostelIdSnapshot], [LogDate], [PunchId]) INCLUDE ([StudentId], [UserId], [ProcessingStatus], [PunchType], [DeviceId])
GO
CREATE INDEX [IX_Punches_Student_Time_Id] ON attendance.[ProcessedPunches] ([StudentId], [LogDate], [PunchId]) INCLUDE ([ProcessingStatus], [PunchType], [RawPunchId])
GO
CREATE UNIQUE INDEX [UX_ProcessedPunches_RawPunchId] ON attendance.[ProcessedPunches] ([RawPunchId])
GO

CREATE TABLE integration.[RecoveryPunches] (
	[RecoveryId] BIGINT NOT NULL IDENTITY, 
	[ScanId] BIGINT NOT NULL, 
	[SourceDeviceLogId] BIGINT NOT NULL, 
	[StudentId] BIGINT NOT NULL, 
	[UserId] VARCHAR(50) NOT NULL, 
	[DeviceId] INTEGER NOT NULL, 
	[LogDate] DATETIME NOT NULL, 
	[DownloadDate] DATETIME NULL, 
	[ReviewStatus] VARCHAR(20) NOT NULL, 
	[Reason] VARCHAR(500) NOT NULL, 
	[CapturedAt] DATETIME NOT NULL, 
	[ReviewedBy] VARCHAR(100) NULL, 
	[ReviewedAt] DATETIME NULL, 
	[ReviewNote] VARCHAR(500) NULL, 
	PRIMARY KEY ([RecoveryId]), 
	FOREIGN KEY([ScanId]) REFERENCES integration.[RecoveryScans] ([ScanId]), 
	UNIQUE ([SourceDeviceLogId]), 
	FOREIGN KEY([StudentId]) REFERENCES master.[Students] ([StudentId])
)


GO
CREATE INDEX [ix_integration_RecoveryPunches_ScanId] ON integration.[RecoveryPunches] ([ScanId])
GO
CREATE INDEX [ix_integration_RecoveryPunches_StudentId] ON integration.[RecoveryPunches] ([StudentId])
GO

CREATE TABLE master.[DeviceStateHistory] (
	[StateId] BIGINT NOT NULL IDENTITY, 
	[DeviceId] INTEGER NOT NULL, 
	[HostelId] INTEGER NULL, 
	[IsActive] BIT NOT NULL, 
	[EffectiveFrom] DATETIME NULL, 
	[EffectiveTo] DATETIME NULL, 
	PRIMARY KEY ([StateId]), 
	FOREIGN KEY([DeviceId]) REFERENCES master.[Devices] ([DeviceId])
)


GO
CREATE INDEX [ix_master_DeviceStateHistory_DeviceId] ON master.[DeviceStateHistory] ([DeviceId])
GO

CREATE TABLE master.[StudentHostelHistory] (
	[HistoryId] BIGINT NOT NULL IDENTITY, 
	[StudentId] BIGINT NOT NULL, 
	[HostelId] INTEGER NOT NULL, 
	[RoomNo] VARCHAR(50) NULL, 
	[FromDate] DATETIME NOT NULL, 
	[ToDate] DATETIME NULL, 
	[CreatedAt] DATETIME NOT NULL, 
	PRIMARY KEY ([HistoryId]), 
	FOREIGN KEY([StudentId]) REFERENCES master.[Students] ([StudentId]), 
	FOREIGN KEY([HostelId]) REFERENCES master.[Hostels] ([HostelId])
)


GO

CREATE TABLE master.[StudentStateHistory] (
	[StateId] BIGINT NOT NULL IDENTITY, 
	[StudentId] BIGINT NOT NULL, 
	[HostelId] INTEGER NULL, 
	[RoomNo] VARCHAR(50) NULL, 
	[RegistrationStatus] VARCHAR(20) NOT NULL, 
	[EffectiveFrom] DATETIME NULL, 
	[EffectiveTo] DATETIME NULL, 
	PRIMARY KEY ([StateId]), 
	FOREIGN KEY([StudentId]) REFERENCES master.[Students] ([StudentId])
)


GO
CREATE INDEX [ix_master_StudentStateHistory_StudentId] ON master.[StudentStateHistory] ([StudentId])
GO

CREATE TABLE master.[VerifiedRoomChanges] (
	[ChangeId] BIGINT NOT NULL IDENTITY, 
	[StudentId] BIGINT NOT NULL, 
	[OldRoomNo] VARCHAR(50) NOT NULL, 
	[NewRoomNo] VARCHAR(50) NOT NULL, 
	[ChangeDate] DATETIME NOT NULL, 
	[EffectiveAt] DATETIME NULL, 
	[Evidence] VARCHAR(1000) NOT NULL, 
	[RecordedBy] VARCHAR(100) NOT NULL, 
	[RecordedAt] DATETIME NOT NULL, 
	PRIMARY KEY ([ChangeId]), 
	CONSTRAINT [UQ_VerifiedRoomChanges_Student_Date] UNIQUE ([StudentId], [ChangeDate]), 
	FOREIGN KEY([StudentId]) REFERENCES master.[Students] ([StudentId])
)


GO
CREATE INDEX [ix_master_VerifiedRoomChanges_StudentId] ON master.[VerifiedRoomChanges] ([StudentId])
GO

CREATE TABLE security.[RevokedTokens] (
	[TokenHash] VARCHAR(64) NOT NULL, 
	[UserId] BIGINT NOT NULL, 
	[ExpiresAt] DATETIME NOT NULL, 
	PRIMARY KEY ([TokenHash]), 
	FOREIGN KEY([UserId]) REFERENCES security.[Users] ([SystemUserId])
)


GO
CREATE INDEX [IX_RevokedTokens_ExpiresAt] ON security.[RevokedTokens] ([ExpiresAt])
GO

CREATE TABLE security.[SecurityAudit] (
	[AuditId] BIGINT NOT NULL IDENTITY, 
	[ActorId] BIGINT NOT NULL, 
	[TargetId] BIGINT NOT NULL, 
	[Action] VARCHAR(60) NOT NULL, 
	[Details] TEXT NOT NULL, 
	[CreatedAt] DATETIME NOT NULL, 
	PRIMARY KEY ([AuditId]), 
	FOREIGN KEY([ActorId]) REFERENCES security.[Users] ([SystemUserId]), 
	FOREIGN KEY([TargetId]) REFERENCES security.[Users] ([SystemUserId])
)


GO
CREATE INDEX [IX_SecurityAudit_CreatedAt] ON security.[SecurityAudit] ([CreatedAt])
GO

CREATE TABLE attendance.[StudentCurrentStatus] (
	[StudentId] BIGINT NOT NULL, 
	[CurrentStatus] VARCHAR(20) NOT NULL, 
	[LastPunchId] BIGINT NULL, 
	[LastPunchTime] DATETIME NULL, 
	[LastPunchType] VARCHAR(20) NULL, 
	[LastValidAttendanceDate] DATETIME NULL, 
	[CounterDate] DATETIME NULL, 
	[TodayInCount] INTEGER NOT NULL, 
	[TodayOutCount] INTEGER NOT NULL, 
	[TodayValidPunchCount] INTEGER NOT NULL, 
	[TodayDuplicatePunchCount] INTEGER NOT NULL, 
	[UpdatedAt] DATETIME NOT NULL, 
	PRIMARY KEY ([StudentId]), 
	FOREIGN KEY([StudentId]) REFERENCES master.[Students] ([StudentId]), 
	FOREIGN KEY([LastPunchId]) REFERENCES attendance.[ProcessedPunches] ([PunchId])
)


GO
CREATE INDEX [IX_CurrentStatus_Status_Time] ON attendance.[StudentCurrentStatus] ([CurrentStatus], [LastPunchTime], [StudentId])
GO
