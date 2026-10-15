"""Small SQL AST allowlist for registered single-source analytical queries."""

import re

import sqlglot
from sqlglot import exp

IDENTIFIER = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]{0,63}\Z")
ALLOWED = {
    exp.Select,
    exp.From,
    exp.Where,
    exp.Group,
    exp.Order,
    exp.Ordered,
    exp.Limit,
    exp.With,
    exp.CTE,
    exp.TableAlias,
    exp.Subquery,
    exp.Table,
    exp.Column,
    exp.Identifier,
    exp.Alias,
    exp.Literal,
    exp.Star,
    exp.Null,
    exp.Sum,
    exp.Count,
    exp.Avg,
    exp.Min,
    exp.Max,
    exp.Add,
    exp.Sub,
    exp.Mul,
    exp.Div,
    exp.Paren,
    exp.EQ,
    exp.NEQ,
    exp.GT,
    exp.GTE,
    exp.LT,
    exp.LTE,
    exp.And,
    exp.Or,
    exp.Not,
    exp.Is,
    exp.Between,
    exp.In,
    exp.Like,
    exp.Lower,
    exp.Cast,
    exp.TryCast,
    exp.DataType,
    exp.DateTrunc,
    exp.TimeToStr,
    exp.Extract,
    exp.Distinct,
    exp.Having,
    exp.Neg,
    exp.Case,
    exp.If,
    exp.Coalesce,
    exp.Join,
}


class SqlRejected(ValueError):
    pass


def _name(value: str) -> str:
    if not IDENTIFIER.fullmatch(value):
        raise SqlRejected("Unsafe identifier.")
    return value.lower()


def _check_nodes(tree: exp.Expression) -> None:
    for node in tree.walk():
        if type(node) not in ALLOWED:
            raise SqlRejected(f"Unsupported SQL construct: {type(node).__name__}.")
        if isinstance(node, exp.DataType) and node.this != exp.DataType.Type.DATE:
            raise SqlRejected("Only DATE casts are supported.")
        if isinstance(node, exp.TryCast):
            target = node.args.get("to")
            if not isinstance(target, exp.DataType) or target.this != exp.DataType.Type.DATE:
                raise SqlRejected("Only DATE casts are supported.")
        if isinstance(node, exp.DateTrunc):
            unit = node.args.get("unit")
            if not isinstance(unit, exp.Literal) or unit.this.lower() not in {"month", "year", "day"}:
                raise SqlRejected("Unsupported date grouping.")
        if isinstance(node, exp.TimeToStr):
            format_literal = node.args.get("format")
            if not isinstance(format_literal, exp.Literal) or format_literal.this not in {"%Y-%m", "%Y", "%Y-%m-%d"}:
                raise SqlRejected("Unsupported date formatting.")
        if isinstance(node, exp.Literal) and len(str(node.this)) > 200:
            raise SqlRejected("SQL literal is too long.")


def _check_columns(
    expr: exp.Expression | None, columns: set[str], source_alias: str, aliases: set[str] | None = None
) -> None:
    if expr is None:
        return
    if any(isinstance(node, exp.Select) for node in expr.walk()):
        raise SqlRejected("Nested scalar queries are unsupported.")
    for column in expr.find_all(exp.Column):
        if column.is_star:
            continue
        name = _name(column.name)
        if column.table and _name(column.table) != source_alias:
            raise SqlRejected("Unknown table qualifier.")
        if name not in columns and (aliases is None or name not in aliases):
            raise SqlRejected("Unknown column.")


def _validate_select(node: exp.Expression, registered: dict[str, set[str]], inherited: dict[str, set[str]]) -> set[str]:
    if not isinstance(node, exp.Select):
        raise SqlRejected("Only SELECT queries are supported.")
    ctes = dict(inherited)
    with_clause = node.args.get("with_")
    if with_clause:
        if with_clause.args.get("recursive"):
            raise SqlRejected("Recursive CTEs are unsupported.")
        for cte in with_clause.expressions:
            name = _name(cte.alias)
            if name in ctes or name in registered:
                raise SqlRejected("Duplicate or shadowing CTE name.")
            ctes[name] = _validate_select(cte.this, registered, ctes)
    if node.args.get("joins") or node.args.get("laterals"):
        raise SqlRejected("Joins require an explicit join workflow.")
    source = node.args.get("from_")
    if not source or not source.this:
        raise SqlRejected("A registered dataset source is required.")
    item = source.this
    if isinstance(item, exp.Table):
        if item.db or item.catalog:
            raise SqlRejected("Qualified table names are unsupported.")
        table_name = _name(item.name)
        columns = registered.get(table_name) or ctes.get(table_name)
        if columns is None:
            raise SqlRejected("Unknown or unauthorized table.")
        source_alias = _name(item.alias_or_name)
    elif isinstance(item, exp.Subquery):
        if not item.alias:
            raise SqlRejected("Subqueries need an alias.")
        columns = _validate_select(item.this, registered, ctes)
        source_alias = _name(item.alias)
    else:
        raise SqlRejected("Unsupported data source.")
    output = set()
    for projection in node.expressions:
        _check_columns(projection, columns, source_alias)
        if isinstance(projection, exp.Star):
            output.update(columns)
        elif isinstance(projection, exp.Alias):
            output.add(_name(projection.alias))
        elif isinstance(projection, exp.Column):
            output.add(_name(projection.name))
        else:
            raise SqlRejected("Computed columns need a safe alias.")
    for key in ("where", "group", "having", "order", "limit"):
        _check_columns(
            node.args.get(key), columns, source_alias, output if key in {"group", "having", "order"} else None
        )
    if not output:
        raise SqlRejected("Query has no output columns.")
    return output


