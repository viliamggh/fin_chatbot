# fin_chatbot Evaluation Checklist

## Quick Smoke Test (5 minutes)

Run the automated smoke suite:

```bash
cd /Users/viliamgago/Projects/FinanceAssistant/fin_chatbot/src
uv run python eval/run_evaluation.py
```

**Expected**: 9/9 tests passing (100%)

If any failures, check the JSON report in `eval/reports/` for details.

---

## Manual Spot Check (Optional - 10 minutes)

Use the chatbot-evaluator agent for specific questions:

```
Use the chatbot-evaluator agent to test "How many transactions do I have?"
```

### Key Questions to Verify:
1. **Count**: "How many transactions do I have?" → Should match DB count
2. **Balance**: "What is my net balance?" → Should show CZK, not $
3. **Spending**: "What is my total spending?" → Should be positive value in CZK

---

## Full Test Suite Details

The smoke suite tests these 9 cases:

| ID | Category | Question | Expected |
|----|----------|----------|----------|
| smoke_001 | counting | Transaction count | 46 |
| smoke_002 | aggregation | Net balance | 4604.81 CZK |
| smoke_003 | aggregation | Total income | 261653.00 CZK |
| smoke_004 | aggregation | Total spending | 257048.19 CZK |
| smoke_005 | aggregation | Largest expense | 230000.00 CZK |
| smoke_006 | aggregation | Largest income | 233653.00 CZK |
| smoke_007 | aggregation | Average transaction | ~100.10 CZK |
| smoke_008 | date_filtering | December 2025 count | (verified) |
| smoke_009 | account_filtering | Spending account Dec 2025 | (verified) |

---

## When to Run Evaluations

| Trigger | What to Run | Time |
|---------|-------------|------|
| After chatbot code change | Full smoke suite | 2 min |
| After prompt modifications | Full smoke suite | 2 min |
| Weekly health check | Full smoke suite | 2 min |
| Investigating accuracy issue | chatbot-evaluator agent | 5-10 min |

---

## Reading Evaluation Reports

Reports are saved to `eval/reports/smoke_suite_YYYYMMDD_HHMMSS.json`

Key fields:
- `summary.pass_rate` - Overall accuracy percentage
- `failure_breakdown.WRONG_SQL` - SQL generation issues
- `failure_breakdown.RIGHT_SQL_WRONG_NARRATIVE` - Presentation issues (currency, viz hallucination)

---

## Failure Root Causes

| Root Cause | Meaning | Fix Location |
|------------|---------|--------------|
| WRONG_SQL | Chatbot generated bad SQL | `main.py` sql_agent prompt |
| RIGHT_SQL_WRONG_NARRATIVE | SQL correct, answer wrong | `main.py` response_agent prompt |
| CURRENCY_ERROR | Uses $ instead of CZK | response_agent prompt |
| VIZ_HALLUCINATION | Mentions chart in CLI | response_agent prompt |

---

## Post-Evaluation Actions

If failures occur:
1. Check report JSON for specific discrepancy
2. Identify root cause category
3. Fix prompt in `main.py`
4. Re-run smoke suite to verify fix
5. Commit changes

---

*Last updated*: 2026-01-05
*Current baseline*: 46 transactions, 2025-10-25 to 2026-01-03
