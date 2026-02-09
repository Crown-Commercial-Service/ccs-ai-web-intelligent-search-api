import uuid
import os
import csv
from datetime import datetime
import ast
from flask import Flask, render_template, session, request, redirect, url_for
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'default-dev-key-123')
api_url = os.getenv('WEBSEARCH_API_URL')
download_url = os.getenv('DOWNLOAD_SOURCE_URL')
CSV_PATH = os.path.join(os.path.dirname(__file__), "website_agreement_data2.csv")


def _format_date(date_str: str) -> str:
    if not date_str:
        return ""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return date_str


def load_agreements():
    """Load all agreements from the local CSV file (no filtering)."""
    agreements = []
    with open(CSV_PATH, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            lots_raw = row.get("lots") or "[]"
            lots = []
            try:
                parsed = ast.literal_eval(lots_raw)
                if isinstance(parsed, list):
                    lots = parsed
            except Exception:
                lots = []

            agreements.append(
                {
                    "id": row.get("id") or "",
                    "title": row.get("title") or "",
                    "rm_number": row.get("rm_number") or "",
                    "start_date": _format_date(row.get("start_date") or ""),
                    "end_date": _format_date(row.get("end_date") or ""),
                    "regulation": row.get("regulation") or "",
                    "agreement_type": row.get("regulation_type") or "",
                    "summary": row.get("summary") or "",
                    "description": row.get("description") or "",
                    "benefits": row.get("benefits") or "",
                    "how_to_buy": row.get("how_to_buy") or "",
                    "lots": lots,
                    "lots_count": len(lots) if lots else 0,
                }
            )
    return agreements

@app.route('/', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        access_key = request.form.get('access_key')

        # Define your secret key here
        if access_key == os.getenv('TEST_ACCESS_KEY'):
            session['logged_in'] = True
            return redirect(url_for('index'))
        else:
            error = "Invalid access key. Please try again or contact support."

    return render_template('login.html', error=error)



@app.route('/index')
def index():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())

    return render_template('index_v2.html', user_id=session['user_id'], api_url=api_url, download_url=download_url)

@app.route('/results')
def results():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())

    # Note: we intentionally ignore query filtering for now and render all CSV results.
    agreements = load_agreements()
    return render_template(
        'results.html',
        user_id=session['user_id'],
        api_url=api_url,
        download_url=download_url,
        agreements=agreements,
    )


@app.route('/agreement/<rm_number>')
def agreement(rm_number: str):
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    agreements = load_agreements()
    selected = next((a for a in agreements if a.get("rm_number") == rm_number), None)
    if not selected:
        return redirect(url_for('results'))

    return render_template(
        'agreement.html',
        user_id=session.get('user_id', ''),
        api_url=api_url,
        download_url=download_url,
        agreement=selected,
    )


if __name__ == '__main__':
    app.run(debug=True)
