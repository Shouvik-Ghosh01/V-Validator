"""Output-vs-Output (peer) comparison: compare_execution_reports()."""
import re

from compare.comparator_output import compare_execution_reports
from tests.helpers import diffs_for, es, pts, script

ACCOUNTS_A = (
    "Ensure the following accounts exist:\n"
    "- QMS Owner (Security Profile: Full User; System Assignments: QMS User): qms.owner28@test.com\n"
    "- QMS QA (Security Profile: Full User; System Assignments: QA): qms.qa28@test.com"
)


def steps_1_to_4():
    return [
        es(1, "Log in to the Vault", "Home page is displayed", "Home page is displayed"),
        es(2, "Open the Documents tab", "Documents list is displayed", "Documents list is displayed"),
        es(3, "Create a new Product record", "Product record is created", "Product record is created"),
        es(4, "Delete the draft document", "Document is deleted", "Document is deleted"),
    ]


# ── identical ─────────────────────────────────────────────────────────────────
def test_identical_reports():
    a = script(steps_1_to_4(), [pts(1, "Enable feature X")], script_id="TS-1", title="T")
    b = script(steps_1_to_4(), [pts(1, "Enable feature X")], script_id="TS-1", title="T")

    r = compare_execution_reports(a, b)

    assert r["comparison_mode"] == "output_vs_output"
    assert r["has_differences"] is False
    assert r["differences"] == []
    assert r["summary"]["total_differences"] == 0
    assert r["summary"]["identical_execution_steps"] == 4
    assert r["summary"]["identical_setup_steps"] == 1


def test_include_identical_lists_identical_steps_without_counting_them():
    a = script(steps_1_to_4())
    r = compare_execution_reports(a, script(steps_1_to_4()), include_identical=True)

    assert {d["type"] for d in r["differences"]} == {"identical"}
    assert r["summary"]["total_differences"] == 0
    assert r["has_differences"] is False


# ── changed values ────────────────────────────────────────────────────────────
def test_changed_procedure():
    a = script(steps_1_to_4())
    b_steps = steps_1_to_4()
    b_steps[1] = es(2, "Open the Documents tab and sort by Name",
                    "Documents list is displayed", "Documents list is displayed")
    r = compare_execution_reports(a, script(b_steps))

    [d] = diffs_for(r, scope="execution")
    assert (d["type"], d["field"], d["step_number"]) == ("changed", "procedure", 2)
    assert d["output_a"] == "Open the Documents tab"
    assert d["output_b"] == "Open the Documents tab and sort by Name"
    assert d["runtime_generated"] is False
    assert r["has_differences"] is True


def test_changed_actual_result_is_meaningful():
    a_steps, b_steps = steps_1_to_4(), steps_1_to_4()
    b_steps[2] = es(3, "Create a new Product record", "Product record is created",
                    "An error banner is displayed")
    r = compare_execution_reports(script(a_steps), script(b_steps))

    [d] = diffs_for(r, scope="execution")
    assert d["field"] == "actual_results" and d["type"] == "changed"
    assert d["runtime_generated"] is False
    assert r["summary"]["total_differences"] == 1


def test_changed_status_is_reported_neutrally():
    a_steps, b_steps = steps_1_to_4(), steps_1_to_4()
    b_steps[3] = es(4, "Delete the draft document", "Document is deleted",
                    "Document is deleted", pass_fail="FAIL")
    r = compare_execution_reports(script(a_steps), script(b_steps))

    [d] = diffs_for(r, scope="execution", field="pass_fail")
    assert d["type"] == "changed"
    assert (d["output_a"], d["output_b"]) == ("PASS", "FAIL")
    assert d["message"] == "Status changed: PASS → FAIL"


def test_changed_metadata_counts_but_run_specific_metadata_does_not():
    a = script(build_number="B-100", run_number="28", start_time="01-JAN-2026 10:00:00 GMT")
    b = script(build_number="B-101", run_number="29", start_time="02-JAN-2026 11:30:00 GMT")
    r = compare_execution_reports(a, b)

    build = diffs_for(r, scope="metadata", field="build_number")[0]
    run = diffs_for(r, scope="metadata", field="run_number")[0]

    assert build["type"] == "changed" and build["runtime_generated"] is False
    assert (run["output_a"], run["output_b"]) == ("28", "29")
    assert run["type"] == "changed" and run["runtime_generated"] is True
    # run number + start time are listed, but only build_number counts
    assert r["summary"]["total_differences"] == 1
    assert r["summary"]["runtime_generated_differences"] == 2


