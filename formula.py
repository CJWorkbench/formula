import builtins
import itertools
from formulas import Parser
from typing import Any, Dict
import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype, is_datetime64_dtype
from schedula import DispatcherError
from cjwmodule import i18n


def autocast_series_dtype(series: pd.Series) -> pd.Series:
    """
    Cast any sane Series to str/category[str]/number/datetime.

    This is appropriate when parsing CSV data or Excel data. It _seems_
    appropriate when a search-and-replace produces numeric columns like
    '$1.32' => '1.32' ... but perhaps that's only appropriate in very-specific
    cases.

    The input must be "sane": if the dtype is object or category, se assume
    _every value_ is str (or null).

    If the series is all-null, do nothing.

    Avoid spurious calls to this function: it's expensive.

    TODO handle dates and maybe booleans.
    """
    if series.dtype == object:
        nulls = series.isnull()
        if (nulls | (series == "")).all():
            return series
        try:
            # If it all looks like numbers (like in a CSV), cast to number.
            return pd.to_numeric(series)
        except (ValueError, TypeError):
            # Otherwise, we want all-string. Is that what we already have?
            #
            # TODO assert that we already have all-string, and nix this
            # spurious conversion.
            array = series[~nulls].array
            if any(type(x) != str for x in array):
                series = series.astype(str)
                series[nulls] = None
            return series
    elif hasattr(series, "cat"):
        # Categorical series. Try to infer type of series.
        #
        # Assume categories are all str: after all, we're assuming the input is
        # "sane" and "sane" means only str categories are valid.
        if (series.isnull() | (series == "")).all():
            return series
        try:
            return pd.to_numeric(series)
        except (ValueError, TypeError):
            # We don't cast categories to str here -- because we have no
            # callers that would create categories that aren't all-str. If we
            # ever do, this is where we should do the casting.
            return series
    else:
        assert is_numeric_dtype(series) or is_datetime64_dtype(series)
        return series


class UserVisibleError(Exception):
    """Has an `i18n.I18nMessage` as its first argument"""

    @property
    def i18n_message(self):
        return self.args[0]


def build_builtins_for_eval() -> Dict[str, Any]:
    """
    Build a __builtins__ for use in custom code.

    Call ``exec(code, {'__builtins__': retval}, {})`` to use it.
    """
    # Start with _this_ module's __builtins__
    eval_builtins = dict(builtins.__dict__)

    # Disable "dangerous" builtins.
    #
    # This doesn't increase security: it just helps module authors.
    def disable_func(name):
        def _disabled(*args, **kwargs):
            raise UserVisibleError(
                i18n.trans(
                    "python.disabledFunction",
                    "{name} is disabled",
                    {"name": "builtins.%s" % name},
                )
            )

        return _disabled

    to_disable = ["__import__", "breakpoint", "compile", "eval", "exec", "open"]
    for name in to_disable:
        eval_builtins[name] = disable_func(name)

    return eval_builtins


def build_globals_for_eval() -> Dict[str, Any]:
    """Builds a __globals__ for use in custom code.
    """
    eval_builtins = build_builtins_for_eval()

    # Hard-code modules we provide the user
    import math
    import pandas as pd
    import numpy as np

    return {"__builtins__": eval_builtins, "math": math, "np": np, "pd": pd}


def sanitize_series(series: pd.Series) -> pd.Series:
    """
    Enforce type rules on input pandas `Series.values`.

    The return value is anything that can be passed to the `pandas.Series()`
    constructor.

    Specific fixes:

    * Make sure categories have no excess values.
    * Convert numeric categories to 
    * Convert unsupported dtypes to string.
    * Reindex so row numbers are contiguous.
    """
    series.reset_index(drop=True, inplace=True)
    if hasattr(series, "cat"):
        series.cat.remove_unused_categories(inplace=True)

        categories = series.cat.categories
        if pd.api.types.is_numeric_dtype(categories.values):
            # Un-categorize: make array of int/float
            return pd.to_numeric(series)
        elif (
            categories.dtype != object
            or pd.api.types.infer_dtype(categories.values, skipna=True) != "string"
        ):
            # Map from non-Strings to Strings
            #
            # 1. map the _codes_ to unique _codes_
            mapping = pd.Categorical(categories.astype(str))
            values = pd.Categorical(series.cat.codes[mapping.codes])
            # 2. give them names
            values.rename_categories(mapping.categories, inplace=True)
            series = pd.Series(values)

        return series
    elif is_numeric_dtype(series.dtype):
        return series
    elif is_datetime64_dtype(series.dtype):
        return series
    else:
        # Force it to be a str column: every object is either str or np.nan
        ret = series.astype(str)
        ret[pd.isna(series)] = np.nan
        return ret


