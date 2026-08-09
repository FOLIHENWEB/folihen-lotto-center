from pathlib import Path
from datetime import datetime
from docx import Document
import argparse
import re
import sys


MASTER_DATA_DIR = Path.home() / "Documents" / "MASTER_DATA"
EXPECTED_GAME_COUNT = 19


# ============================================================
# BASIC TEXT HELPERS
# ============================================================

def clean_text(value):
    """Normalize whitespace without changing source meaning."""
    if value is None:
        return ""

    return " ".join(str(value).split()).strip()


# ============================================================
# MASTER_DATA FILE DISCOVERY
# ============================================================

def get_master_data_files():
    """
    Return genuine MASTER_DATA DOCX files only.

    Microsoft Word temporary files beginning with ~$ are ignored.
    """
    if not MASTER_DATA_DIR.is_dir():
        return []

    return sorted(
        [
            path
            for path in MASTER_DATA_DIR.glob("*.docx")
            if path.is_file()
            and not path.name.startswith("~$")
        ],
        key=lambda path: path.name.lower(),
    )


# ============================================================
# DATE NORMALIZATION / PARSING
# ============================================================

def normalize_date_text(value):
    """
    Normalize MASTER_DATA date variations.

    Examples accepted:

        4th Jan, 24
        17th March,26
        21st April. 26
        9th May. 26
        21th Feb,26
        24th Feb,26

    The source DOCX is never changed.
    """

    value = clean_text(value)

    if not value:
        return ""

    # --------------------------------------------------------
    # Remove ordinal suffixes:
    #
    # 1st  -> 1
    # 2nd  -> 2
    # 3rd  -> 3
    # 4th  -> 4
    #
    # Also intentionally accepts malformed ordinal suffixes
    # such as "21th" because the numerical date is still clear.
    # --------------------------------------------------------

    value = re.sub(
        r"(\d{1,2})(st|nd|rd|th)\b",
        r"\1",
        value,
        flags=re.IGNORECASE,
    )

    # --------------------------------------------------------
    # Normalize punctuation between month and year.
    #
    # April. 26  -> April, 26
    # May. 26    -> May, 26
    # --------------------------------------------------------

    value = re.sub(
        r"\.\s*(?=\d{2,4}\b)",
        ", ",
        value,
    )

    # --------------------------------------------------------
    # Normalize comma spacing.
    #
    # March,26 -> March, 26
    # Feb,26  -> Feb, 26
    # --------------------------------------------------------

    value = re.sub(
        r",\s*",
        ", ",
        value,
    )

    # Remove repeated spaces one final time.
    value = clean_text(value)

    return value


def parse_date(value):
    """
    Parse normalized MASTER_DATA dates into datetime.date.
    """

    value = normalize_date_text(value)

    if not value:
        return None

    formats = (
        "%d %b, %y",
        "%d %B, %y",
        "%d %b %y",
        "%d %B %y",
        "%d/%m/%Y",
        "%d/%m/%y",
        "%Y-%m-%d",
    )

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue

    return None


# ============================================================
# DRAW NUMBER PARSING
# ============================================================

def parse_draw_numbers(value):
    """
    Parse draw-number strings such as:

        7-30-33-48-76

    into:

        [7, 30, 33, 48, 76]

    Supports standard and Unicode dash variants.
    """

    value = clean_text(value)

    if not value:
        return None

    parts = re.split(
        r"\s*[-–—]\s*",
        value,
    )

    numbers = []

    for part in parts:
        part = part.strip()

        if not part:
            return None

        if not re.fullmatch(r"\d+", part):
            return None

        numbers.append(int(part))

    return numbers if numbers else None


# ============================================================
# WORD TABLE READING
# ============================================================

def read_table(table):
    """Extract all non-empty rows from one Word table."""

    rows = []

    for row in table.rows:
        values = [
            clean_text(cell.text)
            for cell in row.cells
        ]

        if any(values):
            rows.append(values)

    return rows


