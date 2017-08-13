from flask import Flask, flash, redirect, render_template, request, session, url_for, jsonify
from flask_session import Session
from functools import wraps
from tempfile import gettempdir
from urllib.parse import urlparse
from decimal import *
import sqlalchemy
import os
import psycopg2
import gviz_api

app = Flask(__name__)

url = urlparse(os.environ["DATABASE_URL"])
conn = psycopg2.connect(
 database=url.path[1:],
 user=url.username,
 password=url.password,
 host=url.hostname,
 port=url.port
)

class SQL(object):
    """Wrap SQLAlchemy to provide a simple SQL API."""

    def __init__(self, url):
        """
        Create instance of sqlalchemy.engine.Engine.

        URL should be a string that indicates database dialect and connection arguments.

        http://docs.sqlalchemy.org/en/latest/core/engines.html#sqlalchemy.create_engine
        """
        try:
            self.engine = sqlalchemy.create_engine(url)
        except Exception as e:
            raise RuntimeError(e)

    def execute(self, text, *multiparams, **params):
        """
        Execute a SQL statement.
        """
        try:

            # bind parameters before statement reaches database, so that bound parameters appear in exceptions
            # http://docs.sqlalchemy.org/en/latest/core/sqlelement.html#sqlalchemy.sql.expression.text
            # https://groups.google.com/forum/#!topic/sqlalchemy/FfLwKT1yQlg
            # http://docs.sqlalchemy.org/en/latest/core/connections.html#sqlalchemy.engine.Engine.execute
            # http://docs.sqlalchemy.org/en/latest/faq/sqlexpressions.html#how-do-i-render-sql-expressions-as-strings-possibly-with-bound-parameters-inlined
            statement = sqlalchemy.text(text).bindparams(*multiparams, **params)
            result = self.engine.execute(str(statement.compile(compile_kwargs={"literal_binds": True})))

            # if SELECT (or INSERT with RETURNING), return result set as list of dict objects
            if result.returns_rows:
                rows = result.fetchall()
                return [dict(row) for row in rows]

            # if INSERT, return primary key value for a newly inserted row
            elif result.lastrowid is not None:
                return result.lastrowid

            # if DELETE or UPDATE (or INSERT without RETURNING), return number of rows matched
            else:
                return result.rowcount

        # if constraint violated, return None
        except sqlalchemy.exc.IntegrityError:
            return None

        # else raise error
        except Exception as e:
            raise RuntimeError(e)



db = SQL(os.environ["DATABASE_URL"])

app.config["SESSION_FILE_DIR"] = gettempdir()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)


def login_required(f):
    """
    Decorate routes to require login.

    http://flask.pocoo.org/docs/0.11/patterns/viewdecorators/
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return "sorry"
        return f(*args, **kwargs)
    return decorated_function


@app.route("/", methods=["GET"])
def index(message=""):
    
    upcoming = db.execute("SELECT bookings.id, bookings.date, courses.name AS course, to_char(CAST(date as DATE), 'day') AS day, to_char(CAST(date as DATE), 'month') AS month, EXTRACT(day FROM CAST(date as DATE)) FROM bookings INNER JOIN courses ON bookings.course=courses.id WHERE bookings.private = 0 AND cast(date as DATE) > CURRENT_DATE ORDER BY date LIMIT 4")
    
    for row in upcoming:
        row["day"] = row["day"].title()
        row["month"] = row["month"].title()
        row["date_part"] = int(row["date_part"])
    
    return render_template("index.html", upcoming = upcoming)

@app.route("/about", methods=["GET"])
def about(message=""):
    return render_template("about.html")

@app.route("/inquire", methods=["GET", "POST"])
def inquire(message=""):
    if request.method == 'POST':
        data = request.form.get('inquiry')
        return redirect(url_for('thankyou'))
    
    elif request.args.get("token") != None:
        booking = db.execute("SELECT bookings.date, courses.name AS course FROM bookings INNER JOIN courses ON bookings.course=courses.id WHERE bookings.id = :id",
                                id = request.args.get('token')
                                )
        booking = booking[0]
    else:
        booking = None
    return render_template("inquire.html", booking = booking)

@app.route("/thankyou", methods=["GET", "POST"])
def thankyou(message=""):
    return render_template("thankyou.html")

@app.route("/it-courses", methods=["GET", "POST"])
def itcourses(message=""):
    return render_template("it-courses.html")

@app.route("/management", methods=["GET", "POST"])
def management(message=""):
    return render_template("management.html")

@app.route("/technical", methods=["GET", "POST"])
def technical(message=""):
    return render_template("technical.html")

@app.route("/exams", methods=["GET"])
def exams(message=""):
    return render_template("exams.html")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port,debug=True)
    