def python_formula(table, formula):
    # spaces to underscores in column names
    colnames = [x.replace(" ", "_") for x in table.columns]

    code = compile(formula, "<string>", "eval")
    custom_code_globals = build_globals_for_eval()

    # Much experimentation went into the form of this loop for good
    # performance.
    # Note we don't use iterrows or any pandas indexing, and construct the
    # values dict ourselves
    newcol = pd.Series(list(itertools.repeat(None, len(table))))
    for i, row in enumerate(table.values):
        newcol[i] = eval(code, custom_code_globals, dict(zip(colnames, row)))

    newcol = autocast_series_dtype(sanitize_series(newcol))

    return newcol


def flatten_single_element_lists(x):
    """Return `x[0]` if `x` is a list, otherwise `x`."""
    if isinstance(x, list) and len(x) == 1:
        return x[0]
    else:
        return x


def eval_excel(code, args):
    """
    Return result of running Excel code with args.

    Raise UserVisibleError if a function is unimplemented.
    """
    try:
        ret = code(*args)
    except DispatcherError as err:
        if isinstance(err.args[2], NotImplementedError):
            raise UserVisibleError(
                i18n.trans(
                    "excel.functionNotImplemented",
                    "Function {name} not implemented",
                    {"name": err.args[1]},
                )
            )
        else:
            raise
    if isinstance(ret, np.ndarray):
        return ret.item()
    else:
        return ret


def eval_excel_one_row(code, table):

    # Generate a list of input table values for each range in the expression
    formula_args = []
    for token, obj in code.inputs.items():
        if obj is None:
            raise UserVisibleError(
                i18n.trans(
                    "excel.one_row.invalidCellRange",
                    "Invalid cell range: {token}",
                    {"token": token},
                )
            )
        ranges = obj.ranges
        if len(ranges) != 1:
            # ...not sure what input would get us here
            raise UserVisibleError(
                i18n.trans(
                    "excel.one_row.cellRangeNotRectangular",
                    "Excel range must be a rectangular block of values",
                )
            )
        range = ranges[0]

        # Unpack start/end row/col
        r1 = int(range["r1"]) - 1
        r2 = int(range["r2"])
        c1 = int(range["n1"]) - 1
        c2 = int(range["n2"])

        nrows, ncols = table.shape
        # allow r2 > nrows: users use it to say SUM(A1:A99999)
        if r1 < 0 or c1 < 0 or c2 > ncols or r1 >= r2 or c1 >= c2:
            raise UserVisibleError(
                i18n.trans(
                    "excel.one_row.badRef",
                    'Excel range "{ref}" is out of bounds',
                    {"ref": range["ref"]},
                )
            )

        # retval of code() is OperatorArray:
        # https://github.com/vinci1it2000/formulas/issues/12
        table_part = list(table.iloc[r1:r2, c1:c2].values.flat)
        formula_args.append(flatten_single_element_lists(table_part))

    # evaluate the formula just once
    # raises ValueError if function isn't implemented
    return eval_excel(code, formula_args)


def eval_excel_all_rows(code, table):
    col_idx = []
    for token, obj in code.inputs.items():
        # If the formula is valid but no object comes back it means the
        # reference is no good
        # Missing row number?
        # with only A-Z. But just in case:
        if obj is None:
            raise UserVisibleError(
                i18n.trans(
                    "excel.badCellReference",
                    "Bad cell reference {token}",
                    {"token": token},
                )
            )

        ranges = obj.ranges
        for rng in ranges:
            # r1 and r2 refer to which rows are referenced by the range.
            if rng["r1"] != "1" or rng["r2"] != "1":
                raise UserVisibleError(
                    i18n.trans(
                        "excel.formulaFirstRowReference",
                        "Excel formulas can only reference the first row when applied to all rows",
                    )
                )

            c1 = rng["n1"] - 1
            c2 = rng["n2"]

            if c1 < 0 or c2 > len(table.columns) or c1 >= c2:
                raise UserVisibleError(
                    i18n.trans(
                        "excel.all_rows.badColumnRef",
                        'Excel range "{ref}" is out of bounds',
                        {"ref": rng["ref"]},
                    )
                )

            col_idx.append(list(range(c1, c2)))

    newcol = []
    for row in table.values:
        args_to_excel = [
            flatten_single_element_lists([row[idx] for idx in col]) for col in col_idx
        ]
        # raises ValueError if function isn't implemented
        newcol.append(eval_excel(code, args_to_excel))

    return pd.Series(newcol)


