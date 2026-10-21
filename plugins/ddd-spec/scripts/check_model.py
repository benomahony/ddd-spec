import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

SCHEMA = "https://benomahony.github.io/ddd-spec/v{version}/ddd.schema.json"
REJECTED = "Schema validation errors were encountered"


def manifest_above(path: Path) -> Path | None:
    return next((folder / "ddd.yaml" for folder in path.parents if (folder / "ddd.yaml").is_file()), None)


def listed(path: Path, manifest: Path) -> bool:
    relative = re.escape(path.relative_to(manifest.parent).as_posix())
    return path == manifest or re.search(rf"^\s+[a-z0-9][a-z0-9-]*:\s*['\"]?{relative}['\"]?\s*$", manifest.read_text(), re.MULTILINE) is not None


def main() -> int:
    edited = json.load(sys.stdin).get("tool_input", {}).get("file_path", "")
    if not edited.endswith((".yaml", ".yml")):
        return 0
    path = Path(edited).resolve()
    manifest = manifest_above(path)
    if manifest is None or not listed(path, manifest) or shutil.which("uvx") is None:
        return 0
    declared = re.search(r"^ddd_spec_version:[ \t]*(.*?)[ \t]*$", manifest.read_text(), re.MULTILINE)
    version = re.fullmatch(r"[\"']([0-9.]+)[\"']", declared.group(1)) if declared else None
    if version is None:
        problem = f"ddd_spec_version is {declared.group(1)}, which isn't a quoted version" if declared else "there is no ddd_spec_version"
        print(f"In {manifest}, {problem}; write it as ddd_spec_version: \"0.1\" so the files can be checked against their schema", file=sys.stderr)
        return 2
    schema = SCHEMA.format(version=version.group(1))
    command = ["uvx", "--quiet", "--with", "rfc3986-validator", "check-jsonschema", "--schemafile", schema, str(path)]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=100)
    except subprocess.TimeoutExpired:
        return 0
    if REJECTED not in result.stdout + result.stderr:
        return 0
    print(f"{path.name} doesn't match the ddd-spec {version.group(1)} schema ({schema}):\n{result.stdout.strip()}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
