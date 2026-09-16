"""Run with Python and lupa installed. Uses an asynchronous mock of Q-SYS APIs."""
from pathlib import Path
import json
import os
import sys
sys.path.insert(0, os.path.join(os.environ.get('TEMP', ''), 'confero-test-deps'))
from lupa import LuaRuntime

lua = LuaRuntime(unpack_returned_tuples=True)
source = (Path(__file__).resolve().parents[1] / 'TelevicConfero.qplug').read_text(encoding='utf-8')
lua.execute(source)
lua.execute('''
Properties = {}
for _, property in ipairs(GetProperties()) do Properties[property.Name] = property end
assert(Properties["IP Address"] == nil and Properties["API Token"] == nil)
Properties["Seat Count"].Value = 3
Controls = {}
for _, definition in ipairs(GetControls(Properties)) do
  local function control() return {String = "", Boolean = false, Value = 0} end
  if definition.Count then
    Controls[definition.Name] = {}
    for i = 1, definition.Count do Controls[definition.Name][i] = control() end
  else Controls[definition.Name] = control() end
end
local layout = GetControlLayout(Properties)
assert(layout["IP Address"] and layout["API Token"])
assert(layout["Discussion Mode"].Style == "ComboBox")
-- Designer requires flat indexed names; nested layout arrays are not rendered.
for _, count in ipairs({1, 3, 10, 15, 16, 30, 31, 100}) do
  Properties["Seat Count"].Value = count
  local seatLayout = {}
  local pages = GetPages(Properties)
  assert(#pages == 4 + math.ceil(count / 15))
  assert(pages[#pages - 1].name == "Active / Request List" and pages[#pages].name == "Recording")
  for page = 1, #pages do
    Properties.page_index = {Value=page}
    for key, item in pairs(GetControlLayout(Properties)) do
      assert(seatLayout[key] == nil, "Control repeated across pages: " .. key)
      seatLayout[key] = item
      if key:match("^Seat ") then
        local row = tonumber(key:match(" (%d+)$")) or 1
        assert(page == 3 + math.floor((row - 1) / 15), "Seat on wrong page: " .. key)
        assert(item.Position[2] == 56 + ((row - 1) % 15) * 30, "Seat row position: " .. key)
      end
    end
  end
  Properties.page_index = nil
  for _, definition in ipairs(GetControls(Properties)) do
    for i = 1, definition.Count or 1 do
      local key = definition.Name .. ((definition.Count or 1) > 1 and (" " .. i) or "")
      assert(seatLayout[key] and seatLayout[key].Position and seatLayout[key].Style, "Missing layout: " .. key)
    end
  end
end
Properties["Seat Count"].Value = 3
outbound, scheduled = {}, {}
HttpClient = {
  Download = function(r) table.insert(outbound, r) end,
  Upload = function(r) table.insert(outbound, r) end
}
Timer = {
  New = function() return {Start = function() end, Stop = function() end} end,
  CallAfter = function(f) table.insert(scheduled, f) end
}
function take(path, method)
  for i, r in ipairs(outbound) do
    if r.Url:match("^https?://[^/]+([^?]+)") == path and (not method or r.Method == method) then
      return table.remove(outbound, i)
    end
  end
  error("Missing request " .. path)
end
function edit(name, value)
  Controls[name].String = value
  Controls[name].EventHandler(Controls[name])
end
''')

def to_lua(value):
    if isinstance(value, dict):
        return lua.table_from({k: to_lua(v) for k, v in value.items()})
    if isinstance(value, list):
        return lua.table_from([to_lua(v) for v in value])
    return value

lua.globals().json_decode = lambda raw: to_lua(json.loads(raw))
def from_lua(value):
    if hasattr(value, 'items'):
        return {k: from_lua(v) for k, v in value.items()}
    return value

lua.globals().json_encode = lambda value: json.dumps(from_lua(value))
lua.execute('package.preload.rapidjson = function() return {encode = json_encode, decode = json_decode} end')
lua.execute(source)
g = lua.globals()

def reply(path, value=None, code=200, method=None):
    req = g.take(path, method)
    req.EventHandler(req, code, json.dumps(value) if value is not None else '', None, lua.table())
    return req

