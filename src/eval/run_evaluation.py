"""
Automated evaluation runner for fin_chatbot (Smoke Suite v2.0).

Based on Phase 0.4 design decisions:
- Reuses db.py for SQL queries (no duplicate connection logic)
- Parses --verbose audit blocks for deterministic comparison
- Two-stage evaluation: SQL correctness, then narrative quality

Usage:
    cd /Users/viliamgago/Projects/FinanceAssistant/fin_chatbot/src
    uv run python eval/run_evaluation.py

Prerequisites:
    - .env file with SQL credentials (same as chatbot)
    - db.py accessible in parent directory
"""

import json
import subprocess
import re
from datetime import datetime
from pathlib import Path
import sys

# Add parent directory to path to import db module
sys.path.insert(0, str(Path(__file__).parent.parent))

from db import execute_sql_query  # Reuse existing DB infrastructure

# Paths
SCRIPT_DIR = Path(__file__).parent
SRC_DIR = SCRIPT_DIR.parent
TEST_CASES_FILE = SCRIPT_DIR / "test_cases.json"
REPORTS_DIR = SCRIPT_DIR / "reports"


def run_chatbot_query_verbose(question: str) -> str:
    """Run chatbot CLI with --verbose flag and capture full output."""
    try:
        result = subprocess.run(
            ["uv", "run", "python", "main.py", "--verbose"],
            input=question + "\n",
            capture_output=True,
            text=True,
            cwd=str(SRC_DIR),
            timeout=60
        )
        return result.stdout
    except subprocess.TimeoutExpired:
        return "ERROR: Chatbot timed out after 60 seconds"
    except Exception as e:
        return f"ERROR: {str(e)}"


def parse_audit_block(chatbot_output: str) -> dict:
    """
    Parse --verbose audit block from chatbot output.

    Returns dict with:
        - question: str
        - sql_generated: str
        - sql_result: list (parsed JSON)
        - final_answer: str
        - raw_audit: str (full audit block text)
    """
    # Find audit block
    audit_match = re.search(
        r'--- AUDIT START ---(.+?)--- AUDIT END ---',
        chatbot_output,
        re.DOTALL
    )

    if not audit_match:
        return {"error": "No audit block found in output"}

    audit_text = audit_match.group(1)

    # Extract components
    question_match = re.search(r'QUESTION: (.+)', audit_text)
    sql_match = re.search(r'SQL_GENERATED: (.+)', audit_text)
    result_match = re.search(r'SQL_RESULT: (\[.+?\])', audit_text, re.DOTALL)
    answer_match = re.search(r'FINAL_ANSWER: (.+)', audit_text, re.DOTALL)

    parsed = {
        "question": question_match.group(1).strip() if question_match else None,
        "sql_generated": sql_match.group(1).strip() if sql_match else None,
        "sql_result_raw": result_match.group(1).strip() if result_match else None,
        "final_answer": answer_match.group(1).strip() if answer_match else None,
        "raw_audit": audit_text
    }

    # Parse SQL_RESULT JSON
    if parsed["sql_result_raw"]:
        try:
            parsed["sql_result"] = json.loads(parsed["sql_result_raw"])
        except json.JSONDecodeError as e:
            parsed["sql_result"] = None
            parsed["json_parse_error"] = str(e)

    return parsed


