import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "route_reference.py"
SCOPES = ("scenes", "design", "moves", "skills", "scripts")

sys.path.insert(0, str(ROOT))
from scripts import route_reference as router  # noqa: E402


class RouteReferenceTests(unittest.TestCase):
    def test_all_indexed_bodies_are_readable(self):
        total = 0
        for scope in SCOPES:
            result = router.route(scope, "屋顶")
            for item in result["available"]:
                body = router.read(f"{scope}/{item['id']}")
                self.assertNotIn("未找到", body)
                self.assertGreater(len(body.strip()), 10)
                total += 1
        self.assertEqual(total, 132)

    def test_strong_terms_require_route_metadata_hit(self):
        result = router.route("scenes", "提示词")
        self.assertIsNone(result["primary"])
        self.assertEqual(result["eligible"], [])

    def test_weak_term_is_fallback(self):
        result = router.route("moves", "剑")
        self.assertTrue(result["weak_fallback"])
        self.assertIsNotNone(result["primary"])

    def test_strong_route_match_suppresses_weak_only_candidates(self):
        result = router.route("moves", "长枪 连招")
        self.assertFalse(result["weak_fallback"])
        self.assertEqual(result["primary"]["id"], "21")
        self.assertNotIn("35", [item["id"] for item in result["eligible"]])

    def test_sword_flight_routes_to_dedicated_entry(self):
        result = router.route("moves", "仙子御剑飞行 剑尖朝前 剑柄朝后")
        self.assertEqual(result["primary"]["id"], "38")
        self.assertIn("剑尖朝前", result["primary"]["matched_keywords"])
        self.assertIn("剑柄朝后", result["primary"]["matched_keywords"])

    def test_read_accepts_id_and_catalog_file_name(self):
        by_id = router.read("scenes/03")
        by_name = router.read("scenes/03-古代武侠.txt")
        self.assertEqual(by_id, by_name)

    def test_index_rules_are_returned(self):
        result = router.route("moves", "长枪")
        self.assertTrue(result["routing_rules"])
        self.assertIn("conflict_resolution", result)

    def test_cli_success_and_failure_exit_codes(self):
        success = subprocess.run(
            [sys.executable, "-X", "utf8", str(SCRIPT), "--read", "moves/35"],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(success.returncode, 0, success.stderr)
        self.assertGreater(len(success.stdout.strip()), 10)

        failure = subprocess.run(
            [sys.executable, "-X", "utf8", str(SCRIPT), "--read", "moves/99"],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertNotEqual(failure.returncode, 0)
        self.assertIn("未找到", failure.stderr)

    def test_cli_query_returns_json(self):
        completed = subprocess.run(
            [sys.executable, "-X", "utf8", str(SCRIPT), "scenes", "--query", "屋顶"],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["scope"], "scenes")


if __name__ == "__main__":
    unittest.main()