def read_document(file_path):
    """
    Read one MASTER_DATA DOCX file.

    The source document is never modified.
    """

    document = Document(file_path)

    tables = [
        read_table(table)
        for table in document.tables
    ]

    paragraphs = [
        clean_text(paragraph.text)
        for paragraph in document.paragraphs
        if clean_text(paragraph.text)
    ]

    return {
        "game": file_path.stem,
        "file": file_path.name,
        "tables": tables,
        "paragraphs": paragraphs,
    }


# ============================================================
# GAME SCHEMA INSPECTION
# ============================================================

def inspect_game(file_path):
    """
    Inspect one game's table structure and data quality.
    """

    data = read_document(file_path)

    result = {
        "game": file_path.stem,
        "tables": len(data["tables"]),
        "rows": 0,
        "data_rows": 0,
        "column_counts": set(),
        "draw_counts": set(),
        "headers": [],
        "bad_dates": 0,
        "bad_draws": 0,
        "bad_date_rows": [],
        "bad_draw_rows": [],
    }

    for table_rows in data["tables"]:

        if not table_rows:
            continue

        result["rows"] += len(table_rows)

        header = table_rows[0]
        result["headers"].append(header)

        for row in table_rows:
            result["column_counts"].add(
                len(row)
            )

        # First row is the table header.
        for physical_row_number, row in enumerate(
            table_rows[1:],
            start=2,
        ):

            if not any(row):
                continue

            result["data_rows"] += 1

            # ------------------------------------------------
            # STRUCTURAL CHECK
            # ------------------------------------------------

            if len(row) < 2:

                result["bad_dates"] += 1
                result["bad_draws"] += 1

                result["bad_date_rows"].append(
                    {
                        "row": physical_row_number,
                        "date": row[0] if row else "",
                        "draw": "",
                    }
                )

                result["bad_draw_rows"].append(
                    {
                        "row": physical_row_number,
                        "date": row[0] if row else "",
                        "draw": "",
                    }
                )

                continue

            # ------------------------------------------------
            # DATE CHECK
            # ------------------------------------------------

            parsed_date = parse_date(
                row[0]
            )

            if parsed_date is None:

                result["bad_dates"] += 1

                result["bad_date_rows"].append(
                    {
                        "row": physical_row_number,
                        "date": row[0],
                        "normalized_date": normalize_date_text(
                            row[0]
                        ),
                        "draw": row[1],
                    }
                )

            # ------------------------------------------------
            # DRAW CHECK
            # ------------------------------------------------

            numbers = parse_draw_numbers(
                row[1]
            )

            if numbers is None:

                result["bad_draws"] += 1

                result["bad_draw_rows"].append(
                    {
                        "row": physical_row_number,
                        "date": row[0],
                        "draw": row[1],
                    }
                )

            else:

                result["draw_counts"].add(
                    len(numbers)
                )

    return result


# ============================================================
# ALL-GAME INSPECTION
# ============================================================