seats = [dict(seatNumber=n, microphoneOn=False, requestingToSpeak=n == 42, role='delegate') for n in (42, 7, 101)]
meeting = {'meetingId': 'm1', 'title': 'Test', 'participants': [
    {'firstName': 'Jane', 'lastName': 'Doe', 'presence': {'kind': 'LocalParticipantPresence', 'seatNumber': 42}}]}
assert len(g.outbound) == 0
g.edit('IP Address', '192.0.2.1')
assert len(g.outbound) == 0
g.edit('API Token', 'test-token')
reply('/api/meeting', meeting)
reply('/api/discussion/seats', seats)
reply('/api/discussion/speakers', [])
reply('/api/discussion/requests', [42])
assert g.Controls['Seat Number'][1].String == '7'
assert g.Controls['Seat Number'][2].String == '42'
assert g.Controls['Seat Name'][2].String == 'Jane Doe'
assert g.Controls['Request Seats'].Choices[1] == '42 - Jane Doe'

reply('/api/recording/state', {'state': 'idle'})
assert not g.Controls['Recording Active'].Boolean
g.Controls['Recording Start'].EventHandler()
req = g.take('/api/recording/state', 'PUT')
assert json.loads(req.Data) == {'state': 'recording'}
req.EventHandler(req, 204, '', None, lua.table())
reply('/api/recording/state', {'state': 'recording'})
assert g.Controls['Recording Active'].Boolean
g.Controls['Recording Stop'].EventHandler()
req = g.take('/api/recording/state', 'PUT')
assert json.loads(req.Data) == {'state': 'idle'}
req.EventHandler(req, 204, '', None, lua.table())
reply('/api/recording/state', None, 404)
assert g.Controls['Recording State'].String == 'Unknown'
assert g.Controls.Connected.Boolean

# Command targets the actual seat, includes the required request flag, and waits for feedback.
mic = g.Controls['Seat Mic On'][2]
mic.Boolean = True
mic.EventHandler(mic)
assert not mic.Boolean
put = g.take('/api/discussion/seats/42', 'PUT')
assert json.loads(put.Data) == {'microphoneOn': True, 'requestingToSpeak': False}
put.EventHandler(put, 204, '', None, lua.table())
seats[0]['microphoneOn'] = True
reply('/api/discussion/seats/42', seats[0])
reply('/api/discussion/seats', seats)
assert mic.Boolean and g.Controls['Seat Request'][2].Boolean

# An event beats a stale pending snapshot; list order comes from API, not sorting.
g.Controls.Refresh.EventHandler()
reply('/api/notification/events', {'id': 10, 'module': 'Discussion', 'name': 'SpeakersChanged', 'data': [101, 42]})
reply('/api/discussion/speakers', [])
assert list(g.Controls['Speaking Seats'].Choices.values()) == ['101 - Seat 101', '42 - Jane Doe']
reply('/api/discussion/requests', [42])
reply('/api/discussion/seats', seats)
reply('/api/meeting', meeting)

# Reopen long poll with the event cursor; update/clear requests with no list GETs.
lua.eval('table.remove')(g.scheduled, 1)()
poll = g.take('/api/notification/events')
assert 'minimum-id=11' in poll.Url
poll.EventHandler(poll, 200, json.dumps({'id': 11, 'module': 'Discussion', 'name': 'RequestsChanged', 'data': [101, 42]}), None, lua.table())
assert list(g.Controls['Request Seats'].Choices.values()) == ['101 - Seat 101', '42 - Jane Doe']
g.edit('Request Seats', '42 - Jane Doe')
assert not g.Controls['Enable Requested Mic'].IsDisabled
g.Controls['Enable Requested Mic'].EventHandler()
request = g.take('/api/discussion/seats/42', 'PUT')
assert json.loads(request.Data) == {'microphoneOn': True, 'requestingToSpeak': False}
g.edit('Speaking Seats', '101 - Seat 101')
g.Controls['Turn Off Selected Mic'].EventHandler()
request = g.take('/api/discussion/seats/101', 'PUT')
assert json.loads(request.Data) == {'microphoneOn': False, 'requestingToSpeak': False}
lua.eval('table.remove')(g.scheduled, 1)()
reply('/api/notification/events', {'id': 12, 'module': 'Discussion', 'name': 'RequestsChanged', 'data': []})
assert g.Controls['Request Count'].String == '0'
assert g.Controls['Request Seats'].String == ''
assert g.Controls['Enable Requested Mic'].IsDisabled
before = len(g.outbound)
g.Controls['Enable Requested Mic'].EventHandler()
assert len(g.outbound) == before
lua.eval('table.remove')(g.scheduled, 1)()
reply('/api/notification/events', None, 204)
lua.eval('table.remove')(g.scheduled, 1)()
poll = g.take('/api/notification/events')
assert 'minimum-id=13' in poll.Url
for _, req in g.outbound.items():
    assert not req.Url.endswith(('/api/discussion/speakers', '/api/discussion/requests'))
