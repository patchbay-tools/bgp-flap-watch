import unittest

from flap_watch import FlapTracker, parse_protocols, parse_routes

ROUTES = """\
BIRD 2.0.12 ready.
Table master4:
192.0.2.0/24         unicast [upstream1 2024-03-02 11:04:51] * (100) [AS64500i]
	via 203.0.113.1 on eth0
                     unicast [upstream2 2024-03-02 11:05:02] (100) [AS64500i]
	via 203.0.113.9 on eth1
198.51.100.0/24      unicast [upstream1 2024-03-02 11:04:51] * (100) [AS64501i]
	via 203.0.113.1 on eth0
2001:db8::/32        unicast [upstream1 2024-03-02 11:04:51] * (100) [AS64502i]
	via 2001:db8:ffff::1 on eth0
"""

PROTOCOLS = """\
BIRD 2.0.12 ready.
Name       Proto      Table      State  Since         Info
device1    Device     ---        up     2024-03-01 09:12:44
kernel1    Kernel     master4    up     2024-03-01 09:12:44
upstream1  BGP        ---        up     2024-03-02 11:04:50  Established
upstream2  BGP        ---        start  2024-03-02 11:20:13  Active        Socket: Connection refused
"""


class ParseTest(unittest.TestCase):
    def test_routes(self):
        self.assertEqual(parse_routes(ROUTES), {"192.0.2.0/24", "198.51.100.0/24", "2001:db8::/32"})

    def test_protocols(self):
        sessions = parse_protocols(PROTOCOLS)
        self.assertEqual([s.name for s in sessions], ["upstream1", "upstream2"])
        self.assertEqual(sessions[0].info, "Established")
        self.assertEqual(sessions[1].state, "start")


class TrackerTest(unittest.TestCase):
    def test_flap_over_threshold(self):
        tracker = FlapTracker(window=60, threshold=3)
        base = {"192.0.2.0/24", "198.51.100.0/24"}
        self.assertEqual(tracker.update(base, 0), [])
        self.assertEqual(tracker.update(base - {"192.0.2.0/24"}, 10), [])
        self.assertEqual(tracker.update(base, 20), [])
        self.assertEqual(tracker.update(base - {"192.0.2.0/24"}, 30), [("192.0.2.0/24", 3)])

    def test_old_changes_expire(self):
        tracker = FlapTracker(window=60, threshold=3)
        base = {"192.0.2.0/24"}
        tracker.update(base, 0)
        tracker.update(set(), 10)
        tracker.update(base, 20)
        self.assertEqual(tracker.update(set(), 200), [])


if __name__ == "__main__":
    unittest.main()
