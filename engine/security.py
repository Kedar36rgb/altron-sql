import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError


class UnsafeSQLError(ValueError):
    pass

ALLOWED_ROOTS = (exp.Select, exp.Union, exp.Intersect, exp.Except)
_FORBIDDEN_NAMES = ["Insert", "Update", "Delete", "Drop", "Create", "Alter",
"AlterTable", "Command", "Pragma", "Attach", "Detach",
"Merge", "TruncateTable", "Transaction", "Commit", "Rollback"]
FORBIDDEN = tuple(getattr(exp, n) for n in _FORBIDDEN_NAMES if hasattr(exp, n))
BLOCKED_FUNCS = {"load_extension", "readfile", "writefile"}

def validate_sql(query: str) -> str:
    """Return normalized SQLite SQL if it is a single read-only query, else raise."""
    try:
        statements = [s for s in sqlglot.parse(query, read="sqlite") if s is not None]
    except SqlglotError as e:
        raise UnsafeSQLError(f"Unparseable SQL: {e}") from e
        
    if len(statements) != 1:
        raise UnsafeSQLError("Exactly one statement is allowed.")
        
    tree = statements[0]
    
    if not isinstance(tree, ALLOWED_ROOTS):
        raise UnsafeSQLError("Only SELECT queries are allowed.")
        
    if tree.find(*FORBIDDEN):
        raise UnsafeSQLError("Query contains a forbidden operation.")
        
    for fn in tree.find_all(exp.Anonymous):
        if str(fn.name).lower() in BLOCKED_FUNCS:
            raise UnsafeSQLError(f"Function {fn.name} is not allowed.")
            
    return tree.sql(dialect="sqlite")

def is_safe_sql(query: str) -> bool:
    try:
        validate_sql(query)
        return True
    except UnsafeSQLError:
        return False