def inspect_all_games():
    """
    Inspect schema consistency across all MASTER_DATA games.
    """

    files = get_master_data_files()

    print()
    print(
        "=== TOC PHASE 3: ALL-GAME SCHEMA INSPECTION ==="
    )

    print(
        f"Source: {MASTER_DATA_DIR}"
    )

    print(
        f"Expected games:  {EXPECTED_GAME_COUNT}"
    )

    print(
        f"Games discovered: {len(files)}"
    )

    print()

    readable = 0
    failed = 0

    total_data_rows = 0
    total_bad_dates = 0
    total_bad_draws = 0

    all_columns = set()
    all_draw_counts = set()
    all_headers = set()

    for index, file_path in enumerate(
        files,
        start=1,
    ):

        try:

            result = inspect_game(
                file_path
            )

            readable += 1

            total_data_rows += (
                result["data_rows"]
            )

            total_bad_dates += (
                result["bad_dates"]
            )

            total_bad_draws += (
                result["bad_draws"]
            )

            all_columns.update(
                result["column_counts"]
            )

            all_draw_counts.update(
                result["draw_counts"]
            )

            for header in result["headers"]:
                all_headers.add(
                    tuple(header)
                )

            columns = (
                ",".join(
                    str(value)
                    for value in sorted(
                        result["column_counts"]
                    )
                )
                or "none"
            )

            draw_counts = (
                ",".join(
                    str(value)
                    for value in sorted(
                        result["draw_counts"]
                    )
                )
                or "none"
            )

            print(
                f"{index:02d}. "
                f"{result['game']} | "
                f"tables={result['tables']} | "
                f"rows={result['rows']} | "
                f"data={result['data_rows']} | "
                f"columns={columns} | "
                f"draw-count={draw_counts} | "
                f"bad-dates={result['bad_dates']} | "
                f"bad-draws={result['bad_draws']}"
            )

            # --------------------------------------------
            # BAD DATE DETAILS
            # --------------------------------------------

            for bad in result["bad_date_rows"]:

                print(
                    f"    BAD DATE | "
                    f"row={bad['row']} | "
                    f"date={bad['date']!r} | "
                    f"normalized="
                    f"{bad.get('normalized_date', '')!r} | "
                    f"draw={bad['draw']!r}"
                )

            # --------------------------------------------
            # BAD DRAW DETAILS
            # --------------------------------------------

            for bad in result["bad_draw_rows"]:

                print(
                    f"    BAD DRAW | "
                    f"row={bad['row']} | "
                    f"date={bad['date']!r} | "
                    f"draw={bad['draw']!r}"
                )

        except Exception as exc:

            failed += 1

            print(
                f"{index:02d}. "
                f"{file_path.stem} | "
                f"ERROR: "
                f"{type(exc).__name__}: "
                f"{exc}"
            )

    # ========================================================
    # SUMMARY
    # ========================================================

    print()
    print(
        "=== SCHEMA SUMMARY ==="
    )

    print(
        f"Games discovered:    {len(files)}"
    )

    print(
        f"Games readable:      {readable}"
    )

    print(
        f"Games failed:        {failed}"
    )

    print(
        f"Total data rows:    {total_data_rows}"
    )

    print(
        f"Column counts seen:  "
        f"{sorted(all_columns)}"
    )

    print(
        f"Draw-number counts:  "
        f"{sorted(all_draw_counts)}"
    )

    print(
        f"Distinct headers:    "
        f"{len(all_headers)}"
    )

    print(
        f"Invalid date rows:  "
        f"{total_bad_dates}"
    )

    print(
        f"Invalid draw rows:  "
        f"{total_bad_draws}"
    )

    # ========================================================
    # HEADER REPORT
    # ========================================================

    print()
    print(
        "=== HEADERS DETECTED ==="
    )

    if all_headers:

        for index, header in enumerate(
            sorted(all_headers),
            start=1,
        ):

            print(
                f"{index:02d}. "
                f"{list(header)}"
            )

    else:

        print(
            "No headers detected."
        )

    # ========================================================
    # FINAL STATUS
    # ========================================================

    print()

    passed = (
        len(files) == EXPECTED_GAME_COUNT
        and readable == EXPECTED_GAME_COUNT
        and failed == 0
        and total_bad_dates == 0
        and total_bad_draws == 0
    )

    if passed:

        print(
            "ALL-GAME SCHEMA INSPECTION: PASSED"
        )

    else:

        print(
            "ALL-GAME SCHEMA INSPECTION: REVIEW REQUIRED"
        )

    return passed


# ============================================================
# SINGLE GAME PREVIEW
# ============================================================

