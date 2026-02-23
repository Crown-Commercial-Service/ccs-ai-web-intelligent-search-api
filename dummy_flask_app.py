import uuid
import os
from flask import Flask, render_template, session, request, redirect, url_for
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)


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

    return render_template('index.html', user_id=session['user_id'])


if __name__ == '__main__':
    app.run(debug=True)