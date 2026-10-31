import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import catch_log
from fishing import Catch


class CatchLogTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "catches.csv"

    def save(self, *catches):
        for c in catches:
            catch_log.append(catch_log.row(c), self.path)

    def test_round_trip_keeps_order_and_writes_one_header(self):
        self.save(Catch("Blue-Lip Grouper", "Common"), None, Catch("Jack-O'-Bite", "Legendary"))
        rows = catch_log.load(self.path)
        self.assertEqual([(r["name"], r["rarity"]) for r in rows],
                         [("Blue-Lip Grouper", "Common"), (catch_log.NO_NAME, "Unknown"),
                          ("Jack-O'-Bite", "Legendary")])
        self.assertEqual(self.path.read_text().count("time,name,rarity"), 1)

    def test_names_with_commas_and_quotes_survive(self):
        self.save(Catch('Odd, "quoted" fish', "Rare"))
        self.assertEqual(catch_log.load(self.path)[0]["name"], 'Odd, "quoted" fish')

    def test_missing_or_empty_file_is_no_history(self):
        self.assertEqual(catch_log.load(self.path), [])
        self.path.write_text("")
        self.assertEqual(catch_log.load(self.path), [])
        self.save(Catch("Swordfish", "Legendary"))  # an empty file still gets the header
        self.assertEqual(len(catch_log.load(self.path)), 1)

    def test_wrong_header_fails_loudly(self):
        self.path.write_text("when,what\n2026-10-31,Swordfish\n")
        with self.assertRaisesRegex(catch_log.CatchLogError, "expected"):
            catch_log.load(self.path)

    def test_broken_line_names_the_line(self):
        self.save(Catch("Swordfish", "Legendary"))
        with open(self.path, "a") as f:
            f.write("2026-10-31 10:00:00,half a row\n")
        with self.assertRaisesRegex(catch_log.CatchLogError, "line 3"):
            catch_log.load(self.path)

    def test_tally_groups_unread_colours_as_unknown(self):
        rows = [{"rarity": r} for r in ("Common", "Common", "Epic", "unknown (orange)", "Unknown")]
        self.assertEqual(catch_log.tally(rows), Counter({"Common": 2, "Epic": 1, "Unknown": 2}))

    def test_rarity_line_shows_unknown_only_when_there_is_one(self):
        self.assertEqual(catch_log.rarity_line(Counter({"Rare": 2})), "0 Common · 2 Rare · 0 Epic · 0 Legendary")
        self.assertTrue(catch_log.rarity_line(Counter({"Unknown": 1})).endswith("· 1 Unknown"))

    def test_by_name_counts_most_caught_first(self):
        rows = [{"name": n, "rarity": r} for n, r in
                (("Swordfish", "Legendary"), ("Grouper", "Common"), ("Grouper", "Common"), ("Anchovy", "Common"))]
        self.assertEqual(catch_log.by_name(rows),
                         [("Grouper", "Common", 2), ("Anchovy", "Common", 1), ("Swordfish", "Legendary", 1)])


if __name__ == "__main__":
    unittest.main()
