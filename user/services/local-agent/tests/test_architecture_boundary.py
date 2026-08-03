from pathlib import Path
import re


def test_customer_python_does_not_import_administrator_source():
    user_root = Path(__file__).resolve().parents[3]
    illegal = re.compile(
        r"^\s*(?:from|import)\s+(?:license_server|payment_server|payment_signer)(?:\.|\s|$)",
        re.MULTILINE,
    )
    violations = []
    for path in user_root.rglob("*.py"):
        if "__pycache__" not in path.parts and illegal.search(path.read_text(encoding="utf-8")):
            violations.append(str(path.relative_to(user_root)))
    assert not violations, f"customer source imports administrator code: {violations}"
