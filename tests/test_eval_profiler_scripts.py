from collections import defaultdict
from pathlib import Path

from eval import render_html_report
from profiler import summarize_api_failure


def test_profiler_api_failure_summary_omits_response_body():
    message = summarize_api_failure(500, "provider leaked hf-token and stack trace")

    assert "500 server_error" in message
    assert "hf-token" not in message
    assert "stack trace" not in message
    assert "response body omitted" in message


def test_eval_html_report_escapes_pathology_labels():
    labels = ["fomo_entries", "<script>alert(1)</script>"]
    report = {
        label: {"precision": 1, "recall": 1, "f1": 1}
        for label in labels
    }
    report["macro_avg"] = {"precision": 1, "recall": 1, "f1": 1}
    confusion = defaultdict(lambda: defaultdict(int))

    html = render_html_report(report, confusion, labels)

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_static_report_page_is_self_contained():
    html = Path("report/index.html").read_text()

    assert 'href="../eval_report.html"' not in html
    assert 'href="../eval_report.json"' not in html
    assert 'src="../eval_report.html"' not in html
    assert "python eval.py" in html
