from jobscope.cli import main
from jobscope.core.store import Store


def test_campaign_cli_creates_and_lists_ranked_targets(tmp_path, capsys):
    path = tmp_path / "campaign-cli.db"

    assert main([
        "--db", str(path), "campaign", "create",
        "--name", "India security", "--count", "2",
    ]) == 0
    output = capsys.readouterr().out
    assert "created campaign:" in output and "India security" in output

    store = Store(str(path))
    values = store.outreach_campaigns()
    assert len(values) == 1 and values[0]["requested_count"] == 2
    assert len(store.outreach_campaign_targets(values[0]["id"])) == 2
    store.close()

    assert main(["--db", str(path), "campaign", "list"]) == 0
    listed = capsys.readouterr().out
    assert values[0]["id"] in listed and "ranked=2" in listed

    assert main(["--db", str(path), "campaign", "replies"]) == 0
    assert "0 replied, 0 opted out" in capsys.readouterr().out