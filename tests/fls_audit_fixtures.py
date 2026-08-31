def report_with_changes(*, live_checksum: str = "live-a", affected: bool = True) -> dict:
    return {
        "metadata": {
            "baseline_commit": "a" * 40,
            "current_commit": "b" * 40,
            "generated_at": "2026-08-27T00:00:00+00:00",
            "spec_lock": "/tmp/src/spec.lock",
        },
        "changes": {
            "added": [
                {
                    "fls_id": "fls_added",
                    "live": {"checksum": live_checksum, "section_id": "1:1"},
                }
            ],
            "removed": [],
            "changed": [
                {
                    "fls_id": "fls_changed",
                    "locked": {"checksum": "old", "section_id": "2:1"},
                    "live": {"checksum": "new", "section_id": "2:1"},
                    "content_changed": True,
                    "section_changed": False,
                }
            ],
        },
        "affected_guidelines": (
            {"gui_example": {"title": "Example guideline", "changes": [{"fls_id": "fls_changed"}]}}
            if affected
            else {}
        ),
        "header_changes": [],
        "new_paragraph_assessments": [],
        "relevance": [],
        "section_reorders": [],
        "summary": {
            "added": 1,
            "removed": 0,
            "content_changed": 1,
            "renumbered_only": 0,
            "header_changed": 0,
            "section_reordered": 0,
            "section_changed": 0,
            "affected_guidelines": int(affected),
        },
        "text": {
            "added": {"fls_added": "Added paragraph."},
            "removed": {},
            "content_diffs": [
                {
                    "fls_id": "fls_changed",
                    "diff": ["--- before", "+++ after", "-old", "+new"],
                }
            ],
        },
    }


def report_with_structural_changes() -> dict:
    report = report_with_changes()
    report["header_changes"] = [
        {
            "section_id": "fls_section",
            "document_title_before": "Expressions",
            "document_title_after": "Expression semantics",
            "section_title_before": "Evaluation",
            "section_title_after": "Expression evaluation",
            "section_path_before": "3.1",
            "section_path_after": "3.2",
        }
    ]
    report["section_reorders"] = [
        {
            "section_id": "fls_reordered",
            "title": "Reordered section",
            "path_before": "4.1",
            "path_after": "4.3",
            "document": "expressions.rst",
        }
    ]
    report["summary"]["header_changed"] = 1
    report["summary"]["section_reordered"] = 1
    return report


def spec_lock() -> dict:
    return {
        "documents": [{"link": "one.html", "sections": [{"id": "fls_one"}]}],
        "metadata": {"ignored": True},
    }
