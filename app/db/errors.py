from sqlalchemy.exc import IntegrityError


def violates(error: IntegrityError, constraint: str) -> bool:
    """True only when `constraint` is the one that failed.

    Lets an endpoint turn its own unique constraint into a 409 while any other
    integrity error (a foreign key, for example) stays unexpected. The name
    comes from the Postgres driver (psycopg2).
    """
    return getattr(error.orig.diag, "constraint_name", None) == constraint
