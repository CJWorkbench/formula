from formula import build_globals_for_eval


def _exec_code(code):
    built_globals = build_globals_for_eval()
    inner_locals = {}
    exec(code, built_globals, inner_locals)
    return inner_locals


def test_builtin_functions():
    env = _exec_code("ret = sorted(list([1, 2, sum([3, 4])]))")
    assert env["ret"] == [1, 2, 7]
