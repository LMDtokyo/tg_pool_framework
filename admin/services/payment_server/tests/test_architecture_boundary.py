from pathlib import Path
import re


def test_admin_python_does_not_import_customer_source():
    admin_root = Path(__file__).resolve().parents[3]
    illegal = re.compile(r"^\s*(?:from|import)\s+(?:tg_pool|src)(?:\.|\s|$)", re.MULTILINE)
    violations = []
    for path in admin_root.rglob("*.py"):
        if "__pycache__" not in path.parts and illegal.search(path.read_text(encoding="utf-8")):
            violations.append(str(path.relative_to(admin_root)))
    assert not violations, f"administrator source imports customer code: {violations}"