print('PASS: long-poll cursor, request events, empty lists, 204 renewal, no event-triggered list GETs')

# Full-duration, empty event timeouts renew without a false fault or cursor reset.
for milliseconds in (40000, 40001):
    before = len(g.outbound)
    poll.EventHandler(poll, 0.0, '', f'Operation timed out after {milliseconds} milliseconds with 0 bytes received', lua.table())
    assert g.Controls.Connected.Boolean and g.Controls.Status.Value == 0
    assert len(g.outbound) == before
    lua.eval('table.remove')(g.scheduled, 1)()
    poll = g.take('/api/notification/events')
    assert 'minimum-id=13' in poll.Url
    assert len(g.outbound) == before

# Ordinary timeouts still fault; an idle event poll must not clear that fault.
g.Controls.Refresh.EventHandler()
health = g.take('/api/discussion/seats')
health.EventHandler(health, 0, '', 'Operation timed out after 10000 milliseconds with 0 bytes received', lua.table())
assert not g.Controls.Connected.Boolean
fault = g.Controls.Status.String
poll.EventHandler(poll, 0, '', 'Operation timed out after 40000 milliseconds with 0 bytes received', lua.table())
assert not g.Controls.Connected.Boolean and g.Controls.Status.String == fault
lua.eval('table.remove')(g.scheduled, 1)()
poll = g.take('/api/notification/events')
# A quick connection failure remains a fault and uses the recovery path.
poll.EventHandler(poll, 0, '', 'Failed to connect to host', lua.table())
assert not g.Controls.Connected.Boolean
assert 'Failed to connect' in g.Controls.Status.String
lua.eval('table.remove')(g.scheduled, 1)()
reply('/api/discussion/seats', seats)
assert g.Controls.Connected.Boolean
print('PASS: idle timeout renewal, cursor preservation, health timeout faults, connection failure recovery')

# Old HTTP responses and scheduled event polls cannot cross credential changes.
g.Controls.Refresh.EventHandler()
old = g.take('/api/discussion/seats')
g.edit('API Token', '')
old.EventHandler(old, 200, json.dumps(seats), None, lua.table())
assert g.Controls['Seat Number'][1].String == ''
assert not g.Controls.Connected.Boolean
while len(g.scheduled):
    lua.eval('table.remove')(g.scheduled, 1)()
g.outbound = lua.table()
g.edit('API Token', 'new-token')
req = reply('/api/discussion/seats', None, 401)
assert req.Headers.Authorization == 'Bearer new-token'
reply('/api/discussion/speakers', [])
assert not g.Controls.Connected.Boolean
assert g.Controls.Status.String == 'Authorization failed'
reply('/api/discussion/requests', [])
reply('/api/meeting', None, 412)
g.Controls.Refresh.EventHandler()
reply('/api/discussion/seats', seats)
assert g.Controls.Connected.Boolean
assert g.Controls['Seat Name'][2].String == 'Seat 42'
reply('/api/discussion/speakers', [42])
reply('/api/discussion/requests', [42])
reply('/api/meeting', None, 412)

