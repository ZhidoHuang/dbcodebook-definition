"""Synthetic path-migration fixtures; these make no real review claims."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from report_relocation import ReportRelocation, _absolute
import execution_report as er
import exploration_handoff as eh


class RelocationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.formal = self.root / "formal"
        self.process = self.root / "process"
        self.formal.mkdir()
        self.process.mkdir()
        self.old = "Z:\\synthetic_missing_history\\formal"
        self.input = self.formal / "definition.R"
        self.input.write_text("x <- 1\n# 输出\nprint(x)\n", encoding="utf-8")
        self.record = self.formal / "definition_search_record.json"
        self.record.write_text('{"research": "synthetic"}', encoding="utf-8")
        self.map_path = self.root / "map.json"
        self.write_map([{"old": self.old, "new": str(self.formal)}])
        self.role = "synthetic review"
        self.data = {"status": "failed", "business": {"keep": True}, "stage_reviews": {
            self.role: {"status": "pass", "mode": "isolated", "limitation": "Synthetic fixture only",
                        "evidence": "Synthetic fixture only; no real audit", "r_scope": "public",
                        "source_scope": "research_v1", "reused_from": "Z:\\absent\\report.json",
                        "inputs": self.old_bindings([self.input, self.record])}}}
        self.report_path = self.process / "historical.json"
        self.write_report()

    def write_map(self, roots):
        self.map_path.write_text(json.dumps({"schema_version": 1, "roots": roots}), encoding="utf-8")

    def write_report(self):
        self.report_path.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")

    def old_bindings(self, paths, scope="public"):
        return {self.old + "\\" + Path(path).name: value for path, value in
                er.input_hashes(paths, scope, "research_v1").items()}

    def helper(self):
        return ReportRelocation(self.map_path, self.formal, self.process)

    def projected(self):
        return self.helper().report(self.report_path, roles=(self.role,))

    def test_read_only_cli(self):
        import subprocess
        import sys
        command = [sys.executable, '-X', 'utf8', str(Path(__file__).resolve().parents[1]/'scripts/report_relocation.py'),
                   '--report', str(self.report_path), '--path-map', str(self.map_path),
                   '--formal-dir', str(self.formal), '--process-dir', str(self.process),
                   '--role', self.role]
        snapshot = lambda: {str(p): p.read_bytes() for p in self.process.parent.rglob('*') if p.is_file()}
        before = snapshot()
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)['current_report_modified'])
        self.assertEqual(snapshot(), before)
        self.input.write_text('changed calculation', encoding='utf-8')
        before = snapshot()
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(snapshot(), before)

    def test_relocation_preserves_original_and_failed_status(self):
        before = self.report_path.read_bytes()
        helper = self.helper()
        projected = helper.report(self.report_path, roles=(self.role,))
        er.validate_stage_review(projected, self.role)
        self.assertEqual(projected["status"], "failed")
        self.assertEqual(projected["business"], self.data["business"])
        self.assertEqual(projected["stage_reviews"][self.role]["reused_from"], self.data["stage_reviews"][self.role]["reused_from"])
        self.assertEqual(self.report_path.read_bytes(), before)
        evidence = helper.save_evidence(self.process / "relocation")
        self.assertEqual(Path(evidence["reports"][0]["snapshot"]).read_bytes(), before)
        self.assertEqual(evidence["reports"][0]["sha256"], hashlib.sha256(before).hexdigest())
        with self.assertRaises(FileExistsError):
            helper.save_evidence(self.process / "relocation")
        projected["stage_reviews"][self.role]["status"] = "failed"
        with self.assertRaises(ValueError):
            er.validate_stage_review(projected, self.role)
        self.data["stage_reviews"][self.role]["status"] = "failed"
        self.write_report()
        with self.assertRaises(ValueError):
            er.validate_stage_review(self.projected(), self.role)

    def test_public_r_and_research_mutations_rejected_by_existing_validator(self):
        self.input.write_text("x <- 2\n# 输出\nprint(x)\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            er.validate_stage_review(self.projected(), self.role)
        self.input.write_text("x <- 1\n# 输出\nprint(x)\n", encoding="utf-8")
        self.record.write_text('{"research": "changed"}', encoding="utf-8")
        with self.assertRaises(ValueError):
            er.validate_stage_review(self.projected(), self.role)

    def test_byte_hash_changes_rejected(self):
        self.data["stage_reviews"][self.role]["r_scope"] = "full"
        self.data["stage_reviews"][self.role]["inputs"] = self.old_bindings([self.input], "full")
        self.write_report()
        self.input.write_bytes(self.input.read_bytes() + b"\n")
        with self.assertRaises(ValueError):
            er.validate_stage_review(self.projected(), self.role)

    def test_only_selected_review_bindings_change(self):
        self.data["stage_reviews"]["unselected"] = copy.deepcopy(self.data["stage_reviews"][self.role])
        self.write_report()
        projected = self.projected()
        self.assertEqual(projected["stage_reviews"]["unselected"], self.data["stage_reviews"]["unselected"])

    def test_missing_and_unmapped_files_rejected(self):
        self.input.unlink()
        with self.assertRaises(FileNotFoundError):
            self.projected()
        self.data["stage_reviews"][self.role]["inputs"] = {"Z:\\external\\file.R": "unchanged"}
        self.write_report()
        with self.assertRaises(ValueError):
            self.projected()

    def test_overlap_duplicate_destination_and_outside_rejected(self):
        nested = self.formal / "nested"
        nested.mkdir()
        cases = [
            [{"old": self.old, "new": str(self.formal)}, {"old": self.old + "\\nested", "new": str(self.process)}],
            [{"old": self.old, "new": str(self.formal)}, {"old": "Z:\\different", "new": str(self.formal)}],
            [{"old": self.old, "new": str(self.formal)}, {"old": "Z:\\different", "new": str(nested)}],
            [{"old": self.old, "new": str(self.root)}],
            [{"old": str(self.formal), "new": str(nested)}],
        ]
        for roots in cases:
            with self.subTest(roots=roots):
                self.write_map(roots)
                with self.assertRaises(ValueError):
                    self.helper()

    def test_parent_traversal_rejected_and_posix_parsing_supported(self):
        self.assertEqual(str(_absolute("/old/report.json")), "/old/report.json")
        self.data["stage_reviews"][self.role]["inputs"] = {self.old + "\\..\\file.R": "unchanged"}
        self.write_report()
        with self.assertRaises(ValueError):
            self.projected()

    def test_posix_history_maps_without_original_directory(self):
        review = self.data["stage_reviews"][self.role]
        review["inputs"] = {"/synthetic_missing_history/" + Path(path).name: digest
                            for path, digest in er.input_hashes([self.input, self.record], "public", "research_v1").items()}
        self.write_map([{"old": "/synthetic_missing_history", "new": str(self.formal)}])
        self.write_report()
        er.validate_stage_review(self.projected(), self.role)

    def test_symlink_escape_rejected(self):
        outside_dir = self.root / "outside"
        outside_dir.mkdir()
        outside = outside_dir / "definition.R"
        outside.write_text("synthetic", encoding="utf-8")
        link = self.formal / "linked"
        try:
            link.symlink_to(outside_dir, target_is_directory=True)
        except OSError:
            # Windows directory junctions exercise the same resolve boundary
            # without requiring the symlink privilege or developer mode.
            try:
                import _winapi
                _winapi.CreateJunction(str(outside_dir), str(link))
            except (ImportError, OSError) as error:
                self.skipTest("Creating links unavailable: " + str(error))
        self.data["stage_reviews"][self.role]["inputs"] = {self.old + "\\linked\\definition.R": "unchanged"}
        self.write_report()
        with self.assertRaises(ValueError):
            self.projected()

    def test_exploration_validates_and_retains_hashes(self):
        inputs = self.old_bindings([self.input], "full")
        exploration = {"inputs": inputs, "branches": {}, "merge": {}}
        self.data.update(exploration_policy=eh.POLICY, primary_agent_id="synthetic-primary", exploration=exploration)
        for key, role in eh.ROLES.items():
            output = self.formal / (key + ".txt")
            output.write_text("synthetic " + key, encoding="utf-8")
            agent_id = "synthetic-" + key
            started = "2026-01-01T00:00:00+00:00"
            finished = "2026-01-01T00:01:00+00:00"
            agent = {"agent_id": agent_id, "role": role, "closed": True, "unfinished_turns": [],
                     "rounds": [{"started_at": started, "outcome": "completed"}]}
            self.data["stage_reviews"][role] = {"status": "pass", "mode": "independent", "inputs": copy.deepcopy(inputs),
                "agent_id": agent_id, "started_at": started, "finished_at": finished,
                "evidence": "Synthetic fixture only; no actual review", "prior_agent_record": agent}
            exploration["branches"][key] = {"agent_id": agent_id, "review_started_at": started,
                "review_finished_at": finished, "outputs": self.old_bindings([output], "full")}
        decision = self.formal / "decision.txt"
        decision.write_text("synthetic decision", encoding="utf-8")
        exploration["merge"] = {"status": "ready", "unresolved": [], "decision": self.old_bindings([decision], "full"),
            "record": self.old + "\\" + self.record.name, "hash_version": 2, "plan_hash": eh.plan_hash(self.record, 2)}
        previous = self.formal / "previous.json"
        previous.write_bytes(b'{"synthetic":true}')
        exploration["from_report"] = self.old + "\\" + previous.name
        exploration["from_report_hash"] = hashlib.sha256(previous.read_bytes()).hexdigest()
        self.write_report()
        projected = self.helper().report(self.report_path, exploration=True)
        eh.validate_exploration(projected, self.record)
        self.assertEqual(projected["status"], "failed")
        self.assertEqual(projected["exploration"]["merge"]["plan_hash"], exploration["merge"]["plan_hash"])
        previous.write_bytes(b'{"synthetic":false}')
        with self.assertRaises(ValueError):
            eh.validate_exploration(projected)



if __name__ == "__main__":
    unittest.main()
