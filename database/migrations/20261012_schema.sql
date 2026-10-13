-- Use python -m database.migrate_production --apply to execute with transactional checks.
IF DB_NAME() <> N'HostelAttendance' THROW 51000, 'Wrong target database', 1;

CREATE TABLE system.[AttendanceRevision] (
	[RevisionId] INTEGER NOT NULL, 
	[Version] BIGINT NOT NULL, 
	PRIMARY KEY ([RevisionId])
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

CREATE TABLE security.[RevokedTokens] (
	[TokenHash] VARCHAR(64) NOT NULL, 
	[UserId] BIGINT NOT NULL, 
	[ExpiresAt] DATETIME NOT NULL, 
	PRIMARY KEY ([TokenHash]), 
	FOREIGN KEY([UserId]) REFERENCES security.[Users] ([SystemUserId])
)


GO

CREATE TABLE security.[SecurityAudit] (
	[AuditId] BIGINT NOT NULL IDENTITY, 
	[ActorId] BIGINT NOT NULL, 
	[TargetId] BIGINT NOT NULL, 
	[Action] VARCHAR(60) NOT NULL, 
	[Details] VARCHAR(max) NOT NULL, 
	[CreatedAt] DATETIME NOT NULL, 
	PRIMARY KEY ([AuditId]), 
	FOREIGN KEY([ActorId]) REFERENCES security.[Users] ([SystemUserId]), 
	FOREIGN KEY([TargetId]) REFERENCES security.[Users] ([SystemUserId])
)


GO
CREATE INDEX [IX_LoginThrottle_UpdatedAt] ON security.[LoginThrottle] ([UpdatedAt])
GO
CREATE INDEX [IX_Punches_Hostel_Time_Id] ON attendance.[ProcessedPunches] ([HostelIdSnapshot], [LogDate], [PunchId]) INCLUDE ([StudentId], [UserId], [ProcessingStatus], [PunchType], [DeviceId])
GO
CREATE INDEX [IX_Punches_Student_Time_Id] ON attendance.[ProcessedPunches] ([StudentId], [LogDate], [PunchId]) INCLUDE ([ProcessingStatus], [PunchType], [RawPunchId])
GO
CREATE INDEX [IX_RevokedTokens_ExpiresAt] ON security.[RevokedTokens] ([ExpiresAt])
GO
CREATE INDEX [IX_SecurityAudit_CreatedAt] ON security.[SecurityAudit] ([CreatedAt])
GO
CREATE INDEX [IX_CurrentStatus_Status_Time] ON attendance.[StudentCurrentStatus] ([CurrentStatus], [LastPunchTime], [StudentId])