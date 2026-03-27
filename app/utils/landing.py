from app.utils.roles import is_admin_role


def resolve_landing_endpoint(role: str | None) -> str:
    """Retorna endpoint de inicio según rol autenticado."""
    return "dashboard.dashboard_home" if is_admin_role(role) else "home.home_dashboard"