def compare_sql_results(ground_truth_json: str, chatbot_sql_result: list, test_case: dict) -> dict:
    """
    Stage 1: Compare SQL results (deterministic).

    Returns:
        - sql_match: bool
        - sql_status: "PASS" | "FAIL"
        - sql_details: str (explanation)
    """
    try:
        ground_truth = json.loads(ground_truth_json)
    except json.JSONDecodeError:
        return {
            "sql_match": False,
            "sql_status": "FAIL",
            "sql_details": "Ground truth query failed or returned invalid JSON"
        }

    # Simple comparison: check if values match expected_value
    expected = test_case.get("expected_value")

    if ground_truth and len(ground_truth) > 0:
        # Extract first value from ground truth result
        gt_value = list(ground_truth[0].values())[0]
    else:
        return {
            "sql_match": False,
            "sql_status": "FAIL",
            "sql_details": "Ground truth returned no rows"
        }

    if chatbot_sql_result and len(chatbot_sql_result) > 0:
        cb_value = list(chatbot_sql_result[0].values())[0]
    else:
        return {
            "sql_match": False,
            "sql_status": "FAIL",
            "sql_details": "Chatbot SQL returned no rows"
        }

    # Tolerance for float comparison
    if isinstance(gt_value, (int, float)) and isinstance(cb_value, (int, float)):
        tolerance = 0.50  # Allow ±0.50 for currency
        match = abs(float(gt_value) - float(cb_value)) <= tolerance
    else:
        match = gt_value == cb_value

    return {
        "sql_match": match,
        "sql_status": "PASS" if match else "FAIL",
        "sql_details": f"Ground truth: {gt_value}, Chatbot SQL result: {cb_value}",
        "ground_truth_value": gt_value,
        "chatbot_value": cb_value
    }


def check_narrative_quality(final_answer: str, test_case: dict, sql_result: list) -> dict:
    """
    Stage 2: Check narrative quality (if SQL was correct).

    Checks:
        - Currency symbol (CZK not $)
        - No chart hallucination in CLI mode
        - Spending sign convention

    Returns:
        - narrative_issues: list of str
        - narrative_status: "PASS" | "FAIL"
    """
    issues = []

    # Check 1: Currency symbol
    if "$" in final_answer and "CZK" not in final_answer:
        issues.append("CURRENCY_ERROR: Uses '$' instead of 'CZK'")

    # Check 2: Chart hallucination
    chart_keywords = ["chart", "visual", "graph", "visualization"]
    if any(kw in final_answer.lower() for kw in chart_keywords):
        issues.append("VIZ_HALLUCINATION: Mentions chart/visualization in CLI mode")

    # Check 3: Spending sign convention (if applicable)
    if test_case.get("category") == "aggregation" and "spending" in test_case.get("question", "").lower():
        # Should report positive value for spending
        if sql_result and len(sql_result) > 0:
            sql_value = list(sql_result[0].values())[0]
            if sql_value < 0:  # SQL returned negative
                # Check if answer mentions negative sign incorrectly
                if "-" in final_answer and "$" not in final_answer:
                    # Negative sign with CZK might be acceptable
                    pass  # Allow "-X CZK" format
                elif "$" in final_answer and "-" in final_answer:
                    issues.append("SIGN_ERROR: Reports negative spending with wrong currency")

    return {
        "narrative_issues": issues,
        "narrative_status": "FAIL" if issues else "PASS",
        "narrative_details": "; ".join(issues) if issues else "Narrative looks correct"
    }


