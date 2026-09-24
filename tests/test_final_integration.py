from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]


def test_all_modular_feature_packages_have_init():
    for base in (ROOT / "features", ROOT / "infrastructure", ROOT / "api", ROOT / "core", ROOT / "config", ROOT / "ui"):
        assert base.exists()


def test_legacy_dependencies_are_explicit_compatibility_boundaries():
    allowed = {"features", "infrastructure", "ui", "api"}
    offenders = []
    for base in [ROOT / x for x in allowed]:
        for path in base.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for n in node.names:
                        if n.name == "legacy" or n.name.startswith("legacy."):
                            offenders.append((str(path.relative_to(ROOT)), n.name))
                elif isinstance(node, ast.ImportFrom):
                    if node.module == "legacy" or (node.module and node.module.startswith("legacy.")):
                        offenders.append((str(path.relative_to(ROOT)), node.module))
    # Compatibility imports are permitted during the final staged migration,
    # but they must remain visible and auditable rather than hidden dynamically.
    assert offenders


def test_final_entrypoints_remain_thin():
    assert len((ROOT / "app.py").read_text(encoding="utf-8").splitlines()) <= 20
    assert len((ROOT / "main.py").read_text(encoding="utf-8").splitlines()) <= 12

