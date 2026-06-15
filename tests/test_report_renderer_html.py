from report.renderer_html import dump_script_tag, insert_dump_into_html, report_html_template


def test_report_html_template_contains_playwright_like_sections():
    html = report_html_template("Demo Report")

    assert 'id="report-search"' in html
    assert 'id="theme-select"' in html
    assert "Dark" in html
    assert "Light" in html
    assert "pymidscene-report-theme" in html
    assert "Search tests" in html
    assert "Test Steps" in html
    assert "Executed in Worker #0" in html
    assert "renderActionRecovery" in html
    assert "Action Recovery" in html
    assert "recovery-stage" in html
    assert "filter-chip" in html


def test_insert_dump_into_html_keeps_action_recovery_payload():
    dump = {
        "meta": {"group_name": "demo", "sdk_version": "1.0.0", "device_type": "windows"},
        "executions": [
            {
                "id": "exec-1",
                "name": "demo execution",
                "log_time": 1,
                "tasks": [
                    {
                        "sub_type": "Tap",
                        "status": "finished",
                        "log": {
                            "action_recovery": [
                                {
                                    "stage": "initial_failure",
                                    "action_type": "Tap",
                                    "selector_ref": {"selector_value": "old-btn"},
                                    "error": "stale selector",
                                },
                                {
                                    "stage": "refresh_retry",
                                    "action_type": "Tap",
                                    "selector_ref": {"selector_value": "new-btn"},
                                },
                            ]
                        },
                    }
                ],
            }
        ],
    }

    html = insert_dump_into_html(report_html_template("Demo Report"), dump)
    script = dump_script_tag(dump)

    assert script.strip() in html
    assert "initial_failure" in html
    assert "new-btn" in html


def run_all_report_renderer_checks():
    test_report_html_template_contains_playwright_like_sections()
    test_insert_dump_into_html_keeps_action_recovery_payload()


if __name__ == "__main__":
    run_all_report_renderer_checks()
    print("all report renderer checks passed")
