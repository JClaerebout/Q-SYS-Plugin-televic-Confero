# Confero API review — 10 September 2026

Reference: [7.18 Plixus Swagger page](https://tcs-static.azurewebsites.net/confero-customer-api/7.18_Plixus/index.html), using its [OpenAPI source](https://tcs-static.azurewebsites.net/confero-customer-api/7.18_Plixus/openapi.txt). The browser fetch could not render the page; the HTML and schema were retrieved directly. This review covers the endpoints used by the plugin, not unrelated audio, voting, interpretation, or wireless functionality.

| Feature | Documentation and implementation |
|---|---|
| Connection | HTTP 9080 / HTTPS 9443; Authorization Bearer token. Explicit host/port overrides are plugin conveniences. |
| Notifications | GET `/api/notification/events`, comma-separated `include-filter`, optional `minimum-id` equal to last received ID + 1. HTTP 200 carries one event; 204 renews the long poll. Discussion/Meeting/Room are documented module names. |
| Lists | SpeakersChanged and RequestsChanged carry ordered arrays of integer seat numbers. They update lists directly. GET speaker/request lists supplies startup, recovery, and manual-refresh snapshots. |
| Seat feedback | SeatChanged carries SeatDiscussionState: seatNumber, microphoneOn, requestingToSpeak, role. |
| Mic command | PUT `/api/discussion/seats/{seat}` documents microphoneOn and requestingToSpeak and returns 204. The controller requires requestingToSpeak despite the schema omitting a required list; commands now send both fields. |
| Clear lists | DELETE `/api/discussion/speakers` and `/api/discussion/requests` return 204. |
| Scheduled meetings | GET `/api/meeting/scheduled-meetings` returns objects containing kind=ScheduledMeeting, scheduledMeetingId, name. ScheduledMeetingsChanged triggers a refresh. |
| Start/stop | POST `/api/meeting` uses NewMeetingFromLocalTemplate or NewMeetingFromScheduledMeeting with scheduledMeetingId. Returns a JSON meeting-ID string. DELETE returns 204. The documented scheduled-start example includes title, although that property is not listed in its schema. |
| Names | GET `/api/meeting` supplies participants; firstName + lastName are matched through presence.seatNumber. Absent participants have no seat number. |
| Meeting availability | GET meeting: 412 means no open meeting; 405 means not licensed. Scheduled-meeting GET also documents 405. Neither GET's expected unavailable state should disable microphone control. |
| Discussion actions | POST `/api/meeting/actions`: StartDiscussionAction includes meetingId and discussion title/description; 200 returns discussion ID. StopDiscussionAction uses meetingId and discussionId per the endpoint example. |

Corrections from this review:

- Added required ScheduledMeeting.kind values to simulator responses and replaced the unsupported discussion role `lectern`.
- Replaced empty simulator room/participant event payloads with documented structures; added ScheduledMeetingsChanged.
- Enforced the notification include-filter in the simulator and reported discontinuity when the requested event history has expired.
- Handled unlicensed scheduled-meeting access without marking mic communication disconnected.
- Fixed recovery when an in-flight list snapshot is invalidated by a discontinuity, while avoiding redundant GETs when a complete newer list event already arrived.
- Removed duplicate meeting reads triggered by the same MeetingStateChanged event.

Documentation ambiguities and validation limits:

- G4 follow-up, 14 September 2026: checked the [7.18 G4 OpenAPI source](https://tcs-static.azurewebsites.net/confero-customer-api/7.18_G4/openapi.txt). Its introduction specifies `/api/notification/events` with a comma-separated include-filter and last event ID + 1. SpeakersChanged and RequestsChanged payloads are ordered integer arrays, matching the plugin's event handlers. The seat PUT schema lists both booleans without marking them required, but the supplied controller log returns HTTP 400 with `Missing json field: requestingToSpeak` when it is omitted. The earlier claim that microphoneOn could be sent independently was not validated on hardware and is corrected above. Both mic command paths now send requestingToSpeak=false; successful operation still needs controller confirmation.

- StopDiscussionAction's schema incorrectly lists `itemId` as required while its property and endpoint example use `discussionId`. The plugin follows the property/example.
- The introduction requires include-filter although its parameter schema omits required=true. The implementation follows the introduction.
- The document describes a server long-poll timeout but gives no numeric duration. The plugin's 40-second HTTP timeout is a client choice, with retry/recovery on failure.
- The simulator's overflow-to-request policy and automatic queue admission are requested test behavior. The API's seat PUT schema does not specify those arbitration rules, so simulator success does not prove that a real controller in every discussion mode behaves identically.
- The simulator's `/sim/*` routes and browser UI are test-only extensions, not Confero endpoints. It does not emulate licensing, TLS, all discussion modes, or every controller rule.
- Automated Lua and simulator regressions pass. Designer rendering, Core HTTP/TLS behavior, real-controller timing, and externally started discussion IDs still require hardware validation.
