# Unofficial Televic Confero plugin for Q-SYS, providing meeting, microphone and seat control. (In Development)

## Overview

The **Televic Confero (Plixus) Q-SYS Plugin** enables monitoring and control of Televic conference systems directly from Q-SYS through the Confero Customer API.

It provides per-seat microphone control, active speaker and request lists, meeting controls, discussion settings, and recording controls in a multi-page interface.

---

## Features

- Connect over HTTP or HTTPS using an API token
- Discover seats and display seat numbers, participant names, roles, and microphone/request status
- Control up to 100 seat rows, with 15 rows per page
- Monitor active speakers and requests in selectable, scrollable lists
- Turn off selected speakers, enable requested microphones, and clear lists
- Start an open meeting or a selected scheduled meeting, and stop the current meeting
- Set discussion mode and maximum number of open microphones
- Start and stop recording with state feedback
- Receive changes through long-poll notifications
- Automatically refresh seat status and recover communication after controller outages
- Expose controls and feedback as Q-SYS control pins

---

## Plugin Information

| Property | Value |
| -------- | ----- |
| Name | Televic Confero (Plixus) |
| File | `TelevicConfero.qplug` |
| Version | 1.1.0 |
| Build Version | 1.1.0.0 |
| Author | Jens Claerebout |
| API Target | Confero Customer API 7.18 (Plixus) |
| Protocol | HTTP / HTTPS API |
| Default Ports | HTTP `9080`, HTTPS `9443` |
| Authentication | Bearer API token |

---

## Configuration

### Properties

| Property | Default | Description |
| -------- | ------- | ----------- |
| `Connection` | HTTP (9080) | Select HTTP on port 9080 or HTTPS on port 9443 |
| `Seat Count` | 15 | Number of seat control rows to create (1-100) |
| `Refresh Interval` | 30 | Seat status and meeting metadata refresh interval in seconds (10-60) |
| `Debug Print` | None | Logging level: `None`, `Tx/Rx`, or `All` |

### Connection and Discussion Controls

| Control | Pin | Description |
| ------- | --- | ----------- |
| `IP Address` | Input/Output | Controller hostname, IP address, or explicit URL and port |
| `API Token` | Input/Output | API token without the `Bearer` prefix |
| `Status` | Output | Connection status and diagnostic message |
| `Connected` | Output | Connection LED |
| `Refresh` | Input | Manually refresh controller data |
| `Discussion Mode` | Input/Output | Select the microphone discussion mode |
| `Number of Open Mics` | Input/Output | Maximum open microphones (plugin range: 1-100; default: 3) |
| `Apply Discussion Settings` | Input | Immediately apply settings; labelled **Apply Settings** |
| `Discussion Settings Status` | Output | Settings operation feedback |

Changing the address or token reconnects automatically. An explicit URL can specify a different port, for example `https://192.168.0.100:9443`.

### Meeting Controls

| Control | Pin | Description |
| ------- | --- | ----------- |
| `Meeting Start` | Input | Start a local-template meeting; labelled **Start Open** |
| `Scheduled Meetings` | Input/Output | Select an available scheduled meeting |
| `Start Selected Meeting` | Input | Start the selected scheduled meeting |
| `Meeting Stop` | Input | Stop the current meeting |
| `Meeting Running` | Output | Meeting running LED |
| `Meeting Title` | Output | Current meeting title |
| `Meeting ID` | Output | Current meeting ID |
| `Meeting Command Status` | Output | Scheduled-list loading and meeting command results |

### Per-Seat Controls

| Control | Pin | Description |
| ------- | --- | ----------- |
| `Seat Number` | Output | Actual API seat number assigned to the row |
| `Seat Name` | Output | Participant name, or `Seat N` when no name is available |
| `Seat Mic On` | Input/Output | Toggle the microphone and display confirmed feedback |
| `Seat Request` | Output | Request-to-speak LED |
| `Seat Role` | Output | Reported seat role |

### Speaker and Request List Controls

| Control | Pin | Description |
| ------- | --- | ----------- |
| `Speaking Seats` | Input/Output | Select an active speaker from the list |
| `Request Seats` | Input/Output | Select a seat requesting to speak |
| `Turn Off Selected Mic` | Input | Turn off the selected speaker; labelled **Turn Off Mic** |
| `Enable Requested Mic` | Input | Enable the selected request; labelled **Enable Mic** |
| `Speaker Count` | Output | Active speaker count as text |
| `Request Count` | Output | Request count as text |
| `Clear Speakers` | Input | Clear the active speaker list |
| `Clear Requests` | Input | Clear the request list |

### Recording Controls

| Control | Pin | Description |
| ------- | --- | ----------- |
| `Recording Start` | Input | Start recording; labelled **Start Recording** |
| `Recording Stop` | Input | Stop recording; labelled **Stop Recording** |
| `Recording Active` | Output | Recording LED |
| `Recording State` | Output | `idle`, `recording`, or `Unknown` feedback |
| `Recording Status` | Output | Recording operation status |

---

## UI Layout

| Page | Contents |
| ---- | -------- |
| Setup | Address, token, connection status, refresh, discussion mode, and maximum open microphones |
| Meeting Controls | Current meeting information, start/stop buttons, and scheduled-meeting selection |
| Seats | Seat number, name, role, microphone toggle, and request LED; up to 15 rows per page |
| Active / Request List | Speaker/request lists, counts, selected-seat actions, and clear-list buttons |
| Recording | Start/stop recording, recording LED, state, and operation status |

Seat pages are created automatically. A Seat Count of 1-15 creates one **Seats** page; 16-30 creates **Seats 1** and **Seats 2**, with further pages added as needed.

