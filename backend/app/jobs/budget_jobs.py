
from app.services.automation_service import run_all_automations


def run_due_budget_jobs(today=None):
    return run_all_automations(today=today)
