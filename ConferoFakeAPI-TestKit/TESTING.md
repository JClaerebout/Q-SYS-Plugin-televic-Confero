# Testing the Televic Confero Q-SYS plugin

## 1. Run the fake API

Python 3 is the only requirement.

```bash
python ConferoFakeAPI.py --system plixus --seats 10 --token qsys-test-token
```

On Windows, allow Python through Windows Firewall for the private network if prompted. Find the computer's LAN address with `ipconfig`. The Q-SYS Core and computer must be able to reach each other.

## 2. Configure the Q-SYS plugin

Open **http://127.0.0.1:9080/** on the simulator computer for the browser UI. Enter the same token as the plugin. Set microphone count, maximum open microphones, meeting title, and seat names, then click **Apply room & names**. Settings remain in memory until the server stops.

Use each seat's **On / Off** buttons to simulate physical microphone actions. If the open-mic limit is reached, On adds the seat to the ordered request queue. Off cancels that seat's microphone/request. Turning off a speaking mic automatically admits the first queued request. Increasing the limit or removing a speaking seat from the room also fills available slots in queue order. All mics off deliberately clears speakers without admitting requests. Lowering the limit queues excess speakers. Removing seats removes them from both lists.

In the plugin, press **Refresh**, select your meeting under **Scheduled Meetings**, and press **Start Selected Meeting**. The saved seat names become meeting participant names and appear in both live lists. Saving new names while the meeting runs updates its participants as well.

- **IP Address input field:** the LAN IP address of the computer running the simulator (do not use `127.0.0.1` when testing on a physical Core)
- **Connection:** `HTTP (9080)`
- **System Type:** `Plixus` for wired seats, or `G4` when the simulator runs with `--system g4`
- **API Token input field:** `qsys-test-token`. Connection starts automatically when both fields are filled.
- **Seat Count:** `10`, or the value passed to `--seats`

If you only emulate the design on the same computer as the Python server, `127.0.0.1` can be used.

## 3. Test sequence

1. Verify that `Connected` becomes true and the status reads `Connected`.
2. Toggle any `Seat Mic On` control. Its state follows confirmed controller feedback. `Seat Request` is a feedback LED.
3. Press `Meeting Start`; the simulated local-template meeting starts.
4. Enter a discussion title and press `Discussion Start`.
5. Press `Discussion Stop`, then `Meeting Stop`.
6. Test `Clear Speakers` and `Clear Requests` after enabling several seats.
7. Verify `Speaking Seats` and `Request Seats` show seat numbers and names, with entries in API order. Starting a simulated meeting supplies names such as `Delegate 1`.
8. Change a microphone or request externally with PowerShell and verify live feedback:

```powershell
Invoke-RestMethod -Method Put -Uri 'http://127.0.0.1:9080/api/discussion/seats/2' -Headers @{Authorization='Bearer qsys-test-token'} -ContentType 'application/json' -Body '{"requestingToSpeak":true}'
```

9. Enter an invalid token: status should report authorization failure. Restore the token and verify recovery. Change the IP while connected and verify old feedback does not repopulate the cleared lists.

The terminal running the simulator logs every HTTP request.

## Seat telemetry in Designer without a WAP

1. Start the fake API with `python ConferoFakeAPI.py --system g4 --seats 16 --token qsys-test-token`. Open the simulator UI and run the plugin in Designer Emulate with `127.0.0.1`, the same token, **System Type** set to **G4**, and **Seat Count** set to 16.
2. On **Seats 1**, seat 1 should show **Online**, **Battery A** at **80%**, and **Battery B** at **65%**. Every G4 seat starts with two batteries. Switch seat 2's **Seat status** to **Offline** and back. The Room events should update Designer without pressing **Refresh**.
3. In **Wireless units**, select the unit assigned to seat 1, leave slot B blank, and apply. After the next **Refresh Interval**, or after pressing **Refresh** in Designer, seat 1 should show **Battery A** at **80%** and **Battery B** as **—**. Set slot A to 0 and apply. Verify **Battery A** shows **0%** while **Battery B** still shows **—**.
4. Set **Unit state** to **Offline** and apply. After a refresh, both battery readouts should show **—** and the seat should still show **Online**. Set the unit back to **Online**, apply, and verify that **Battery A** shows **0%** again. Changing the seat's own status to **Offline** should also clear the charge.
5. Set **Assigned seat** to **Seat 16** and apply. The units swap seats. The Room events should move the **0%** reading to **Battery A** on seat 16 on **Seats 2**, while seat 1 shows the other unit's charge. Connect with a plugin configured for **Seat Count** 1 and reassign the edited unit to seat 1 to check the single-row **Seats** page.
6. Restart the fake API with `--system plixus` and set **System Type** to **Plixus**. Each seat should still show its status. The Seats pages omit the battery readouts and the plugin omits the Wireless page.

The plugin joins room `units[]` to device `serial` using exact string matches. A G4 WAP capture on Confero 7.17.2-2 confirmed this match for all 52 seats. To validate battery telemetry on hardware, compare the charge for one online unit with the reading in Confero. Room events during hardware power changes and reassignment still need verification.

## Useful options

```bash
python ConferoFakeAPI.py --help
python ConferoFakeAPI.py --port 9080 --seats 25 --token another-token --long-poll 30
```

The simulator covers the plugin's meeting, discussion, seat, ordered-list, and notification endpoints. It does not reproduce all controller rules or licensing restrictions.

## Automated runtime checks

Install `lupa` in your Python environment (`python -m pip install lupa`), then run `python test_plugin.py` and `python -m unittest -v test_simulator` from this folder. The plugin test executes the Lua with mocked asynchronous Q-SYS controls, HTTP requests, and timers. It also exercises the fake API over loopback HTTP. Coverage includes sparse and reordered seats, reassignment across pages, two battery slots, missing batteries, 0% charge, offline recovery, and Room events.

Actual Q-SYS rendering, Core networking/TLS, and a physical Confero controller still require the manual checks above.
