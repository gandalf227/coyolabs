from app.models.debt import Debt


def user_has_open_debts(user_id: int) -> bool:
    return (
        Debt.query
        .filter(Debt.user_id == user_id, Debt.status == "OPEN")
        .count()
        > 0
    )
