from compare.schemas import ExecutedExecutionStep, ExecutedScript, SetupStep


def es(n, procedure, expected="", actual="", pass_fail="PASS"):
    return ExecutedExecutionStep(
        step_number=n,
        procedure=procedure,
        expected_results=expected,
        actual_results=actual,
        pass_fail=pass_fail,
    )


def pts(n, procedure):
    return SetupStep(step_number=n, procedure=procedure)


def script(execution=None, setup=None, **metadata):
    return ExecutedScript(
        pre_test_setup=setup or [],
        execution_steps=execution or [],
        metadata=metadata,
    )


def diffs_for(result, scope=None, field=None, type=None, include_runtime=True):
    out = []
    for d in result["differences"]:
        if scope and d["scope"] != scope:
            continue
        if field and d["field"] != field:
            continue
        if type and d["type"] != type:
            continue
        if not include_runtime and d["runtime_generated"]:
            continue
        out.append(d)
    return out
