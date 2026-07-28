import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _email_send_functions(path: Path) -> list[str]:
    tree = ast.parse(path.read_text("utf-8"))
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    functions = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "send"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "email"
        ):
            continue
        current = parents.get(node)
        while current is not None and not isinstance(
            current, (ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            current = parents.get(current)
        functions.append(current.name if current is not None else "<module>")
    return functions


def test_recruiter_smtp_originates_only_from_campaign_send_target():
    assert _email_send_functions(ROOT / "jobscope" / "apply" / "campaigns.py") == [
        "send_target",
    ]
    assert _email_send_functions(ROOT / "jobscope" / "apply" / "outreach.py") == []


def test_direct_outreach_routes_only_queue_durable_intents():
    source = (ROOT / "jobscope" / "apply" / "outreach.py").read_text("utf-8")
    for function in ("run", "api_send", "api_company_send"):
        tree = ast.parse(source)
        definition = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == function
        )
        calls = {
            node.func.attr
            for node in ast.walk(definition)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert "create_direct_intent" in calls
        assert "send" not in calls