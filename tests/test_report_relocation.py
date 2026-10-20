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

    def test_relocated_prepare_reuses_current_then_archived_exploration(self):
        """Real prepare/init lifecycle only; no R, research or real review occurs."""
        import update_reader_copy as update

        source = self.process / "definition_search_record.json"
        source.write_text('{"database":"synthetic","topic_id":"999","definition_plan":{"formula":"x"}}', encoding="utf-8")
        old_process = "Z:\\synthetic_missing_history\\process"
        self.write_map([{"old": self.old, "new": str(self.formal)},
                        {"old": old_process, "new": str(self.process)}])
        raw = self.formal / "raw_codebook.csv"
        raw.write_text("Variable,newname\nx,x\n", encoding="utf-8")
        (self.formal / "raw_data.csv").write_text("x\n1\n", encoding="utf-8")
        (self.formal / "文案.md").write_text("Synthetic fixture; no actual review or research.", encoding="utf-8")

        def historical_bindings(paths):
            bound = er.input_hashes(paths, source_scope="research_v1")
            return {(self.old if Path(path).parent == self.formal else old_process) + "\\" + Path(path).name: digest
                    for path, digest in bound.items()}

        start, finish = "2026-01-01T00:00:00Z", "2026-01-01T00:02:00Z"
        report = {"schema_version": 1, "run_id": "synthetic-history", "database": "synthetic", "topic_id": "999",
                  "topic_name": "Synthetic relocation lifecycle fixture", "task": "Synthetic only", "workflow": "general",
                  "status": "completed", "started_at": start, "finished_at": finish, "summary": [], "issues": [],
                  "stages": [], "stage_reviews": {}, "reviews": [], "primary_agent_id": "synthetic-primary",
                  "exploration_policy": eh.POLICY}

        def add_review(role, agent_id, inputs):
            report["reviews"].append({"role": role, "agent_id": agent_id, "closed": True, "unfinished_turns": 0,
                                      "rounds": [{"started_at": start, "outcome": "completed"}]})
            report["stage_reviews"][role] = {"status": "pass", "mode": "independent", "agent_id": agent_id,
                "started_at": start, "finished_at": finish, "inputs": copy.deepcopy(inputs), "source_scope": "research_v1",
                "evidence": "Synthetic test fixture, not an actual review"}

        common = historical_bindings([source])
        report["exploration"] = {"started_at": start, "inputs": common, "branches": {}}
        outputs = {}
        for branch, role in eh.ROLES.items():
            output = self.process / ("synthetic_branch_" + branch + ".md")
            output.write_text("Synthetic branch evidence " + branch, encoding="utf-8")
            outputs[branch] = output
            add_review(role, "synthetic-agent-" + branch, common)
            report["exploration"]["branches"][branch] = {"agent_id": "synthetic-agent-" + branch,
                "review_started_at": start, "review_finished_at": finish, "outputs": historical_bindings([output])}
        decision = self.process / "synthetic_decision.md"
        decision.write_text("Synthetic merge fixture only", encoding="utf-8")
        report["exploration"]["merge"] = {"status": "ready", "unresolved": [], "decision": historical_bindings([decision]),
            "record": old_process + "\\" + source.name, "plan_hash": eh.plan_hash(source, 2), "hash_version": 2}
        add_review(er.COMBINED_REVIEW_ROLE, "synthetic-r-agent", historical_bindings([self.input, source, raw]))
        current_path = self.process / er.REPORT_NAME
        update.write(current_path, report)
        original_bytes = current_path.read_bytes()
        result = {"ok": True, "scope": "complete", "artifacts": {path.name: update.digest(path) for path in self.formal.iterdir()},
                  "source_sha256": update.digest(source)}
        update.write(self.process / "result_check.json", result)
        update.write(self.process / "readability_audit.json", {"unresolved_issues": [], "artifacts": {}})
        update.write(self.process / "definition_change_impact.json", {"schema_version": 3, "changed_dimensions": ["copy"]})
        args = SimpleNamespace(formal_dir=self.formal, process_dir=self.process, path_map=self.map_path,
                               legacy_report=None, reason="Synthetic prepare lifecycle; no real review, R or production generation")
        self.assertEqual(update.prepare(args)["status"], "PREPARED")
        first = update.read(current_path)
        eh.validate_exploration(first, source)
        inherited = first["exploration"]
        self.assertEqual(inherited["started_at"], start)
        self.assertEqual(inherited["merge"]["plan_hash"], report["exploration"]["merge"]["plan_hash"])
        for branch, role in eh.ROLES.items():
            self.assertEqual(inherited["branches"][branch]["agent_id"], report["exploration"]["branches"][branch]["agent_id"])
            self.assertEqual(list(inherited["branches"][branch]["outputs"].values()),
                             list(report["exploration"]["branches"][branch]["outputs"].values()))
            for key in ("agent_id", "started_at", "finished_at"):
                self.assertEqual(first["stage_reviews"][role][key], report["stage_reviews"][role][key])
            self.assertEqual(first["stage_reviews"][role]["prior_agent_record"],
                             next(agent for agent in report["reviews"] if agent["role"] == role))
        snapshot = Path(inherited["from_report"])
        self.assertEqual(snapshot.read_bytes(), original_bytes)
        self.assertEqual(inherited["from_report_hash"], hashlib.sha256(original_bytes).hexdigest())
        self.assertEqual((self.process / "archived_runs" / "synthetic-history" / er.REPORT_NAME).read_bytes(), original_bytes)

        def finish_synthetic_run():
            # Simulate an ended fixture run; no claims of production completion.
            current = update.read(current_path)
            current.update(status="completed", finished_at=er.iso())
            for stage in current["stages"]:
                stage.update(status="completed", finished_at=er.iso())
            update.write(current_path, current)

        args.path_map = None
        finish_synthetic_run()
        self.assertEqual(update.prepare(args)["status"], "PREPARED")
        # The general update's next init archives the already relocated source;
        # a later prepare must discover that archive, never the missing old root.
        finish_synthetic_run()
        self.assertEqual(update.prepare(args)["status"], "PREPARED")
        self.assertEqual(snapshot.read_bytes(), original_bytes)
        finish_synthetic_run()
        outputs["a"].write_text("Changed synthetic evidence", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "产出已变化"):
            update.prepare(args)


if __name__ == "__main__":
    unittest.main()
