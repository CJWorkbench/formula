from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd
from cjwmodule.spec.testing import param_factory
from cjwmodule.testing.i18n import i18n_message
from pandas.testing import assert_frame_equal

import formula

P = param_factory(Path(__name__).parent.parent / "formula.yaml")


def _test(
    table: pd.DataFrame,
    params: Dict[str, Any] = {},
    expected_table: pd.DataFrame = pd.DataFrame(),
    expected_error: str = "",
):
    result = formula.render(table, P(**params))
    if expected_error:
        assert result == expected_error
    else:
        assert isinstance(result, pd.DataFrame)
        assert_frame_equal(result, expected_table)


def test_python_formula_int_output():
    _test(
        pd.DataFrame({"A": [10, 20]}),
        P(syntax="python", formula_python="A*2"),
        pd.DataFrame({"A": [10, 20], "result": [20, 40]}),
    )


def test_python_formula_str_output():
    _test(
        pd.DataFrame({"A": [10, 20]}),
        P(syntax="python", formula_python='str(A) + "x"'),
        pd.DataFrame({"A": [10, 20], "result": ["10x", "20x"]}),
    )


def test_python_formula_empty_output_pval_makes_result():
    # empty out_column defaults to 'result'
    _test(
        pd.DataFrame({"A": [1]}),
        P(syntax="python", formula_python="A*2", out_column=""),
        pd.DataFrame({"A": [1], "result": [2]}),
    )


def test_python_formula_missing_colname_makes_error():
    # formula with missing column name should error
    _test(
        pd.DataFrame({"A": [1]}),
        P(syntax="python", formula_python="B*2"),
        expected_error="name 'B' is not defined",
    )


def test_python_formula_cast_nonsane_output():
    _test(
        pd.DataFrame({"A": [1, 2]}),
        P(syntax="python", formula_python="[A]"),
        pd.DataFrame({"A": [1, 2], "result": ["[1]", "[2]"]}),
    )


def test_python_spaces_to_underscores():
    # column names with spaces should be referenced with underscores in the
    # formula
    _test(
        pd.DataFrame({"A b": [1, 2]}),
        P(syntax="python", formula_python="A_b*2"),
        pd.DataFrame({"A b": [1, 2], "result": [2, 4]}),
    )


def test_excel_formula_no_output_col_name():
    # if no output column name specified, store to a column named 'result'
    _test(
        pd.DataFrame({"A": [1, 2]}),
        P(formula_excel="=A1*2", all_rows=True, out_column=""),
        pd.DataFrame({"A": [1, 2], "result": [2.0, 4.0]}),
    )


def test_excel_date():
    _test(
        pd.DataFrame({"A": [1, 2, 3]}),
        {
            "formula_excel": "=DATE(2019, 6, A1)",
            "all_rows": True,
            "out_column": "X",
        },
        pd.DataFrame(
            {
                "A": [1, 2, 3],
                # Excel dates are integers. TODO let user specify an output
                # format, so they get useful behavior.
                "X": [43617, 43618, 43619],
            }
        ),
    )


def test_excel_bool():
    _test(
        pd.DataFrame({"A": [1, 2, None]}),
        {
            "formula_excel": "=A1=1",
            "all_rows": True,
            "out_column": "X",
        },
        # "None=1" evaluates to False, in Excel-land
        pd.DataFrame({"A": [1, 2, None], "X": ["True", "False", "False"]}),
    )


def test_excel_bool_mixed_type():
    _test(
        pd.DataFrame({"A": [1, 2, None]}),
        {
            "formula_excel": "=IF(A1=1, TRUE, 3)",
            "all_rows": True,
            "out_column": "X",
        },
        # "None=1" evaluates to False, in Excel-land
        pd.DataFrame({"A": [1, 2, None], "X": ["True", "3", "3"]}),
    )


def test_excel_timestamp_add():
    # This is really tricky, because of a bugs in Lotus-1-2-3 in the 1980s.
    # https://docs.microsoft.com/en-gb/office/troubleshoot/excel/wrongly-assumes-1900-is-leap-year
    #
    # Let's follow the behavior of LibreOffice and Google Sheets: say the
    # date system starts at 1899-12-30 instead of 1899-12-31. Test:
    #
    # 1. in column A, enter some dates. (1900-01-01 becomes 2.0!)
    # 2. in column B, enter "=A1" and format as Number
    # 3. in column C, enter "=A1+3"
    # 4. in column D, enter "=A1+3" (again) and format as Datetime
    dates = pd.Series(
        ["1900-01-01", "1900-02-27", "2020-03-01"], dtype="datetime64[ns]"
    )
    _test(
        pd.DataFrame({"A": dates}),
        {
            "formula_excel": "=A1 + 3",
            "all_rows": True,
            "out_column": "X",
        },
        pd.DataFrame(
            {
                "A": dates,
                # Excel dates are integers. TODO let user specify an output
                # format, so they get useful behavior.
                "X": [5.0, 62.0, 43894.0],
            }
        ),
    )


def test_excel_date_add():
    # Look to `test_excel_timestamp_add` for canonical test
    dates = pd.Series(["1900-01-01", "1900-02-27", "2020-03-01"], dtype="period[D]")
    _test(
        pd.DataFrame({"A": dates}),
        {
            "formula_excel": "=A1 + 3",
            "all_rows": True,
            "out_column": "X",
        },
        pd.DataFrame(
            {
                "A": dates,
                # Excel dates are integers. TODO let user specify an output
                # format, so they get useful behavior.
                "X": [5.0, 62.0, 43894.0],
            }
        ),
    )