# Physical/external mic events update controls, and rejected writes restore feedback.
seats[0]['microphoneOn'] = False
reply('/api/notification/events', {'id': 20, 'module': 'Discussion', 'name': 'SeatChanged', 'data': seats[0]})
assert not mic.Boolean
mic.Boolean = True
mic.EventHandler(mic)
reply('/api/discussion/seats/42', None, 400, 'PUT')
assert not mic.Boolean and g.Controls.Connected.Boolean
reply('/api/discussion/seats/42', seats[0])
reply('/api/discussion/seats', seats)
assert not mic.Boolean

# A settings request interrupted by reboot must not latch the connection fault.
reply('/api/discussion/settings', None, 0)
assert not g.Controls.Connected.Boolean
g.Controls.Refresh.EventHandler()
reply('/api/discussion/seats', None, 0)
assert not g.Controls.Connected.Boolean and mic.IsDisabled
g.Controls.Refresh.EventHandler()
reply('/api/discussion/seats', seats)
assert g.Controls.Connected.Boolean and g.Controls.Status.Value == 0
assert not mic.IsDisabled
mic.Boolean = True
mic.EventHandler(mic)
put = g.take('/api/discussion/seats/42', 'PUT')
assert json.loads(put.Data) == {'microphoneOn': True, 'requestingToSpeak': False}
put.EventHandler(put, 204, '', None, lua.table())
reply('/api/discussion/seats/42', seats[0])
reply('/api/discussion/seats', seats)
print('PASS: reboot fault clears on seat feedback; mic controls recover without retrying failed settings')

# Scheduled meeting selection survives refresh by ID, including duplicate names.
catalog = [{'name': 'Council', 'scheduledMeetingId': 'a'}, {'name': 'Council', 'scheduledMeetingId': 'b'}]
reply('/api/meeting/scheduled-meetings', catalog)
g.edit('Scheduled Meetings', 'Council [b]')
g.Controls.Refresh.EventHandler()
reply('/api/meeting/scheduled-meetings', list(reversed(catalog)))
assert g.Controls['Scheduled Meetings'].String == 'Council [b]'
g.Controls['Start Selected Meeting'].EventHandler()
req = g.take('/api/meeting', 'POST')
assert json.loads(req.Data) == {'kind': 'NewMeetingFromScheduledMeeting', 'title': 'Council', 'scheduledMeetingId': 'b'}
req.EventHandler(req, 412, '', None, lua.table())
assert 'Could not start' in g.Controls['Meeting Command Status'].String
g.Controls.Refresh.EventHandler()
reply('/api/meeting/scheduled-meetings', [])
assert g.Controls['Scheduled Meetings'].String == ''
assert g.Controls['Start Selected Meeting'].IsDisabled
g.Controls['Meeting Start'].EventHandler()
req = g.take('/api/meeting', 'POST')
assert json.loads(req.Data) == {'kind': 'NewMeetingFromLocalTemplate'}
req.EventHandler(req, 200, '"new-id"', None, lua.table())
assert g.Controls['Meeting Command Status'].String == 'Open meeting started'
g.Controls['Meeting Stop'].EventHandler()
reply('/api/meeting', None, 204, 'DELETE')
assert g.Controls['Meeting Command Status'].String == 'Meeting stopped'
g.Controls.Refresh.EventHandler()
old = g.take('/api/meeting/scheduled-meetings')
g.edit('IP Address', 'https://192.0.2.2:9555/')
old.EventHandler(old, 200, json.dumps(catalog), None, lua.table())
assert g.Controls['Scheduled Meetings'].String == ''
req = g.take('/api/meeting/scheduled-meetings')
assert req.Url == 'https://192.0.2.2:9555/api/meeting/scheduled-meetings'
print('PASS: scheduled selection, duplicate names, empty lists, start/stop payloads, rejected starts, credential changes, custom URL')

# Compile/run with Q-SYS's scalar representation for Count=1.
lua.execute('''
Controls = nil
''')
lua.execute(source)
lua.execute('''
Properties["Seat Count"].Value = 1
Controls = {}
for _, d in ipairs(GetControls(Properties)) do Controls[d.Name] = {String = "", Boolean = false, Value = 0} end
''')
lua.execute(source)
assert g.Controls['Seat Mic On'].IsDisabled
print('PASS: Lua layout/runtime, credentials, sparse seats, names, mic-only commands, live feedback, ordered lists, stale reads, reconnect, rejected commands, scalar controls')

