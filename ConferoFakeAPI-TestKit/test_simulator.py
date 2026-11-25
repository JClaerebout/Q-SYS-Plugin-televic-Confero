import unittest
from ConferoFakeAPI import State


class SimulatorTests(unittest.TestCase):
    def test_device_inventory_by_system_and_resize(self):
        plixus = State(3)
        self.assertEqual(plixus.snapshot()['wireless'], [])
        self.assertEqual([plixus.room_seat(i)['units'][0] for i in plixus.seats],
                         [device['serial'] for device in plixus.devices()])
        self.assertTrue(all(d['powerState'] == {'powerSource': 'plixus'} for d in plixus.devices()))

        g4 = State(2, 'G4')
        first_serial = g4.room_seat(1)['units'][0]
        with g4.condition:
            g4.configure({'seatCount': 16})
            g4.configure({'seatCount': 15})
            g4.configure({'seatCount': 16})
        serials = {g4.room_seat(i)['units'][0] for i in g4.seats}
        self.assertEqual(g4.room_seat(1)['units'], [first_serial])
        self.assertEqual(serials, {device['serial'] for device in g4.devices()})
        self.assertEqual(len(serials), 16)
        self.assertTrue(all(len(d['powerState']['batteryStatus']['details']) == 2 for d in g4.devices()))

    def test_limit_queue_admission_and_names(self):
        s = State(4)
        with s.condition:
            s.configure({'maxOpen': 1, 'names': {'1': 'Alice', '2': 'Bob'}, 'meetingName': 'Test council'})
            s.set_mic(1, {'microphoneOn': True})
            s.set_mic(2, {'microphoneOn': True})
            s.set_mic(3, {'microphoneOn': True})
            self.assertEqual(s.speakers, [1])
            self.assertEqual(s.requests, [2, 3])
            s.set_mic(2, {'microphoneOn': True})
            self.assertEqual(s.requests, [2, 3])
            s.set_mic(1, {'microphoneOn': False})
            self.assertEqual(s.speakers, [2])
            self.assertEqual(s.requests, [3])
            self.assertTrue(s.seats[2]['microphoneOn'])
            self.assertFalse(s.seats[2]['requestingToSpeak'])
            self.assertEqual(s.participants()[1]['firstName'], 'Bob')
            self.assertEqual(s.events[-1]['data'], [3])
            s.set_mic(2, {'microphoneOn': False})
            self.assertEqual(s.speakers, [3])
            self.assertEqual(s.requests, [])
            s.set_mic(3, {'microphoneOn': False})
            self.assertEqual(s.speakers, [])

    def test_resize_limit_and_running_names(self):
        s = State(4)
        with s.condition:
            for i in (1, 2, 3):
                s.set_mic(i, {'microphoneOn': True})
            s.meeting = {'participants': s.participants()}
            s.configure({'seatCount': 2, 'maxOpen': 1, 'names': {'2': 'New name'}})
            self.assertEqual(s.speakers, [1])
            self.assertEqual(s.requests, [2])
            self.assertEqual(len(s.meeting['participants']), 2)
            self.assertEqual(s.meeting['participants'][1]['firstName'], 'New name')
            with self.assertRaises(ValueError):
                s.configure({'seatCount': 0})
            self.assertEqual(len(s.seats), 2)


if __name__ == '__main__':
    unittest.main()