def excel_formula(table, formula, all_rows):
    try:
        # 0 is a list of tokens, 1 is the function builder object
        code = Parser().ast(formula)[1].compile()
    except Exception as e:
        raise UserVisibleError(
            i18n.trans(
                "excel.invalidFormula",
                "Couldn't parse formula: {error}",
                {"error": str(e)},
            )
        )

    if all_rows:
        newcol = eval_excel_all_rows(code, table)
        newcol = autocast_series_dtype(sanitize_series(newcol))
    else:
        # the whole column is blank except first row
        value = eval_excel_one_row(code, table)
        newcol = pd.Series([value] + [None] * (len(table) - 1))

    return newcol


def _get_output_column(table, out_column: str) -> str:
    # if no output column supplied, use result0, result1, etc.
    if not out_column:
        out_column = "result"

    # make sure the colname is unique
    if out_column in table.columns:
        n = 0
        while f"{out_column}{n}" in table.columns:
            n += 1
    else:
        n = ""
    return f"{out_column}{n}"


def _prepare_table_for_excel_formulas(table):
    """Convert columns so they'll work with Excel formulas.

    Excel cannot handle datetime columns, so we convert those to Excel dates.
    """
    # Extract a table of just the datetimes. They're np.datetime64
    colnames = table.columns[table.dtypes == "datetime64[ns]"]
    if not len(colnames):
        return table

    datetime_table = table[colnames]
    number_table = pd.DataFrame(
        index=table.index, columns=datetime_table.columns, dtype=float,
    )
    # Excel's number system has two date ranges:
    # 1 .. 60: 1 is 1900-01-01. 60 is 1900-03-01 (1900-02-29 didn't happen)
    # 61 .. *: 61 is 1900-03-01
    # https://docs.microsoft.com/en-gb/office/troubleshoot/excel/wrongly-assumes-1900-is-leap-year
    #
    # But we won't do that. We'll just say 2 is 1900-01-01. This is what
    # LibreOffice and Google Sheets do.
    one_day = np.timedelta64(1, "D").astype("timedelta64[ns]")
    excel_1900_min_date = np.datetime64("1900-01-01").astype("datetime64[ns]")
    excel_1900_zero_date = np.datetime64("1899-12-30").astype("datetime64[ns]")

    number_table[datetime_table >= excel_1900_min_date] = (
        datetime_table - excel_1900_zero_date
    ) / one_day
    # Anything else is null

    new_table = table.copy()
    new_table[colnames] = number_table
    return new_table


def render(table, params, **kwargs):
    if table is None:
        return None  # no rows to process

    if params["syntax"] == "excel":
        input_table = _prepare_table_for_excel_formulas(table)
        formula: str = params["formula_excel"]
        if not formula.strip():
            return table
        all_rows: bool = params["all_rows"]
        try:
            newcol = excel_formula(input_table, formula, all_rows)
        except UserVisibleError as e:
            return e.i18n_message
    else:
        formula: str = params["formula_python"].strip()
        if not formula:
            return table
        try:
            newcol = python_formula(table, formula)
        except UserVisibleError as e:
            return e.i18n_message
        except Exception as e:
            return str(e)

    out_column = _get_output_column(table, params["out_column"])
    table[out_column] = newcol

    return table


def _migrate_params_v0_to_v1(params):
    """
    v0: syntax is int, 0 means excel, 1 means python

    v1: syntax is 'excel' or 'python'
    """
    return {**params, "syntax": ["excel", "python"][params["syntax"]]}


def migrate_params(params):
    if isinstance(params["syntax"], int):
        params = _migrate_params_v0_to_v1(params)
    return params
