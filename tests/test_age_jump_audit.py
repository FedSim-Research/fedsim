"""Independent fixtures for the retrospective, manifest-bound age-jump reader."""

import importlib
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def analysis(monkeypatch):
    folder = Path(__file__).resolve().parents[1] / "experiments/analysis"
    monkeypatch.syspath_prepend(str(folder))
    return importlib.import_module("generate_age_jump_audit")


SERVER = "11111111-1111-1111-1111-111111111111"
PEER = "22222222-2222-2222-2222-222222222222"


def line(before, after):
    return f"[{SERVER}] Aggregated model from {PEER}. Age jumped {before} -> {after}"


def test_positive_print_has_integer_delta_and_old_age_relative_scale(analysis):
    event = analysis.parse_positive_jump(line(40, 99))
    assert event == {
        "server_id": SERVER,
        "peer_id": PEER,
        "old_age": 40,
        "new_age": 99,
        "absolute_jump": 59,
        "relative_jump": 1.475,
    }
    assert analysis.parse_positive_jump(line(0, 2))["relative_jump"] is None
    assert analysis.parse_positive_jump("Ordinary non-jump telemetry") is None


@pytest.mark.parametrize("before,after", [(4, 4), (4, 3)])
def test_impossible_positive_print_is_rejected(analysis, before, after):
    with pytest.raises(ValueError, match="strictly positive"):
        analysis.parse_positive_jump(line(before, after))


def record(analysis, name, data):
    return {"path": name, "data": data, "sha256": analysis.sha(data)}


def test_duplicate_worker_files_count_once_without_deduplicating_event_lines(analysis):
    repeated = (line(1, 2) + "\n" + line(1, 2) + "\n").encode()
    logs = [
        record(analysis, "old/worker-a.out", repeated),
        record(analysis, "worker-a.out", repeated),
        record(analysis, "copy/worker-b.out", repeated),
    ]
    chosen, aliases = analysis.deduplicate_worker_logs(logs)
    assert len(chosen) == 1 and len(aliases) == 2
    assert chosen[0]["data"].count(b"Age jumped") == 2


def test_shorter_capture_must_be_a_byte_prefix_of_same_worker(analysis):
    rows = [
        record(analysis, "worker-a.out", b"first\nsecond\n"),
        record(analysis, "old/worker-a.out", b"first\n"),
    ]
    chosen, aliases = analysis.deduplicate_worker_logs(rows)
    assert chosen[0]["data"] == b"first\nsecond\n"
    assert aliases[0]["reason"] == "byte_prefix_of_retained_longest_capture"
    with pytest.raises(ValueError, match="Divergent copies"):
        analysis.deduplicate_worker_logs(
            rows + [record(analysis, "another/worker-a.out", b"different\n")]
        )


def test_worker_checksum_mismatch_fails_closed(analysis):
    with pytest.raises(ValueError, match="digest mismatch"):
        analysis.deduplicate_worker_logs(
            [{"path": "worker-a.out", "data": b"changed", "sha256": "0" * 64}]
        )


def test_age_accounting_distinguishes_client_progress_and_peer_age(analysis):
    events = [{"absolute_jump": 2}, {"absolute_jump": 4}]
    assert analysis.check_age_accounting({"model_age": 9, "total_client_updates": 3}, events) == (
        9,
        3,
        6,
    )
    assert analysis.check_age_accounting({"model_age": 3, "total_client_updates": 3}, []) == (
        3,
        3,
        0,
    )
    with pytest.raises(ValueError, match="does not match"):
        analysis.check_age_accounting({"model_age": 9, "total_client_updates": 3}, events[:1])


@pytest.mark.parametrize(
    "stats,events",
    [
        ({"model_age": True, "total_client_updates": 1}, []),
        ({"model_age": 1, "total_client_updates": -1}, []),
        ({"model_age": 1, "total_client_updates": 0}, [{"absolute_jump": True}]),
        ({"model_age": 1, "total_client_updates": 0}, [{"absolute_jump": -1}]),
    ],
)
def test_accounting_rejects_invalid_counters(analysis, stats, events):
    with pytest.raises(ValueError):
        analysis.check_age_accounting(stats, events)


def test_retained_case_has_exactly_one_segment(analysis):
    first = {"id": "a", "case_keys": ["accepted-a"]}
    second = {"id": "b", "case_keys": ["accepted-b"]}
    membership = {"segments": [first, second]}
    assert analysis.membership_segment(membership, "accepted-b") is second
    with pytest.raises(ValueError, match="missing"):
        analysis.membership_segment(membership, "failed-unretained-case")
    second["case_keys"].append("accepted-a")
    with pytest.raises(ValueError, match="Duplicate case"):
        analysis.membership_segment(membership, "accepted-a")


def test_manifest_bound_reader_rejects_tampering_and_path_escape(analysis, tmp_path):
    archive = analysis.Archive.__new__(analysis.Archive)
    archive.root, archive.used = tmp_path, {}
    (tmp_path / "worker.out").write_bytes(b"changed")
    archive.manifest = {"worker.out": analysis.sha(b"original"), "../outside": "0" * 64}
    with pytest.raises(ValueError, match="checksum mismatch"):
        archive.read("worker.out")
    with pytest.raises(ValueError):
        archive.read("../outside")


def test_validation_remains_active_under_python_optimized_mode(analysis):
    script = (
        "import sys; sys.path.insert(0, sys.argv[1]); "
        "from generate_age_jump_audit import require; require(False, 'guard stays active')"
    )
    result = subprocess.run(
        [sys.executable, "-O", "-c", script, str(Path(analysis.__file__).parent)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0 and "ValueError: guard stays active" in result.stderr


SOURCE_CONTRACT = """
class Server:
    def __init__(self):
        self.model_age: int = 0
    def on_client_update(self):
        self.model_age += 1
    def _handle_model_broadcast(self, sender_id, sender_age, effective_alpha):
        old_age = self.model_age
        weighted_age = (1.0 - effective_alpha) * self.model_age + effective_alpha * sender_age
        self.model_age = int(round(weighted_age))
        self.model_age = max(old_age, self.model_age)
        if self.model_age > old_age:
            print(f"[{self.server_id}] Aggregated model from {sender_id}. Age jumped {old_age} -> {self.model_age}")
"""


def test_source_contract_checks_print_predicate_and_all_age_writes(analysis):
    proof = analysis.verify_source_contract(SOURCE_CONTRACT.encode())
    assert proof["positive_branch_verified_by_ast"]
    assert len(proof["all_model_age_writes_verified_by_ast"]) == 4


@pytest.mark.parametrize(
    "source",
    [
        SOURCE_CONTRACT.replace("self.model_age > old_age", "self.model_age >= old_age"),
        SOURCE_CONTRACT.replace("Age jumped {old_age}", "Age jumped {sender_age}"),
        SOURCE_CONTRACT + "\n    def reset_age(self):\n        self.model_age = 0\n",
    ],
)
def test_changed_source_print_contract_is_rejected(analysis, source):
    with pytest.raises(ValueError):
        analysis.verify_source_contract(source.encode())
