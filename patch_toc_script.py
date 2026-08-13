#!/usr/bin/env python3
"""
Safely patch build_toc_ui_phase2_final.py.

Fixes:
1. Windows atomic-write WinError 32.
2. React lint purity errors caused by Date.now() during rendering.
3. Unused React import in generated src/App.tsx.
4. Avoids unsafe global find-and-replace operations.
5. Creates a timestamped backup before changing anything.
6. Validates Python syntax after patching.

Run from the TOC project root:

    python .\\patch_toc_script.py
"""

from __future__ import annotations

import ast
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path


TARGET_FILENAME = "build_toc_ui_phase2_final.py"


def find_target() -> Path:
    """Locate the target builder script."""
    current = Path.cwd()

    candidates = [
        current / TARGET_FILENAME,
        current.parent / TARGET_FILENAME,
    ]

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()

    matches = [
        path
        for path in current.rglob(TARGET_FILENAME)
        if path.is_file() and "_backups" not in path.parts
    ]

    if len(matches) == 1:
        return matches[0].resolve()

    if not matches:
        raise FileNotFoundError(
            f"Could not find {TARGET_FILENAME}.\n"
            "Place this patch script in the TOC project root beside the builder script."
        )

    match_list = "\n".join(f" - {path}" for path in matches)
    raise RuntimeError(
        f"Found multiple copies of {TARGET_FILENAME}:\n{match_list}\n"
        "Keep the intended builder script in the TOC project root and run again."
    )