def _validate_joined(tree, registered, confirmed):
    if not isinstance(tree, exp.Select) or tree.args.get("with_") or list(tree.find_all(exp.Subquery)):
        raise SqlRejected("Confirmed joins require a direct SELECT over registered tables.")
    tables = list(tree.find_all(exp.Table))
    aliases = {}
    for table in tables:
        name, alias = _name(table.name), _name(table.alias_or_name)
        if name not in registered or table.db or table.catalog or alias in aliases:
            raise SqlRejected("Unknown or repeated joined source.")
        aliases[alias] = name
    if len(tables) != len(confirmed) + 1 or len(set(aliases.values())) != len(tables):
        raise SqlRejected("Join must use exactly the confirmed sources.")
    joins = tree.args.get("joins", [])
    if len(joins) != len(confirmed):
        raise SqlRejected("Join relationship mismatch.")
    first = tree.args.get("from_")
    if not first or not isinstance(first.this, exp.Table):
        raise SqlRejected("Direct source required.")
    if first.this.name != f"dataset_{confirmed[0].left.hex}":
        raise SqlRejected("Join base mismatch.")
    joined = {confirmed[0].left}
    for join, expected in zip(joins, confirmed, strict=True):
        if expected.left not in joined or expected.right in joined:
            raise SqlRejected("Join order must connect each new source to the joined set.")
        joined.add(expected.right)
        on = join.args.get("on")
        kind = (join.side or join.kind or "inner").lower()
        if (
            kind != expected.type
            or join.args.get("using")
            or join.args.get("method")
            or join.kind not in {"", "INNER"}
            or join.side not in {"", "LEFT"}
        ):
            raise SqlRejected("Unconfirmed join type.")
        if not isinstance(join.this, exp.Table) or join.this.name != f"dataset_{expected.right.hex}":
            raise SqlRejected("Unconfirmed join target.")
        if not isinstance(on, exp.EQ) or not isinstance(on.left, exp.Column) or not isinstance(on.right, exp.Column):
            raise SqlRejected("Join needs the exact confirmed equality keys.")
        actual = {(aliases.get(c.table), c.name) for c in (on.left, on.right)}
        wanted = {
            (f"dataset_{expected.left.hex}", expected.left_key),
            (f"dataset_{expected.right.hex}", expected.right_key),
        }
        if actual != wanted:
            raise SqlRejected("Unconfirmed join keys.")
    output = {_name(p.alias_or_name) for p in tree.expressions if p.alias_or_name and not isinstance(p, exp.Star)}
    for col in tree.find_all(exp.Column):
        if col.is_star:
            raise SqlRejected("Select explicit joined columns.")
        if not col.table:
            if col.name not in output or not isinstance(col.parent, (exp.Ordered, exp.Group)):
                raise SqlRejected("Joined columns must be qualified.")
        elif col.table not in aliases or col.name not in registered[aliases[col.table]]:
            raise SqlRejected("Unknown joined column.")
    for p in tree.expressions:
        if not isinstance(p, (exp.Column, exp.Alias)):
            raise SqlRejected("Joined projections need explicit columns or aliases.")


def validate_sql(sql: str, registered: dict[str, set[str]], confirmed=None) -> str:
    if not sql or len(sql) > 12000:
        raise SqlRejected("SQL is empty or exceeds 12,000 characters.")
    try:
        statements = sqlglot.parse(sql, read="duckdb")
    except sqlglot.errors.SqlglotError:
        raise SqlRejected("SQL could not be parsed.") from None
    if len(statements) != 1 or statements[0] is None:
        raise SqlRejected("Exactly one SQL statement is required.")
    tree = statements[0]
    _check_nodes(tree)
    registry = {_name(k): {_name(c) for c in v} for k, v in registered.items()}
    if confirmed:
        _validate_joined(tree, registry, confirmed)
    else:
        _validate_select(tree, registry, {})
    return tree.sql(dialect="duckdb")
