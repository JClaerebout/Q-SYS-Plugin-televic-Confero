import unittest
from ConferoFakeAPI import State


class SimulatorTests(unittest.TestCase):
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