def test_metadata_present_on_one_side_only():
    r = compare_execution_reports(script(vault_name="V1"), script(product_version="24R3"))

    assert diffs_for(r, field="vault_name")[0]["type"] == "missing"
    assert diffs_for(r, field="product_version")[0]["type"] == "additional"


# ── step matching ─────────────────────────────────────────────────────────────
def test_missing_and_additional_steps_are_matched_by_number_not_position():
    a = script(steps_1_to_4())
    b = script([
        steps_1_to_4()[0],
        steps_1_to_4()[1],
        steps_1_to_4()[3],                      # step 4 survives...
        es(5, "Export the audit trail to CSV", "File downloads", "File downloads"),
    ])
    r = compare_execution_reports(a, b)

    by_type = {d["type"]: d for d in r["differences"]}
    assert by_type["missing"]["step_number"] == 3
    assert by_type["additional"]["step_number"] == 5
    # ...and step 4 is compared with step 4, not with whatever sits at index 3
    assert len(r["differences"]) == 2
    assert r["summary"]["identical_execution_steps"] == 3
    assert r["summary"]["missing"] == 1 and r["summary"]["additional"] == 1


def test_renumbered_step_is_recovered_by_procedure_text():
    a = script([
        es(1, "Log in to the Vault"),
        es(2, "Open the Documents tab"),
        es(3, "Create a new Product record with the standard template"),
    ])
    b = script([
        es(1, "Log in to the Vault"),
        es(2, "Open the Documents tab"),
        es(3, "Verify that the banner reads Welcome"),          # new step
        es(4, "Create a new Product record with the standard template"),  # old step 3
    ])
    r = compare_execution_reports(a, b)

    renumbered = diffs_for(r, field="step_number")[0]
    assert (renumbered["output_a"], renumbered["output_b"]) == ("3", "4")
    assert renumbered["matched_by"] == "procedure_similarity"

    added = diffs_for(r, type="additional")[0]
    assert added["step_number"] == 3
    assert "Welcome" in added["output_b"]
    # nothing else differs: the renumbered pair's text fields are identical
    assert len(r["differences"]) == 2


def test_unrelated_procedures_at_same_number_are_ambiguous_and_not_compared():
    a = script([es(1, "Log in to the Vault"), es(2, "Click Save", "Saved", "Saved")])
    b = script([es(1, "Log in to the Vault"),
                es(2, "Navigate to Reports and export the quarterly summary",
                   "A summary is exported", "A summary is exported")])
    r = compare_execution_reports(a, b)

    [d] = r["differences"]
    assert d["type"] == "ambiguous" and d["step_number"] == 2
    assert r["summary"]["ambiguous"] == 1
    assert r["has_differences"] is True


# ── runtime-generated values ──────────────────────────────────────────────────
def test_runtime_generated_record_name_is_flagged_not_counted():
    a = script([es(1, "Create a Product", "Record Name is displayed", "Record Name: Product_12345")])
    b = script([es(1, "Create a Product", "Record Name is displayed", "Record Name: Product_12387")])
    r = compare_execution_reports(a, b)

    [d] = r["differences"]
    assert d["field"] == "actual_results" and d["type"] == "changed"
    assert d["runtime_generated"] is True
    assert d["dynamic_values"]["output_a"] == {"record_name": ["Product_12345"]}
    assert d["dynamic_values"]["output_b"] == {"record_name": ["Product_12387"]}
    assert r["has_differences"] is False
    assert r["summary"]["runtime_generated_differences"] == 1


def test_generated_value_of_a_different_kind_is_still_meaningful():
    a = script([es(1, "Create a record", "Record Name is displayed", "Record Name: Product_12345")])
    b = script([es(1, "Create a record", "Record Name is displayed", "Record Name: Vendor_12345")])
    r = compare_execution_reports(a, b)

    [d] = r["differences"]
    assert d["runtime_generated"] is False
    assert r["has_differences"] is True