def test_excel_all_rows_function_not_implemented():
    _test(
        pd.DataFrame({"A": [1, 2, 3]}),
        {
            "formula_excel": "=DATEX(2019, 6, A1)",
            "all_rows": True,
            "out_column": "X",
        },
        expected_error=i18n_message("excel.functionNotImplemented", {"name": "DATEX"}),
    )


# --- Formulas which write to all rows ---
def test_excel_all_rows_single_column():
    _test(
        pd.DataFrame({"A": [1, 2]}),
        P(formula_excel="=A1*2", all_rows=True),
        pd.DataFrame({"A": [1, 2], "result": [2.0, 4.0]}),
    )


def test_excel_all_rows_column_range():
    _test(
        pd.DataFrame({"A": [1, 2], "B": [2, 3], "C": [3, 4]}),
        P(formula_excel="=SUM(A1:C1)", all_rows=True),
        pd.DataFrame({"A": [1, 2], "B": [2, 3], "C": [3, 4], "result": [6, 9]}),
    )


def test_excel_text_formula():
    _test(
        pd.DataFrame({"A": ["foo", "bar"]}),
        P(formula_excel="=LEFT(A1, 2)", all_rows=True),
        pd.DataFrame({"A": ["foo", "bar"], "result": ["fo", "ba"]}),
    )


# --- Formulas which write only to a single row ---
def test_excel_divide_two_rows():
    _test(
        pd.DataFrame({"A": [1, 2]}),
        P(formula_excel="=A1/A2", all_rows=False),
        pd.DataFrame({"A": [1, 2], "result": [0.5, np.nan]}),
    )


def test_excel_add_two_columns():
    _test(
        pd.DataFrame({"A": [1, 2], "B": [2, 3]}),
        P(formula_excel="=A1+B1", all_rows=False),
        pd.DataFrame({"A": [1, 2], "B": [2, 3], "result": [3, np.nan]}),
    )


def test_excel_function_not_implemented():
    _test(
        pd.DataFrame({"A": [1, 2, 3]}),
        {
            "formula_excel": "=DATEX(2019, 6, A1)",
            "all_rows": False,
            "out_column": "X",
        },
        expected_error=i18n_message("excel.functionNotImplemented", {"name": "DATEX"}),
    )


def test_excel_sum_column():
    _test(
        pd.DataFrame({"A": [1, 2, 3]}),
        P(formula_excel="=SUM(A2:A3)", all_rows=False),
        pd.DataFrame({"A": [1, 2, 3], "result": [5, np.nan, np.nan]}),
    )


def test_excel_error_missing_row_number():
    _test(
        pd.DataFrame({"A": [1, 2]}),
        P(formula_excel="=A*2", all_rows=True),
        expected_error=i18n_message("excel.badCellReference", {"token": "A"}),
    )


def test_excel_error_missing_row_number_in_range():
    _test(
        pd.DataFrame({"A": [1, 2], "B": [2, 3]}),
        P(formula_excel="=SUM(A:B)", all_rows=True),
        expected_error=i18n_message("excel.formulaFirstRowReference"),
    )


def test_excel_error_reference_row_other_than_1_with_all_rows():
    _test(
        pd.DataFrame({"A": [1, 2]}),
        P(formula_excel="=A2*2", all_rows=True),
        expected_error=i18n_message("excel.formulaFirstRowReference"),
    )


def test_excel_error_syntax():
    _test(
        pd.DataFrame({"A": [1, 2]}),
        P(formula_excel="=SUM B>", all_rows=False),
        expected_error=i18n_message(
            # The "%s" is built in to the formulas module. TODO file bugrep
            "excel.invalidFormula",
            {"error": "Not a valid formula:\n%s"},
        ),
    )


def test_excel_error_out_of_range_columns():
    _test(
        pd.DataFrame({"A": [1, 2]}),
        P(formula_excel="=SUM(A1:B1)", all_rows=True),
        expected_error=i18n_message("excel.all_rows.badColumnRef", {"ref": "A1:B1"}),
    )


def test_excel_error_out_of_range_rows():
    _test(
        pd.DataFrame({"A": [1, 2]}),
        P(formula_excel="=SUM(A1:A3)", all_rows=False),
        # Just ignore missing rows
        pd.DataFrame({"A": [1, 2], "result": [3, np.nan]}),
    )


def test_excel_error_row_0():
    _test(
        pd.DataFrame({"A": [1, 2]}),
        P(formula_excel="=A0*2", all_rows=False),
        expected_error=i18n_message("excel.one_row.invalidCellRange", {"token": "A0"}),
    )


def test_excel_sanitize_output():
    _test(
        pd.DataFrame({"A": [1, 2]}),
        P(formula_excel='=IF(A1=1, 1, "x")', all_rows=True),
        pd.DataFrame({"A": [1, 2], "result": ["1", "x"]}),
    )


def test_excel_value_error():
    # https://www.pivotaltracker.com/story/show/168909000
    _test(
        pd.DataFrame({"A": ["1", "x", "3"]}),
        P(formula_excel="=SUM(A1:A3)", all_rows=False, out_column="X"),
        pd.DataFrame({"A": ["1", "x", "3"], "X": ["#VALUE!", None, None]}),
    )