def evaluate_test_case(test_case: dict) -> dict:
    """
    Run a single test case with two-stage evaluation.

    Stage 1: SQL correctness (compare SQL_RESULT from audit vs ground truth)
    Stage 2: Narrative quality (currency, viz, sign convention)
    """
    test_id = test_case["id"]
    question = test_case["question"]
    sql_validation = test_case["sql_validation"]

    print(f"  Running {test_id}: {question[:50]}...")

    # Get ground truth from database (using db.py)
    ground_truth_json = execute_sql_query(sql_validation)

    # Run chatbot with --verbose
    chatbot_output = run_chatbot_query_verbose(question)

    # Parse audit block
    audit = parse_audit_block(chatbot_output)

    if "error" in audit:
        return {
            "id": test_id,
            "question": question,
            "status": "ERROR",
            "error": audit["error"],
            "chatbot_output": chatbot_output[:500],
            "timestamp": datetime.utcnow().isoformat()
        }

    # Stage 1: SQL correctness
    sql_comparison = compare_sql_results(
        ground_truth_json,
        audit.get("sql_result"),
        test_case
    )

    # Stage 2: Narrative quality (only if SQL passed)
    if sql_comparison["sql_status"] == "PASS":
        narrative_check = check_narrative_quality(
            audit.get("final_answer", ""),
            test_case,
            audit.get("sql_result")
        )
    else:
        narrative_check = {
            "narrative_issues": [],
            "narrative_status": "SKIPPED",
            "narrative_details": "SQL comparison failed, skipping narrative check"
        }

    # Determine overall status and root cause
    if sql_comparison["sql_status"] == "FAIL":
        overall_status = "FAIL"
        root_cause = "WRONG_SQL"
    elif narrative_check["narrative_status"] == "FAIL":
        overall_status = "FAIL"
        root_cause = "RIGHT_SQL_WRONG_NARRATIVE"
    else:
        overall_status = "PASS"
        root_cause = None

    return {
        "id": test_id,
        "category": test_case.get("category"),
        "question": question,
        "expected_value": test_case.get("expected_value"),
        "status": overall_status,
        "root_cause": root_cause,
        "sql_comparison": sql_comparison,
        "narrative_check": narrative_check,
        "audit_block": audit,
        "timestamp": datetime.utcnow().isoformat()
    }


def run_smoke_suite():
    """Run smoke suite and generate report."""
    print("=" * 70)
    print("fin_chatbot Smoke Suite Evaluation Runner v2.0")
    print("Based on Phase 0.4 Design Decisions")
    print("=" * 70)

    # Load test cases
    if not TEST_CASES_FILE.exists():
        print(f"Error: Test cases file not found: {TEST_CASES_FILE}")
        return

    with open(TEST_CASES_FILE) as f:
        test_data = json.load(f)

    print(f"\nTest Suite: {test_data.get('test_suite')}")
    print(f"as_of_date: {test_data.get('as_of_date')}")
    print(f"Total test cases: {len(test_data.get('test_cases', []))}")

    # Run tests
    results = []
    test_cases = test_data.get("test_cases", [])

    print("\nRunning tests...")
    print("-" * 70)

    for test_case in test_cases:
        result = evaluate_test_case(test_case)
        results.append(result)

        # Print quick result
        status_emoji = "✅" if result["status"] == "PASS" else "❌"
        print(f"  {status_emoji} {result['id']}: {result['status']}", end="")
        if result.get("root_cause"):
            print(f" ({result['root_cause']})")
        else:
            print()

    # Generate report
    REPORTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    report_path = REPORTS_DIR / f"smoke_suite_{timestamp}.json"

    # Calculate summary stats
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    errors = sum(1 for r in results if r["status"] == "ERROR")

    wrong_sql = sum(1 for r in results if r.get("root_cause") == "WRONG_SQL")
    wrong_narrative = sum(1 for r in results if r.get("root_cause") == "RIGHT_SQL_WRONG_NARRATIVE")

    report = {
        "run_timestamp": datetime.utcnow().isoformat(),
        "test_suite": test_data.get("test_suite"),
        "as_of_date": test_data.get("as_of_date"),
        "summary": {
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "pass_rate": f"{(passed / len(results) * 100):.1f}%" if results else "0%"
        },
        "failure_breakdown": {
            "WRONG_SQL": wrong_sql,
            "RIGHT_SQL_WRONG_NARRATIVE": wrong_narrative
        },
        "results": results
    }

    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    # Print summary
    print("\n" + "=" * 70)
    print(f"EVALUATION COMPLETE")
    print("=" * 70)
    print(f"Total tests: {len(results)}")
    print(f"✅ Passed: {passed} ({report['summary']['pass_rate']})")
    print(f"❌ Failed: {failed}")
    print(f"   - WRONG_SQL: {wrong_sql}")
    print(f"   - RIGHT_SQL_WRONG_NARRATIVE: {wrong_narrative}")
    print(f"⚠️  Errors: {errors}")
    print(f"\nReport saved: {report_path}")
    print("=" * 70)

    return results


if __name__ == "__main__":
    run_smoke_suite()
