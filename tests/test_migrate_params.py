from pathlib import Path

from cjwmodule.spec.testing import param_factory

from formula import migrate_params

P = param_factory(Path(__name__).parent.parent / "formula.yaml")


def test_v0_excel():
    assert migrate_params(
        {
            "syntax": 0,
            "out_column": "R",
            "formula_excel": "=A1",
            "formula_python": "A",
            "all_rows": True,
        }
    ) == P(
        syntax="excel",
        out_column="R",
        formula_excel="=A1",
        formula_python="A",
        all_rows=True,
    )


def test_v0_python():
    assert migrate_params(
        {
            "syntax": 1,
            "out_column": "R",
            "formula_excel": "=A1",
            "formula_python": "A",
            "all_rows": True,
        }
    ) == P(
        syntax="python",
        out_column="R",
        formula_excel="=A1",
        formula_python="A",
        all_rows=True,
    )


def test_v1():
    assert migrate_params(
        {
            "syntax": "python",
            "out_column": "R",
            "formula_excel": "=A1",
            "formula_python": "A",
            "all_rows": True,
        }
    ) == P(
        syntax="python",
        out_column="R",
        formula_excel="=A1",
        formula_python="A",
        all_rows=True,
    )
