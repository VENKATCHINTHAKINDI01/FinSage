"""Replace datetime.utcnow() with datetime.now(UTC) across the backend.

Run: python3 scripts/fix_utcnow.py
"""

import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"

SKIP_CODE_CHANGES = {
    "security/jwt_handler.py",
    "security/sessions.py",
    "security/tests/test_sessions.py",
}

changed_files = []

for pyfile in sorted(BACKEND.rglob("*.py")):
    rel = pyfile.relative_to(BACKEND)
    if str(rel) in SKIP_CODE_CHANGES:
        continue

    text = pyfile.read_text()
    if "datetime.utcnow()" not in text:
        continue

    lines = text.splitlines()
    has_code_occurrence = False
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if stripped.startswith('"""') or stripped.startswith("'''"):
            continue
        if "datetime.utcnow()" in line:
            has_code_occurrence = True
            break

    if not has_code_occurrence:
        continue

    new_text = text.replace("datetime.utcnow()", "datetime.now(UTC)")

    if "from datetime import" in new_text and "UTC" not in new_text:
        new_text = re.sub(
            r"from datetime import (datetime(?:,\s*\w+)*)",
            lambda m: m.group(0) + ", UTC" if "UTC" not in m.group(0) else m.group(0),
            new_text,
            count=1,
        )

    pyfile.write_text(new_text)
    changed_files.append(str(rel))
    print(f"  fixed: {rel}")

print(f"\nFixed {len(changed_files)} files.")
