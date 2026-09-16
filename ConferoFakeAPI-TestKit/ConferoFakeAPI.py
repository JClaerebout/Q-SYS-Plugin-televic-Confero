#!/usr/bin/env python3
"""Small stateful simulator for the Televic Confero Customer API endpoints
used by the Q-SYS Televic Confero plugin.

No third-party packages are required. This is a test tool, not a complete
implementation of the Confero API.
"""

from __future__ import annotations

import argparse
import json
import threading
import time
import uuid
from pathlib import Path
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


class State:
    def __init__(self, seat_count: int):
        roles = ("chairperson", "delegate", "delegate", "vip", "delegate")
        self.seats = {
            i: {
                "seatNumber": i,
                "microphoneOn": False,
                "requestingToSpeak": False,
                "role": roles[(i - 1) % len(roles)],
            }
            for i in range(1, seat_count + 1)
        }
        self.meeting = None
        self.recording_state = "idle"
        self.scheduled_meetings = [
            {"kind": "ScheduledMeeting", "scheduledMeetingId": "scheduled-1", "name": "Council meeting"},
            {"kind": "ScheduledMeeting", "scheduledMeetingId": "scheduled-2", "name": "Committee meeting"},
        ]
        self.speakers = []
        self.requests = []
        self.discussion_id = None
        self.next_event_id = 1
        self.events = []
        self.condition = threading.Condition(threading.RLock())
        self.max_open = min(3, seat_count)
        self.discussion_settings = {"microphoneMode": "request", "maximumNumberOfSpeakers": self.max_open,
            "options": {"switchOffAllowed": True, "cancelRequestAllowed": True, "ledColorOn": "red",
                        "ledColorRequest": "green", "ledColorOff": "off", "nextInLineIndication": True}}
        self.names = {i: f"Delegate {i}" for i in self.seats}

    def participants(self):
        return [{"participantId": f"seat-{i}", "firstName": self.names[i], "lastName": "",
                 "presence": {"kind": "LocalParticipantPresence", "seatNumber": i}}
                for i in self.seats]

    def publish(self):
        for seat in self.seats.values():
            self.add_event("Discussion", "SeatChanged", dict(seat))
        self.add_event("Discussion", "SpeakersChanged", list(self.speakers))
        self.add_event("Discussion", "RequestsChanged", list(self.requests))

    def set_mic(self, number, body):
        seat = self.seats[number]
        was_speaking = number in self.speakers
        if "microphoneOn" in body:
            if body["microphoneOn"]:
                if number not in self.speakers:
                    if len(self.speakers) < self.max_open:
                        self.speakers.append(number)
                        if number in self.requests:
                            self.requests.remove(number)
                    elif number not in self.requests:
                        self.requests.append(number)
            else:
                if number in self.speakers:
                    self.speakers.remove(number)
                if number in self.requests:
                    self.requests.remove(number)
        if "requestingToSpeak" in body:
            if body["requestingToSpeak"] and number not in self.requests:
                self.requests.append(number)
            elif not body["requestingToSpeak"] and number in self.requests:
                self.requests.remove(number)
        if was_speaking and number not in self.speakers:
            self.promote_requests()
        self.sync_states()
        self.publish()

    def promote_requests(self):
        while self.requests and len(self.speakers) < self.max_open:
            number = self.requests.pop(0)
            if number in self.seats and number not in self.speakers:
                self.speakers.append(number)

    def sync_states(self):
        for i, seat in self.seats.items():
            seat["microphoneOn"] = i in self.speakers
            seat["requestingToSpeak"] = i in self.requests

    def configure(self, body):
        old_participants = {p['participantId']: p for p in self.participants()}
        count = body.get("seatCount", len(self.seats))
        maximum = body.get("maxOpen", self.max_open)
        names = body.get("names", {})
        title = body.get("meetingName", self.scheduled_meetings[0]["name"])
        if type(count) is not int or not 1 <= count <= 100:
            raise ValueError("Mic count must be 1–100")
        if type(maximum) is not int or not 1 <= maximum <= count:
            raise ValueError("Maximum open mics must be between 1 and mic count")
        if not isinstance(names, dict) or any(not isinstance(v, str) for v in names.values()):
            raise ValueError("Seat names must be text")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("Enter a meeting name")
        old = self.seats
        self.seats = {i: old.get(i, {"seatNumber": i, "microphoneOn": False,
                      "requestingToSpeak": False, "role": "delegate"}) for i in range(1, count + 1)}
        self.names = {i: names.get(str(i), self.names.get(i, f"Delegate {i}")).strip() or f"Seat {i}"
                      for i in self.seats}
        self.max_open = maximum
        active = [i for i in self.speakers if i in self.seats]
        self.speakers = active[:maximum]
        self.requests = list(dict.fromkeys([i for i in self.requests if i in self.seats] + active[maximum:]))
        self.scheduled_meetings[0]["name"] = title.strip()
        self.promote_requests()
        self.sync_states()
        self.publish()
        for i in old.keys() - self.seats.keys():
            self.add_event("Room", "SeatRemoved", i)
        for i in self.seats.keys() - old.keys():
            self.add_event("Room", "SeatAdded", {"seatNumber": i, "state": "online",
                "units": [f"sim-{i}"], "capabilities": ["discussion"], "role": self.seats[i]["role"]})
        self.add_event("Meeting", "ScheduledMeetingsChanged", {
            "kind": "EventScheduledMeetingsChanged",
            "scheduled_meetings": [dict(m) for m in self.scheduled_meetings]})
        if self.meeting:
            self.meeting["participants"] = self.participants()
            new_participants = {p['participantId']: p for p in self.participants()}
            for key in old_participants.keys() - new_participants.keys():
                self.add_event("Meeting", "ParticipantRemoved", {"kind": "EventParticipantRemoved", "participantId": key})
            for key, participant in new_participants.items():
                event = "ParticipantChanged" if key in old_participants else "ParticipantAdded"
                self.add_event("Meeting", event, {"kind": "Event" + event, "participant": participant})

    def snapshot(self):
        return {"seatCount": len(self.seats), "maxOpen": self.max_open,
                "meetingName": self.scheduled_meetings[0]["name"], "meeting": self.meeting,
                "seats": [dict(s, name=self.names[i]) for i, s in self.seats.items()],
                "speakers": self.speakers, "requests": self.requests}

    def add_event(self, module: str, name: str, data=None):
        with self.condition:
            event = {
                "discontinuity": False,
                "id": self.next_event_id,
                "module": module,
                "name": name,
            }
            if data is not None:
                event["data"] = data
            self.next_event_id += 1
            self.events.append(event)
            self.events = self.events[-500:]
            self.condition.notify_all()


class ConferoServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, handler, seat_count: int, token: str, long_poll: float):
        super().__init__(address, handler)
        self.state = State(seat_count)
        self.api_token = token
        self.long_poll = long_poll


class Handler(BaseHTTPRequestHandler):
    server_version = "ConferoFakeAPI/1.0"

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.log_date_time_string(), fmt % args))

    def authorized(self) -> bool:
        expected = "Bearer " + self.server.api_token
        if self.headers.get("Authorization") == expected:
            return True
        self.send_json(HTTPStatus.UNAUTHORIZED, {"message": "Invalid bearer token"})
        return False

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None

    def send_json(self, code: int, value=None):
        if value is None:
            self.send_response(code)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        data = json.dumps(value, separators=(",", ":")).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if urlparse(self.path).path == "/":
            data = Path(__file__).with_name("simulator.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if not self.authorized():
            return
        parsed = urlparse(self.path)
        path = parsed.path
        state = self.server.state

        if path == "/api/discussion/settings":
            with state.condition:
                self.send_json(200, dict(state.discussion_settings, maximumNumberOfSpeakers=state.max_open))
            return

        if path == "/api/recording/state":
            with state.condition:
                self.send_json(200, {"state": state.recording_state})
            return

        if path == "/sim/state":
            with state.condition:
                self.send_json(200, state.snapshot())
            return

        if path == "/api/meeting/scheduled-meetings":
            self.send_json(HTTPStatus.OK, state.scheduled_meetings)
            return

        if path == "/api/discussion/seats":
            with state.condition:
                self.send_json(HTTPStatus.OK, list(state.seats.values()))
            return

        if path in ("/api/discussion/speakers", "/api/discussion/requests"):
            with state.condition:
                self.send_json(HTTPStatus.OK, state.speakers if path.endswith("speakers") else state.requests)
            return

        if path.startswith("/api/discussion/seats/"):
            try:
                seat_number = int(path.rsplit("/", 1)[1])
            except ValueError:
                self.send_json(HTTPStatus.BAD_REQUEST, {"message": "Invalid seat"})
                return
            with state.condition:
                seat = state.seats.get(seat_number)
                self.send_json(HTTPStatus.OK, seat) if seat else self.send_json(HTTPStatus.BAD_REQUEST, {"message": "Unknown seat"})
            return

        if path == "/api/meeting":
            with state.condition:
                if state.meeting is None:
                    self.send_json(HTTPStatus.PRECONDITION_FAILED, {"message": "No open meeting"})
                else:
                    self.send_json(HTTPStatus.OK, state.meeting)
            return

        if path == "/api/notification/modules":
            self.send_json(HTTPStatus.OK, ["Discussion", "Meeting", "Room", "Recording"])
            return

        if path == "/api/notification/events":
            query = parse_qs(parsed.query)
            if not query.get("include-filter"):
                self.send_json(400, {"message": "include-filter is required"})
                return
            modules = set(query.get("include-filter", ["Discussion,Meeting"])[0].split(","))
            try:
                minimum_id = int(query.get("minimum-id", [str(state.next_event_id)])[0])
            except ValueError:
                self.send_json(HTTPStatus.BAD_REQUEST, {"message": "Invalid minimum-id"})
                return

            deadline = time.monotonic() + self.server.long_poll
            with state.condition:
                while True:
                    matches = [e for e in state.events if e["module"] in modules and e["id"] >= minimum_id]
                    if matches:
                        event = dict(matches[0])
                        event["discontinuity"] = bool(state.events and minimum_id < state.events[0]["id"])
                        self.send_json(HTTPStatus.OK, event)
                        return
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        self.send_json(HTTPStatus.NO_CONTENT)
                        return
                    state.condition.wait(remaining)

        self.send_json(HTTPStatus.NOT_FOUND, {"message": "Unknown endpoint"})

    def do_PUT(self):
        if not self.authorized():
            return
        path = urlparse(self.path).path
        state = self.server.state

        if path == "/api/recording/state":
            body = self.read_json()
            if not isinstance(body, dict) or body.get("state") not in ("idle", "recording"):
                self.send_json(400, {"message": "Expected idle or recording"})
                return
            with state.condition:
                state.recording_state = body["state"]
                state.add_event("Recording", "StateChanged", {"state": state.recording_state})
            self.send_json(204)
            return

        if path == "/api/discussion/settings":
            body = self.read_json()
            if (not isinstance(body, dict) or body.get("microphoneMode") not in
                ("directSpeak", "request", "group", "operator", "handsFree") or
                type(body.get("maximumNumberOfSpeakers")) is not int or
                not 1 <= body["maximumNumberOfSpeakers"] <= 100 or not isinstance(body.get("options"), dict)):
                self.send_json(400, {"message": "Invalid discussion settings"})
                return
            with state.condition:
                state.discussion_settings = body
                state.max_open = body["maximumNumberOfSpeakers"]
                overflow = state.speakers[state.max_open:]
                state.speakers = state.speakers[:state.max_open]
                state.requests = list(dict.fromkeys(state.requests + overflow))
                state.promote_requests()
                state.sync_states()
                state.publish()
                state.add_event("Discussion", "SettingsChanged", body)
            self.send_json(204)
            return

        if path == "/sim/config":
            body = self.read_json()
            try:
                if not isinstance(body, dict):
                    raise ValueError("Expected an object")
                with state.condition:
                    state.configure(body)
                    self.send_json(200, state.snapshot())
            except ValueError as error:
                self.send_json(400, {"message": str(error)})
            return

        if path.startswith("/api/discussion/seats/"):
            try:
                seat_number = int(path.rsplit("/", 1)[1])
            except ValueError:
                self.send_json(HTTPStatus.BAD_REQUEST, {"message": "Invalid seat"})
                return
            body = self.read_json()
            if not isinstance(body, dict):
                self.send_json(HTTPStatus.BAD_REQUEST, {"message": "Invalid JSON"})
                return
            with state.condition:
                seat = state.seats.get(seat_number)
                if seat is None:
                    self.send_json(HTTPStatus.BAD_REQUEST, {"message": "Unknown seat"})
                    return
                if any(type(body[k]) is not bool for k in ("microphoneOn", "requestingToSpeak") if k in body):
                    self.send_json(400, {"message": "Mic states must be booleans"})
                    return
                state.set_mic(seat_number, body)
            self.send_json(HTTPStatus.NO_CONTENT)
            return

        self.send_json(HTTPStatus.NOT_FOUND, {"message": "Unknown endpoint"})

    def do_POST(self):
        if not self.authorized():
            return
        path = urlparse(self.path).path
        state = self.server.state
        body = self.read_json()
        if not isinstance(body, dict):
            self.send_json(HTTPStatus.BAD_REQUEST, {"message": "Invalid JSON"})
            return

        if path == "/api/meeting":
            with state.condition:
                if state.meeting is not None:
                    self.send_json(HTTPStatus.PRECONDITION_FAILED, {"message": "Meeting already open"})
                    return
                meeting_id = str(uuid.uuid4())
                title = "Local template meeting"
                if body.get("kind") == "NewMeetingFromScheduledMeeting":
                    selected = next((m for m in state.scheduled_meetings if m["scheduledMeetingId"] == body.get("scheduledMeetingId")), None)
                    if selected is None:
                        self.send_json(HTTPStatus.BAD_REQUEST, {"message": "Unknown scheduled meeting"})
                        return
                    title = body.get("title", selected["name"])
                state.meeting = {
                    "meetingId": meeting_id, "title": title,
                    "participants": state.participants(),
                }
            state.add_event("Meeting", "MeetingStateChanged", {"kind": "EventMeetingStateChanged", "meetingState": "meetingRunning"})
            self.send_json(HTTPStatus.OK, meeting_id)
            return

        if path == "/api/meeting/actions":
            with state.condition:
                if state.meeting is None or body.get("meetingId") != state.meeting["meetingId"]:
                    self.send_json(HTTPStatus.PRECONDITION_FAILED, {"message": "No matching meeting"})
                    return
                kind = body.get("kind")
                if kind == "StartDiscussionAction":
                    state.discussion_id = str(uuid.uuid4())
                    result = state.discussion_id
                elif kind == "StopDiscussionAction":
                    if body.get("discussionId") != state.discussion_id:
                        self.send_json(HTTPStatus.BAD_REQUEST, {"message": "Unknown discussion"})
                        return
                    state.discussion_id = None
                    result = None
                else:
                    self.send_json(HTTPStatus.BAD_REQUEST, {"message": "Unsupported action"})
                    return
            self.send_json(HTTPStatus.OK, result) if result else self.send_json(HTTPStatus.NO_CONTENT)
            return

        self.send_json(HTTPStatus.NOT_FOUND, {"message": "Unknown endpoint"})

    def do_DELETE(self):
        if not self.authorized():
            return
        path = urlparse(self.path).path
        state = self.server.state

        if path == "/api/meeting":
            with state.condition:
                state.meeting = None
                state.discussion_id = None
            state.add_event("Meeting", "MeetingStateChanged", {"kind": "EventMeetingStateChanged", "meetingState": "noMeetingRunning"})
            self.send_json(HTTPStatus.NO_CONTENT)
            return

        if path in ("/api/discussion/speakers", "/api/discussion/requests"):
            field = "microphoneOn" if path.endswith("speakers") else "requestingToSpeak"
            changed = []
            with state.condition:
                for seat in state.seats.values():
                    if seat[field]:
                        seat[field] = False
                        changed.append(dict(seat))
                if field == "microphoneOn":
                    state.speakers.clear()
                else:
                    state.requests.clear()
            for seat in changed:
                state.add_event("Discussion", "SeatChanged", seat)
            state.add_event("Discussion", "SpeakersChanged" if field == "microphoneOn" else "RequestsChanged", [])
            self.send_json(HTTPStatus.NO_CONTENT)
            return

        self.send_json(HTTPStatus.NOT_FOUND, {"message": "Unknown endpoint"})


def main():
    parser = argparse.ArgumentParser(description="Fake Confero API for testing the Q-SYS plugin")
    parser.add_argument("--host", default="0.0.0.0", help="Listen address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=9080, help="Listen port (default: 9080)")
    parser.add_argument("--token", default="qsys-test-token", help="Required bearer token")
    parser.add_argument("--seats", type=int, default=10, help="Number of simulated seats")
    parser.add_argument("--long-poll", type=float, default=10.0, help="Notification timeout in seconds")
    args = parser.parse_args()

    server = ConferoServer((args.host, args.port), Handler, max(1, args.seats), args.token, max(0.1, args.long_poll))
    print(f"Fake Confero API listening on http://{args.host}:{args.port}")
    print(f"Bearer token: {args.token}")
    print(f"Simulated seats: {max(1, args.seats)}")
    print(f"Browser UI: http://127.0.0.1:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