def test_dynamic_value_plus_other_text_change_is_meaningful():
    a = script([es(1, "Create a record", "", "Record Name: Product_12345 saved")])
    b = script([es(1, "Create a record", "", "Record Name: Product_12387 failed to save")])
    r = compare_execution_reports(a, b)

    assert r["differences"][0]["runtime_generated"] is False


# ── accounts ──────────────────────────────────────────────────────────────────
def test_same_account_different_runtime_email_is_not_a_definition_mismatch():
    b_text = ACCOUNTS_A.replace("qms.owner28", "qms.owner29").replace("qms.qa28", "qms.qa29")
    r = compare_execution_reports(script(setup=[pts(1, ACCOUNTS_A)]), script(setup=[pts(1, b_text)]))

    assert diffs_for(r, field="account_definition") == []
    emails = diffs_for(r, field="account_email")
    assert len(emails) == 2
    assert all(d["runtime_generated"] for d in emails)
    assert r["has_differences"] is False


def test_changed_account_definition_is_meaningful():
    b_text = ACCOUNTS_A.replace("QMS Owner (Security Profile: Full User",
                                "QMS Owner (Security Profile: RIM Admin")
    r = compare_execution_reports(script(setup=[pts(1, ACCOUNTS_A)]), script(setup=[pts(1, b_text)]))

    [d] = diffs_for(r, field="account_definition")
    assert d["type"] == "changed" and d["runtime_generated"] is False
    assert "full user" in d["output_a"] and "rim admin" in d["output_b"]
    assert r["has_differences"] is True


def test_account_missing_and_additional():
    b_text = (
        "Ensure the following accounts exist:\n"
        "- QMS Owner (Security Profile: Full User; System Assignments: QMS User): qms.owner28@test.com\n"
        "- QMS Auditor (Security Profile: Read Only): qms.aud28@test.com"
    )
    r = compare_execution_reports(script(setup=[pts(1, ACCOUNTS_A)]), script(setup=[pts(1, b_text)]))

    assert "qms qa" in diffs_for(r, field="account", type="missing")[0]["output_a"]
    assert "qms auditor" in diffs_for(r, field="account", type="additional")[0]["output_b"]


def test_email_change_beyond_digits_is_meaningful():
    b_text = ACCOUNTS_A.replace("qms.owner28@test.com", "someone.else@test.com")
    r = compare_execution_reports(script(setup=[pts(1, ACCOUNTS_A)]), script(setup=[pts(1, b_text)]))

    [d] = diffs_for(r, field="account_email")
    assert d["runtime_generated"] is False


# ── setup steps ───────────────────────────────────────────────────────────────
def test_changed_setup_procedure():
    r = compare_execution_reports(
        script(setup=[pts(2, "Enable feature X in the Vault")]),
        script(setup=[pts(2, "Enable feature Y in the Vault")]),
    )
    [d] = diffs_for(r, scope="setup")
    assert (d["type"], d["field"], d["step_number"]) == ("changed", "procedure", 2)
    assert r["summary"]["setup_steps_with_differences"] == 1


# ── vocabulary ────────────────────────────────────────────────────────────────
FORBIDDEN = re.compile(r"\b(incorrect|correct|wrong|template|client|pass(ed)? validation)\b", re.I)


def test_no_expected_actual_verdict_language_leaks_into_messages():
    a_steps, b_steps = steps_1_to_4(), steps_1_to_4()
    b_steps[0] = es(1, "Log in to the Vault as an admin", "Home page is displayed", "Error", "FAIL")
    r = compare_execution_reports(
        script(a_steps, [pts(1, ACCOUNTS_A)], build_number="1"),
        script(b_steps, [pts(1, ACCOUNTS_A.replace("Full User", "Read Only"))], build_number="2"),
    )

    assert r["differences"]
    allowed = {"changed", "missing", "additional", "identical", "ambiguous"}
    for d in r["differences"]:
        assert d["type"] in allowed
        assert not FORBIDDEN.search(d["message"]), d["message"]
