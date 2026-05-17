
from app import create_app
from app.jobs.budget_jobs import run_due_budget_jobs


def run_once():
    app = create_app()
    with app.app_context():
        return run_due_budget_jobs()


if __name__ == "__main__":
    created = run_once()
    print(f"Created {created} scheduled transaction(s).")
