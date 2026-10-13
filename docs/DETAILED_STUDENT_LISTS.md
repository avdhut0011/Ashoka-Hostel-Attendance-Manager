# Detailed Student Lists

The sidebar now links to `/student-details`. The page lists active registered students in four views:

- Currently IN.
- Currently OUT.
- Five or more valid biometric IN punches OR five or more valid biometric OUT punches today. Counts are separate; three IN plus two OUT does not qualify. Users can select either direction, IN only, or OUT only.
- Currently OUT for strictly more than 24 hours.

Today is midnight inclusive to the following midnight exclusive in Asia/Kolkata. Registration events, duplicates, invalid punches, and manual overrides do not increase biometric punch counts, consistent with existing counter business logic.

Both valid punches and manual overrides maintain `StudentCurrentStatus.LastPunchTime` and `LastPunchType`. For currently OUT students whose last effective event is OUT, that timestamp starts the duration. A later manual OUT restarts it. Exactly 24 hours does not qualify, and legacy statuses with no known OUT timestamp are excluded from the over-24-hour view rather than assigned a guessed duration.

Wardens can only view and export students currently assigned to their hostel. Missing or inactive assignments are rejected by authentication; the query also rejects missing assignments and requests for another hostel. ADMIN, IT_ADMIN, and MANAGEMENT can access all hostels and apply a hostel filter. Student name/user ID search applies to every view.

`GET /api/student-details` is paginated with an exact total count. `GET /api/student-details/export` uses the same query and filters, exports all matching students without pagination limits, and returns Excel. Exports include view/filter metadata, the India attendance date, current status, daily counts, latest event time, OUT time and duration. Spreadsheet text is protected against formula interpretation. Refresh obtains current status; the page shows the most recent successful fetch time and request failures.

The feature uses existing tables and read-only queries. No migration, production seed, or alteration of existing student/attendance records is needed. The backend must load the updated code to expose the new endpoints; the frontend build is complete. Services were not restarted during implementation.

Validation: 70 isolated in-memory backend tests passed, including five new tests covering separate daily thresholds, midnight boundaries, manual OUT timing, strict 24-hour boundary, permission enforcement on lists and exports, missing warden assignment, full export across pages, spreadsheet safety, and read purity. Frontend production build passed. Production database connections are blocked by the test suite.
