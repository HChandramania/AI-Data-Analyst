"""Unique planning references for confirmed joins; SQL policy remains authoritative."""

from copy import deepcopy

import sqlglot
from sqlglot import exp


def join_column_context(datasets):
    if not datasets or not datasets[0].get("confirmed_joins"):
        return datasets, {}
    context = deepcopy(datasets)
    references = {}
    by_source = {}
    for index, dataset in enumerate(context, 1):
        by_source[dataset["id"]] = {}
        for column in dataset["columns"]:
            original = column["id"]
            token = f"s{index}_{original}"
            references[token] = (dataset["table"], original)
            by_source[dataset["id"]][original] = token
            column["id"] = token
    for join in context[0]["confirmed_joins"]:
        join["left_key"] = by_source[join["left"]][join["left_key"]]
        join["right_key"] = by_source[join["right"]][join["right_key"]]
    return context, references


def physical_join_sql(sql, references):
    """Resolve only exact unique tokens; never infer a source from an alias or label."""
    if not sql or not references:
        return sql
    try:
        statements = sqlglot.parse(sql, read="duckdb")
    except sqlglot.errors.SqlglotError:
        return sql  # The execution validator rejects malformed SQL.
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        return sql
    tree = statements[0]
    if tree.args.get("with_") or list(tree.find_all(exp.Subquery)):
        return sql  # Confirmed joins support only direct SELECTs.
    tables = list(tree.find_all(exp.Table))
    aliases = {table.alias_or_name: table.name for table in tables}
    if len(aliases) != len(tables) or len({t.name for t in tables}) != len(tables):
        return sql
    output_aliases = {p.alias for p in tree.expressions if isinstance(p, exp.Alias)}
    # Preserve result-column names used by chart intents for unaliased projections.
    for projection in list(tree.expressions):
        if isinstance(projection, exp.Column) and projection.name in references:
            projection.replace(exp.alias_(projection.copy(), projection.name))
    for column in tree.find_all(exp.Column):
        reference = references.get(column.name)
        if reference is None:
            continue
        if not column.table and column.name in output_aliases and isinstance(column.parent, (exp.Ordered, exp.Group)):
            continue
        table, physical = reference
        candidates = [alias for alias, name in aliases.items() if name == table]
        if len(candidates) != 1 or (column.table and aliases.get(column.table) != table):
            continue  # Leave mismatched references invalid; never repair authorization errors.
        column.set("this", exp.to_identifier(physical))
        column.set("table", exp.to_identifier(candidates[0]))
    return tree.sql(dialect="duckdb")