# Exercise the simulator over real loopback HTTP as well as the Lua mocks.
# Automatic settings coalesce edits and retain edits made during an HTTP write.
g.outbound, g.scheduled = lua.table(), lua.table()
g.edit('IP Address', '192.0.2.1')
g.edit('API Token', 'test-token')
initial_settings = dict(microphoneMode='directSpeak', maximumNumberOfSpeakers=3,
                        options=dict(microphoneActivationType='toggle'))
reply('/api/discussion/settings', initial_settings)
g.edit('Discussion Mode', 'Operator')
maximum = g.Controls['Number of Open Mics']
maximum.Value = 5
maximum.EventHandler(maximum)
while len(g.scheduled):
    lua.eval('table.remove')(g.scheduled, 1)()
put = g.take('/api/discussion/settings', 'PUT')
assert json.loads(put.Data)['microphoneMode'] == 'operator'
assert json.loads(put.Data)['maximumNumberOfSpeakers'] == 5
assert not any(r.Method == 'PUT' for _, r in g.outbound.items())
maximum.Value = 7
maximum.EventHandler(maximum)
# Old controller feedback must not replace the unsent value.
reply('/api/notification/events', dict(id=1, module='Discussion', name='SettingsChanged', data=initial_settings))
assert maximum.Value == 7 and g.Controls['Discussion Mode'].String == 'Operator'
put.EventHandler(put, 204, '', None, lua.table())
put = g.take('/api/discussion/settings', 'PUT')
assert json.loads(put.Data)['maximumNumberOfSpeakers'] == 7
put.EventHandler(put, 204, '', None, lua.table())
reply('/api/discussion/settings', dict(microphoneMode='operator', maximumNumberOfSpeakers=7, options={}))
assert maximum.Value == 7
# Reconnect invalidates a pending debounce callback.
maximum.Value = 8
maximum.EventHandler(maximum)
g.edit('API Token', '')
g.outbound = lua.table()
while len(g.scheduled):
    lua.eval('table.remove')(g.scheduled, 1)()
assert len(g.outbound) == 0
print('PASS: automatic settings, coalesced edits, edits during PUT, feedback protection, reconnect cancellation')

from ConferoFakeAPI import ConferoServer, Handler
from threading import Thread
from urllib.request import Request, urlopen
server = ConferoServer(('127.0.0.1', 0), Handler, 3, 'test', 0.1)
worker = Thread(target=server.serve_forever, daemon=True)
worker.start()
def api(path, method='GET', body=None):
    req = Request(f'http://127.0.0.1:{server.server_port}' + path,
                  data=json.dumps(body).encode() if body is not None else None,
                  headers={'Authorization': 'Bearer test', 'Content-Type': 'application/json'}, method=method)
    with urlopen(req, timeout=3) as response:
        raw = response.read()
        return json.loads(raw) if raw else None
try:
    api('/api/meeting', 'POST', {'kind': 'NewMeetingFromLocalTemplate'})
    assert len(api('/api/meeting')['participants']) == 3
    api('/api/discussion/seats/3', 'PUT', {'microphoneOn': True})
    api('/api/discussion/seats/1', 'PUT', {'microphoneOn': True, 'requestingToSpeak': True})
    assert api('/api/discussion/speakers') == [3, 1]
    assert api('/api/discussion/requests') == [1]
    assert api('/api/notification/events?include-filter=Discussion&minimum-id=2')['name'] == 'SeatChanged'
    api('/api/discussion/speakers', 'DELETE')
    assert api('/api/discussion/speakers') == []
    assert api('/api/discussion/requests') == [1]
    api('/api/discussion/requests', 'DELETE')
    assert api('/api/discussion/requests') == []
finally:
    server.shutdown()
    server.server_close()
    worker.join(timeout=2)
print('PASS: simulator HTTP, participant names, queue order, notifications, clear speakers/requests')
