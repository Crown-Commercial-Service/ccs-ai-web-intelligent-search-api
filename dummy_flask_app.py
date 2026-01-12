import uuid
from flask import Flask, render_template, session


app = Flask(__name__)
app.secret_key = 'your_very_secret_key_here'  # Required for sessions


@app.route('/')
def index():
    # Check if a user_id already exists in the session, if not, create one
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())  # Creates a unique ID like 'a1b2c3d4...'

    return render_template('index.html', user_id=session['user_id'])


if __name__ == '__main__':
    app.run(debug=True, port=5000)