---

## Communication

The plugin uses JSON requests with Bearer token authentication and a long-poll notification connection.

### Main API Endpoints Used

| Endpoint | Method | Purpose |
| -------- | ------ | ------- |
| `/api/discussion/seats` | GET | Discover seats and refresh seat status |
| `/api/discussion/seats/{number}` | GET / PUT | Read seat feedback and control a microphone |
| `/api/discussion/speakers` | GET / DELETE | Read or clear active speakers |
| `/api/discussion/requests` | GET / DELETE | Read or clear requests |
| `/api/discussion/settings` | GET / PUT | Read or apply discussion settings |
| `/api/meeting` | GET / POST / DELETE | Read, start, or stop a meeting |
| `/api/meeting/scheduled-meetings` | GET | Retrieve scheduled meetings |
| `/api/notification/events` | GET | Receive long-poll notifications |
| `/api/recording/state` | GET / PUT | Read or change recording state |

### Notifications and Refresh

Speaker and request lists update directly from `SpeakersChanged` and `RequestsChanged` notifications. Each response renews the poll using `minimum-id = last event ID + 1`; HTTP 204 renews it without changing the lists.

List snapshots are fetched on connection, recovery or missed events, and manual **Refresh**. The **Refresh Interval** reconciles seat status and meeting metadata without polling the speaker/request lists. Scheduled meetings load on connection, every 60 seconds, and on manual **Refresh**.

Recording feedback uses `Recording.StateChanged` notifications. Discussion settings feedback uses `SettingsChanged` notifications.

---

## Behavior

### Seat Assignment and Microphone Control

Seats are sorted by their actual seat numbers, so gaps such as 7, 42, and 101 are supported. Each row's pins follow its displayed seat number; room reconfiguration can therefore change row assignments.

Participant names come from the current meeting, matched using `presence.seatNumber`. When an assigned participant name or meeting access is unavailable, the display uses `Seat N`.

Microphone commands send both `microphoneOn` and `requestingToSpeak: false`. Enabling or disabling a microphone also clears its pending request. This applies to both seat toggles and selected-list actions. An HTTP success alone does not confirm a microphone change; the plugin uses subsequent seat feedback.

### Speaker and Request Lists

Lists display `number - name` in API order and include all returned seats, even when **Seat Count** limits the visible seat rows. The string value contains the selected entry; `Choices` contains all entries.

Selection follows the seat number across updates and clears when that seat leaves the list. Select a speaker and press **Turn Off Mic**, or select a request and press **Enable Mic**.

### Meeting Selection

Scheduled-meeting selection follows the meeting ID across refreshes. Duplicate titles include their IDs. All meeting actions use the same address and token as microphone control.

### Discussion Settings

Changing the mode or open-microphone limit automatically sends both settings after a 300 ms pause. Edits made during a pending write are sent after that write completes. **Apply Settings** sends an immediate manual apply, and incoming settings feedback does not overwrite pending edits.

Mode options reported by the controller are preserved. For a mode not yet reported, the plugin uses toggle activation where applicable, red speaking LEDs, green request LEDs, and off idle LEDs. Switching and cancellation are enabled, speaker override is disabled, and hands-free uses push-to-mute.

### Connection Recovery

A successful seat snapshot clears historical connection failures and restores Connected/OK and the seat controls after a controller reboot. Periodic seat refreshes provide this health check at the configured interval.

Rejected commands and unavailable optional features are logged without treating them as a lost connection. Transport and authorization failures report a fault until communication recovers. On disconnection, retained feedback may be stale.

An empty notification request reaching the full 40-second timeout renews automatically without changing connection status or clearing an existing fault. Other notification errors trigger recovery; periodic seat reads continue to detect controller outages.

---

## Installation

1. Copy `TelevicConfero.qplug` to your Q-SYS Designer user Plugins folder.
2. Add a new plugin instance to the design.
3. Set **Connection**, **Seat Count**, and **Refresh Interval** in the plugin properties.
4. Open **Setup** and enter the controller address and API token without `Bearer`.
5. Deploy the design to the Q-SYS Core.
6. Verify Connected/OK status and confirm that the displayed seat numbers match the room configuration.

When replacing version 1.0.0, check existing UCI controls and pin connections because the control definitions have changed. Discussion title, description, start/stop, and discussion status controls have been removed; meeting start/stop remains available on **Meeting Controls**.

---

## Troubleshooting and Testing

Set **Debug Print** to **All** and open the Q-SYS debug output. Toggle a seat microphone or select a list entry and press its microphone action.

Logs show the mapped seat, requested and confirmed state, skipped-command reasons, HTTP request body, response/error, and seat feedback. **Tx/Rx** includes microphone action logs; **All** additionally includes snapshot row mappings and stale-read diagnostics. **None** disables logging. Authorization headers are not printed.

See the [test instructions](ConferoFakeAPI-TestKit/TESTING.md) for simulator setup and validation. Automated tests mock the Q-SYS runtime; final validation in Designer and against a physical controller is still required.

---

## Known Limitations

- Seat control rows are limited to 100; speaker and request lists include all returned seats.
- Row assignments can change when the room's seat configuration changes.
- The 1-100 open-microphone range is a plugin limit; a controller may reject unsupported values.
- Recording availability depends on the controller. Unknown or unavailable recording feedback is shown as `Unknown`.
- Recording controls do not include duration, filename, storage, pause, or a recording list.
- The simulator stores discussion modes and enforces the speaker limit, but does not reproduce every mode's hardware behavior.
- The simulator emulates recording state and events only; it does not record audio.

---

## Author

Jens Claerebout

## License

This project is licensed under the [MIT License](LICENSE).
