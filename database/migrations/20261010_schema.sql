-- Use python -m database.migrate_production --apply to execute with transactional checks.
IF DB_NAME() <> N'HostelAttendance' THROW 51000, 'Wrong target database', 1;

CREATE TABLE integration.[RecoveryScans] (
	[ScanId] BIGINT NOT NULL IDENTITY, 
	[StartDate] DATE NOT NULL, 
	[EndDate] DATE NOT NULL, 
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

CREATE TABLE master.[VerifiedRoomChanges] (
	[ChangeId] BIGINT NOT NULL IDENTITY, 
	[StudentId] BIGINT NOT NULL, 
	[OldRoomNo] VARCHAR(50) NOT NULL, 
	[NewRoomNo] VARCHAR(50) NOT NULL, 
	[ChangeDate] DATE NOT NULL, 
	[EffectiveAt] DATETIME NULL, 
	[Evidence] VARCHAR(1000) NOT NULL, 
	[RecordedBy] VARCHAR(100) NOT NULL, 
	[RecordedAt] DATETIME NOT NULL, 
	PRIMARY KEY ([ChangeId]), 
	CONSTRAINT [UQ_VerifiedRoomChanges_Student_Date] UNIQUE ([StudentId], [ChangeDate]), 
	FOREIGN KEY([StudentId]) REFERENCES master.[Students] ([StudentId])
)


GO

CREATE TABLE system.[AttendanceChanges] (
	[ChangeId] BIGINT NOT NULL IDENTITY, 
	[CreatedAt] DATETIME NOT NULL, 
	PRIMARY KEY ([ChangeId])
)


GO
CREATE INDEX [ix_integration_RecoveryPunches_ScanId] ON integration.[RecoveryPunches] ([ScanId])
GO
CREATE INDEX [ix_integration_RecoveryPunches_StudentId] ON integration.[RecoveryPunches] ([StudentId])
GO
CREATE INDEX [ix_master_VerifiedRoomChanges_StudentId] ON master.[VerifiedRoomChanges] ([StudentId])