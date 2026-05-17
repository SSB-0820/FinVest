# FinVest

FinVest is a personal finance management web application that helps users track income, expenses, budgets, savings goals, recurring transactions, notifications, reports, analytics, CSV import/export, and admin monitoring.

## Features

- User registration, login, and forgot password with security questions
- Income and expense transaction management
- CSV transaction import
- CSV report export and JSON backup
- Category management
- Budget planning with alerts
- Recurring expense automation
- Monthly salary automation
- Savings goal tracking
- Dashboard with charts and KPIs
- Reports and analytics
- Notifications with read/unread status
- Account settings, currency, language, and password reset
- Admin dashboard and system performance monitoring

## Technologies Used

- Python
- Flask
- Jinja2
- HTML
- CSS
- JavaScript
- MySQL
- SQLAlchemy
- MongoDB
- PyMongo
- Werkzeug Security

## Project Structure

```text
FinVest/
├── backend/
│   ├── app/
│   │   ├── models/
│   │   ├── routes/
│   │   ├── services/
│   │   ├── jobs/
│   │   ├── templates/
│   │   ├── static/
│   │   └── utils/
│   ├── extensions/
│   ├── main.py
│   └── requirements.txt
├── README.md
└── .gitignore
