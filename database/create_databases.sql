-- ============================================================================
-- RUN THIS SCRIPT IN SSMS (SQL Server Management Studio)
-- Connect to Server: MISISC\SQLEXPRESS
-- ============================================================================

IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = 'HostelAttendance')
    CREATE DATABASE HostelAttendance;
GO

IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = 'Epush_Dummy')
    CREATE DATABASE Epush_Dummy;
GO

PRINT 'Databases HostelAttendance and Epush_Dummy created successfully!';