def preview_game(
    game_name,
    max_rows=10,
):

    file_path = (
        MASTER_DATA_DIR
        / f"{game_name}.docx"
    )

    if not file_path.is_file():

        print(
            f"ERROR: File not found: "
            f"{file_path}"
        )

        return False

    data = read_document(
        file_path
    )

    print()

    print(
        f"=== TABLE PREVIEW: "
        f"{game_name} ==="
    )

    if not data["tables"]:

        print(
            "No tables found."
        )

        return False

    for table_index, rows in enumerate(
        data["tables"],
        start=1,
    ):

        column_count = max(
            (
                len(row)
                for row in rows
            ),
            default=0,
        )

        print()

        print(
            f"Table {table_index}: "
            f"{len(rows)} rows x "
            f"{column_count} columns"
        )

        for row_index, row in enumerate(
            rows[:max_rows],
            start=1,
        ):

            print(
                f"{row_index:02d}: "
                f"{row}"
            )

    return True


# ============================================================
# BASIC FILE VALIDATION
# ============================================================

def validate_files():

    files = get_master_data_files()

    print()

    print(
        "=== TOC PHASE 3: MASTER_DATA VALIDATION ==="
    )

    print(
        f"Source: {MASTER_DATA_DIR}"
    )

    print(
        f"Expected games:  {EXPECTED_GAME_COUNT}"
    )

    print(
        f"Games discovered: {len(files)}"
    )

    print()

    readable = 0
    failed = 0

    for index, file_path in enumerate(
        files,
        start=1,
    ):

        try:

            data = read_document(
                file_path
            )

            readable += 1

            print(
                f"{index:02d}. "
                f"{data['game']} | "
                f"tables="
                f"{len(data['tables'])} | "
                f"paragraphs="
                f"{len(data['paragraphs'])} | "
                f"READABLE"
            )

        except Exception as exc:

            failed += 1

            print(
                f"{index:02d}. "
                f"{file_path.stem} | "
                f"ERROR: "
                f"{type(exc).__name__}: "
                f"{exc}"
            )

    print()

    print(
        "=== VALIDATION SUMMARY ==="
    )

    print(
        f"Games discovered: "
        f"{len(files)}"
    )

    print(
        f"Games readable:  "
        f"{readable}"
    )

    print(
        f"Games failed:    "
        f"{failed}"
    )

    passed = (
        len(files) == EXPECTED_GAME_COUNT
        and readable == EXPECTED_GAME_COUNT
        and failed == 0
    )

    if passed:

        print(
            "MASTER_DATA validation: PASSED"
        )

    else:

        print(
            "MASTER_DATA validation: REVIEW REQUIRED"
        )

    return passed


# ============================================================
# COMMAND LINE
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "TOC Phase 3 MASTER_DATA reader"
        )
    )

    parser.add_argument(
        "--inspect-all",
        action="store_true",
        help=(
            "Inspect schema across all "
            "19 MASTER_DATA games"
        ),
    )

    parser.add_argument(
        "--preview",
        type=str,
        help=(
            "Preview one game without "
            "the .docx extension"
        ),
    )

    parser.add_argument(
        "--rows",
        type=int,
        default=10,
        help=(
            "Number of rows to show "
            "with --preview"
        ),
    )

    parser.add_argument(
        "--validate",
        action="store_true",
        help=(
            "Validate all MASTER_DATA files"
        ),
    )

    args = parser.parse_args()

    if not MASTER_DATA_DIR.is_dir():

        print(
            f"ERROR: MASTER_DATA folder "
            f"not found: "
            f"{MASTER_DATA_DIR}"
        )

        return 1

    if args.inspect_all:

        return (
            0
            if inspect_all_games()
            else 2
        )

    if args.preview:

        return (
            0
            if preview_game(
                args.preview,
                args.rows,
            )
            else 3
        )

    if args.validate:

        return (
            0
            if validate_files()
            else 4
        )

    parser.print_help()

    return 0


if __name__ == "__main__":
    sys.exit(main())