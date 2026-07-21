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


def test_campaign_cli_requires_confirmation_to_delete_draft(tmp_path, capsys):
    path = tmp_path / "campaign-delete.db"
    with Store(str(path)) as store:
        campaign = store.create_outreach_campaign("Disposable", 1)
        store.upsert_outreach_campaign_target(campaign["id"], "Acme", "acme")

    command = [
        "--db", str(path), "campaign", "delete", "--campaign-id", campaign["id"],
    ]
    assert main(command) == 1
    assert "without --yes" in capsys.readouterr().err
    assert main([*command, "--yes"]) == 0
    assert f"deleted {campaign['id']}" in capsys.readouterr().out
    with Store(str(path)) as store:
        assert store.get_outreach_campaign(campaign["id"]) is None