def create_backup(target: Path) -> Path:
    """Create a timestamped backup beside the target script."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = target.with_name(f"{target.stem}.before_patch_{timestamp}.py")
    shutil.copy2(target, backup)
    return backup


def replace_exactly_once(
    text: str,
    old: str,
    new: str,
    label: str,
) -> str:
    """Replace text only when exactly one match exists."""
    count = text.count(old)

    if count == 0:
        raise RuntimeError(
            f"Could not find the expected text for: {label}.\n"
            "The target script may already be patched or may differ from the expected version."
        )

    if count != 1:
        raise RuntimeError(
            f"Found {count} copies of the text for: {label}.\n"
            "Refusing an unsafe replacement."
        )

    return text.replace(old, new, 1)


def replace_assignment_block(
    source: str,
    variable_name: str,
    transform,
) -> str:
    """
    Locate a Python triple-quoted string assignment and transform only its content.

    Supports:
        NAME = \"\"\"...\"\"\"
        NAME = '''...'''
    """
    pattern = re.compile(
        rf"(?P<prefix>^{re.escape(variable_name)}\s*=\s*)"
        rf"(?P<quote>\"\"\"|''')"
        rf"(?P<body>.*?)"
        rf"(?P=quote)",
        re.MULTILINE | re.DOTALL,
    )

    matches = list(pattern.finditer(source))

    if len(matches) != 1:
        raise RuntimeError(
            f"Expected exactly one {variable_name} string assignment, "
            f"but found {len(matches)}."
        )

    match = matches[0]
    original_body = match.group("body")
    updated_body = transform(original_body)

    if updated_body == original_body:
        print(f"{variable_name}: already patched or no change required.")
        return source

    replacement = (
        match.group("prefix")
        + match.group("quote")
        + updated_body
        + match.group("quote")
    )

    return source[: match.start()] + replacement + source[match.end() :]


def patch_atomic_write(source: str) -> str:
    """
    Ensure os.replace() happens after NamedTemporaryFile has closed.

    The original unsafe version performs stat and os.replace inside the
    `with NamedTemporaryFile(...)` block. Windows can reject that operation.
    """
    function_pattern = re.compile(
        r"def atomic_write_text\(\s*"
        r"destination:\s*Path,\s*"
        r"content:\s*str,\s*"
        r"temp_files:\s*Set\[Path\],\s*"
        r"\)\s*->\s*None:"
        r".*?"
        r"(?=\ndef [A-Za-z_]\w*\(|\n# ---- File Content Definitions ----)",
        re.DOTALL,
    )

    matches = list(function_pattern.finditer(source))

    if len(matches) != 1:
        raise RuntimeError(
            "Could not uniquely locate the atomic_write_text function."
        )

    corrected_function = '''def atomic_write_text(
    destination: Path,
    content: str,
    temp_files: Set[Path],
) -> None:
    """
    Atomically write text content to destination.

    The temporary file is fully closed before os.replace() runs.
    This prevents WinError 32 on Windows.
    """
    tmp_path: Optional[Path] = None

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            delete=False,
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
        ) as tmp:
            tmp_path = Path(tmp.name)
            temp_files.add(tmp_path)

            tmp.write(content)
            tmp.flush()
            os.fsync(tmp.fileno())

        # NamedTemporaryFile is closed before validation and replacement.
        if tmp_path.stat().st_size == 0:
            raise ValueError(
                f"Generated temporary file is empty: {destination}"
            )

        os.replace(tmp_path, destination)
        temp_files.discard(tmp_path)

    except Exception:
        if tmp_path is not None and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass

        if tmp_path is not None:
            temp_files.discard(tmp_path)

        raise

'''

    match = matches[0]
    current_function = match.group(0)

    # Avoid rewriting when the corrected behavior is already present.
    closed_comment_present = (
        "NamedTemporaryFile is closed before validation and replacement"
        in current_function
    )

    if closed_comment_present:
        print("atomic_write_text: already patched.")
        return source

    return (
        source[: match.start()]
        + corrected_function
        + source[match.end() :]
    )

def patch_notification_center(body: str) -> str:
    """Patch NotificationCenter without depending on exact spacing."""
    result = body

    # Add a stable render-time value after useNotifications().
    if "const [renderTime] = React.useState(() => Date.now());" not in result:
        hook_pattern = re.compile(
            r"(?m)^(?P<indent>[ \t]*)"
            r"const\s*\{\s*notifications\s*,\s*clearNotification\s*,\s*clearAll\s*\}"
            r"\s*=\s*useNotifications\(\);\s*$"
        )

        result, count = hook_pattern.subn(
            lambda m: (
                m.group(0)
                + "\n"
                + m.group("indent")
                + "const [renderTime] = React.useState(() => Date.now());"
            ),
            result,
            count=1,
        )

        if count != 1:
            raise RuntimeError(
                "Could not locate the NotificationCenter useNotifications line."
            )
    else:
        print("NotificationCenter renderTime state: already patched.")

    # Replace Date.now() inside formatTime with the stable renderTime.
    if "const diff = renderTime - ts;" not in result:
        diff_pattern = re.compile(
            r"(?m)^(?P<indent>[ \t]*)"
            r"const\s+diff\s*=\s*Date\.now\(\)\s*-\s*ts\s*;\s*$"
        )

        result, count = diff_pattern.subn(
            lambda m: (
                m.group("indent")
                + "const diff = renderTime - ts;"
            ),
            result,
            count=1,
        )

        if count != 1:
            raise RuntimeError(
                "Could not locate the NotificationCenter Date.now() calculation."
            )
    else:
        print("NotificationCenter Date.now calculation: already patched.")

    return result


def patch_execution_log_panel(body: str) -> str:
    """Patch ExecutionLogPanel without depending on exact spacing."""
    result = body

    # Add a stable render-time value after useLogs().
    if "const [renderTime] = React.useState(() => Date.now());" not in result:
        hook_pattern = re.compile(
            r"(?m)^(?P<indent>[ \t]*)"
            r"const\s*\{\s*logs\s*,\s*clearLogs\s*\}"
            r"\s*=\s*useLogs\(\);\s*$"
        )

        result, count = hook_pattern.subn(
            lambda m: (
                m.group(0)
                + "\n"
                + m.group("indent")
                + "const [renderTime] = React.useState(() => Date.now());"
            ),
            result,
            count=1,
        )

        if count != 1:
            raise RuntimeError(
                "Could not locate the ExecutionLogPanel useLogs line."
            )
    else:
        print("ExecutionLogPanel renderTime state: already patched.")

    # Replace Date.now() inside formatTime with the stable renderTime.
    if "const diff = renderTime - ts;" not in result:
        diff_pattern = re.compile(
            r"(?m)^(?P<indent>[ \t]*)"
            r"const\s+diff\s*=\s*Date\.now\(\)\s*-\s*ts\s*;\s*$"
        )

        result, count = diff_pattern.subn(
            lambda m: (
                m.group("indent")
                + "const diff = renderTime - ts;"
            ),
            result,
            count=1,
        )

        if count != 1:
            raise RuntimeError(
                "Could not locate the ExecutionLogPanel Date.now() calculation."
            )
    else:
        print("ExecutionLogPanel Date.now calculation: already patched.")

    return result



def patch_app_tsx(body: str) -> str:
    """Remove the unused React default import from generated App.tsx."""
    unused_import = "import React from 'react';\n"

    if unused_import in body:
        return replace_exactly_once(
            body,
            unused_import,
            "",
            "unused React import in APP_TSX",
        )

    print("APP_TSX: unused React import already removed.")
    return body


def validate_python(source: str, filename: str) -> None:
    """Validate Python syntax without executing the builder script."""
    try:
        ast.parse(source, filename=filename)
    except SyntaxError as exc:
        raise RuntimeError(
            f"Patched script has invalid Python syntax:\n"
            f"Line {exc.lineno}, column {exc.offset}: {exc.msg}"
        ) from exc


def main() -> int:
    print("TOC builder patch utility")
    print("-------------------------")

    try:
        target = find_target()
        print(f"Target: {target}")

        original = target.read_text(encoding="utf-8")
        patched = original

        patched = patch_atomic_write(patched)

        patched = replace_assignment_block(
            patched,
            "NOTIFICATION_CENTER",
            patch_notification_center,
        )

        patched = replace_assignment_block(
            patched,
            "EXECUTION_LOG_PANEL",
            patch_execution_log_panel,
        )

        patched = replace_assignment_block(
            patched,
            "APP_TSX",
            patch_app_tsx,
        )

        validate_python(patched, target.name)

        if patched == original:
            print("\nNo changes were required. The builder script is already patched.")
            return 0

        backup = create_backup(target)
        print(f"Backup: {backup}")

        target.write_text(patched, encoding="utf-8", newline="\n")

        # Re-read and validate the actual saved file.
        saved = target.read_text(encoding="utf-8")
        validate_python(saved, target.name)

        print("\nPatch completed successfully.")
        print("\nRun these commands next:")
        print(f" python -m py_compile .\\{target.name}")
        print(f" python .\\{target.name}")

        return 0

    except Exception as exc:
        print(f"\nPatch failed: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
