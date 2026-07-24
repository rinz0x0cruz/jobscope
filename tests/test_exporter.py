import json

from jobscope.core.store import Store
from jobscope.deliver import exporter


def test_export_creates_missing_parent_directory(tmp_path):
    store = Store(str(tmp_path / "jobscope.db"))
    output = tmp_path / "nested" / "jobs.json"

    assert exporter.run(store, fmt="json", out=str(output)) == 0
    assert json.loads(output.read_text(encoding="utf-8")) == []
    store.close()