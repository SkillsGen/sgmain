from flask import Flask, flash, redirect, render_template, request, session, url_for, jsonify, send_from_directory
from flask_session import Session
from functools import wraps
from tempfile import gettempdir
from urllib.parse import urlparse
from decimal import *
from flask_mail import Mail, Message
import json
import requests
import sqlalchemy
import os
import psycopg2
import gviz_api

app = Flask(__name__)

mail = Mail(app)

app.config['MAIL_SERVER'] = os.environ.get("MAIL_SERVER")
app.config['MAIL_USERNAME'] = os.environ.get("MAIL_USERNAME")
app.config['MAIL_PASSWORD'] = os.environ.get("MAIL_PASSWORD")
mail = Mail(app)

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


@app.route("/", methods=["GET"])
def index(message=""):
    
    upcoming = db.execute("SELECT bookings.id, bookings.course AS courseid, bookings.date, courses.name AS name, courses.type AS type, courses.icon as icon, to_char(CAST(date as DATE), 'day') AS day, to_char(CAST(date as DATE), 'month') AS month, EXTRACT(day FROM CAST(date as DATE)) FROM bookings INNER JOIN courses ON bookings.course=courses.id WHERE bookings.private = 0 AND type != 0 AND cast(date as DATE) > CURRENT_DATE ORDER BY date LIMIT 4")
    
    for row in upcoming:
        row["day"] = row["day"].title()
        row["month"] = row["month"].title()
        row["date_part"] = int(row["date_part"])
    
    return render_template("index.html", upcoming = upcoming)

@app.route("/schedule", methods=["GET", "POST"]) #Catastrophically ineffecient
def schedule(message=""):
    if request.method != "POST":
        schedule = db.execute("SELECT bookings.id, bookings.course, bookings.date, courses.name AS name, courses.type AS type, courses.icon as icon, courses.duration, to_char(CAST(date as DATE), 'Day') AS day, to_char(CAST(date as DATE), 'yyyy') AS year, to_char(CAST(date as DATE), 'Month') AS month, to_char(EXTRACT(day FROM CAST(date as DATE)), '99') as daynum FROM bookings INNER JOIN courses ON bookings.course=courses.id WHERE bookings.private = 0 AND type != 0 AND cast(date as DATE) > CURRENT_DATE ORDER BY date")

        years = db.execute("SELECT DISTINCT to_char(CAST(date as DATE), 'yyyy') AS year FROM bookings INNER JOIN courses ON bookings.course=courses.id WHERE bookings.private = 0 AND type != 0 AND cast(date as DATE) > CURRENT_DATE ORDER BY year")

        months = db.execute("SELECT DISTINCT ON (EXTRACT(month FROM cast(date as DATE)), EXTRACT(year FROM cast(date as DATE))) to_char(CAST(date as DATE), 'Month') AS month, to_char(CAST(date as DATE), 'yyyy') AS year FROM bookings INNER JOIN courses ON bookings.course=courses.id WHERE bookings.private = 0 AND type != 0 AND cast(date as DATE) > CURRENT_DATE ORDER BY EXTRACT(month FROM cast(date as DATE))")

        return render_template("schedule.html", schedule = schedule, years=years, months=months)
    
    else:
        schedule = db.execute("SELECT bookings.id, bookings.course, bookings.date, courses.name AS name, courses.type AS type, courses.icon as icon, courses.duration, to_char(CAST(date as DATE), 'Day') AS day, to_char(CAST(date as DATE), 'yyyy') AS year, to_char(CAST(date as DATE), 'Month') AS month, to_char(EXTRACT(day FROM CAST(date as DATE)), '99') as daynum FROM bookings INNER JOIN courses ON bookings.course=courses.id WHERE bookings.private = 0 AND type != 0 AND cast(date as DATE) > CURRENT_DATE ORDER BY date")
        
        return jsonify(schedule)
    
    
@app.route("/schedule2", methods=["GET"])
def schedule2(message=""):
    return render_template("schedule2.html")

@app.route("/about", methods=["GET"])
def about(message=""):
    return render_template("about.html")

@app.route("/gdpr", methods=["GET"])
def gdpr(message=""):
    return render_template("gdpr.html")

@app.route("/tailored", methods=["GET"])
def tailored(message=""):
    return render_template("tailored.html")


@app.route("/enquire", methods=["GET", "POST"])
def enquire(message=""):
    if request.method == 'POST':
        
        response = request.form.get("g-recaptcha-response")
        
        enquiry = {'name': request.form.get('name'),
                   'email': request.form.get('email'),
                   'phone': request.form.get('phone'),
                   'enquiry': request.form.get('enquiry')
                  }
        
        if response == "" or response == None:
            return render_template('enquire.html', booking = None, enquiry = enquiry, captcha = "failed")
        
        captchadata = {'secret': os.environ["RECAPTCHA_SECRET"],
                       'response': response,
                      }
        
        apiresponse = requests.post('https://www.google.com/recaptcha/api/siteverify', captchadata)
        
        temp = json.loads(apiresponse.text)
        if temp['success'] == True:
            
            subject = "Website Enquiry from \"" + request.form.get("name") + "\" \"" + request.form.get("email") + "\" \"" + request.form.get("phone") + "\""
            
            msg = Message(subject, sender = "training@skillsgen.com", recipients = ["sreinolds@gmail.com", "karen.reinolds@skillsgen.com"])
            
            msg.body = request.form.get("enquiry")

            try:
                db.execute("INSERT INTO enquiries (name, email, phone, enquiry) VALUES (:name, :email, :phone, :enquiry)",
                            name = request.form.get("name"),
                            email = request.form.get("email"),
                            phone = request.form.get("phone"),
                            enquiry = request.form.get("enquiry")
                            )
            except:
                db.execute("INSERT INTO enquiries (name, email, phone, enquiry) VALUES (:name, :email, :phone, :enquiry)",
                            name = request.form.get("name"),
                            email = request.form.get("email"),
                            phone = request.form.get("phone"),
                            enquiry = "INVALID CHARACTER IN INQUIRY, PLEASE SEE EMAIL FOR CONTENTS"
                            )
            
            try:
                mail.send(msg)                
            except:
                return render_template("apologies.html")
            
            return redirect(url_for('thankyou'))
        
        else:
            return render_template('enquire.html', booking = None, enquiry = enquiry, captcha = "failed")
    
    elif request.args.get("token") != None:
        booking = db.execute("SELECT bookings.date, courses.name AS course FROM bookings INNER JOIN courses ON bookings.course=courses.id WHERE bookings.id = :id",
                                id = request.args.get('token')
                                )
        booking = booking[0]
    else:
        booking = None
    return render_template("enquire.html", booking = booking)


@app.route("/thankyou", methods=["GET"])
def thankyou(message=""):
    return render_template("thankyou.html")


@app.route("/apologies", methods=["GET"])
def apologies(message=""):
    return render_template("apologies.html")


@app.route("/it-courses", methods=["GET"])
def itcourses(message=""):
    cats = db.execute("SELECT DISTINCT category, icon FROM courses WHERE type = 1 AND category != '' and category != 'NULL' and category != 'Bitesize' ORDER BY category")
    
    courses = db.execute("SELECT id, name, description, icon, category FROM courses WHERE type = 1")
    
    return render_template("it-courses.html", courses = courses, cats = cats)


@app.route("/bitesize", methods=["GET"])
def bitesize(message=""):
    courses = db.execute("SELECT id, name, description, icon FROM courses WHERE category = 'Bitesize' ORDER BY name")
    return render_template("bitesize.html", courses = courses)


@app.route("/it", methods=["GET"])
def it(message=""):
    if request.args.get("course") == None:
        return "sorry course not found"
    check = db.execute("SELECT EXISTS(SELECT name FROM courses WHERE id = :id AND type = 1)",
                            id = request.args.get("course")
                            )
    if check[0]["exists"] != True:
        return "sorry course not found"
    
    else:
        dates = db.execute("SELECT bookings.id, bookings.date, to_char(CAST(date as DATE), 'month') AS month, EXTRACT(day FROM CAST(date as DATE)) FROM bookings WHERE bookings.course = :id AND cast(date as DATE) > CURRENT_DATE AND bookings.private = 0  ORDER BY date LIMIT 4",
                                id = request.args.get("course")
                                )
        for row in dates:
            row["month"] = row["month"].title()
            row["date_part"] = int(row["date_part"])
        
        course = db.execute("SELECT * FROM courses WHERE id = :id",
                                id = request.args.get("course")
                                )
        if course[0]["contents"] != None:
            contents = "<div class='col-sm-4 contentparam'><h4>" + course[0]['contents'] + "</p></div>"
            contents = contents.replace("\r\n\r\n", "</p></div><div class='col-sm-4 contentparam'><h4>")
            contents = contents.replace(':\r\n', ':</h4><p>')
            contents = contents.replace('\r\n', '<br>')
            course[0]['contents'] = contents
        
        return render_template("it.html", course = course[0], dates = dates)

    
@app.route("/excel", methods=["GET"])
def excel(message=""):
    return render_template("excel.html")


@app.route("/management", methods=["GET"])
def management(message=""):
    courses = db.execute("SELECT id, name, description FROM courses WHERE type = 2")
    return render_template("management.html", courses = courses)


@app.route("/manage-course", methods=["GET"])
def managecourse(message=""):
    if request.args.get("course") == None:
        return "sorry course not found"
    
    check = db.execute("SELECT EXISTS(SELECT name FROM courses WHERE id = :id AND type = 2)",
                            id = request.args.get("course")
                            )
    if check[0]["exists"] != True:
        return "sorry course not found"
    
    else:
        dates = db.execute("SELECT bookings.id, bookings.date, to_char(CAST(date as DATE), 'month') AS month, EXTRACT(day FROM CAST(date as DATE)) FROM bookings WHERE bookings.course = :id AND cast(date as DATE) > CURRENT_DATE AND bookings.private = 0  ORDER BY date LIMIT 4",
                                id = request.args.get("course")
                                )
        for row in dates:
            row["month"] = row["month"].title()
            row["date_part"] = int(row["date_part"])
            
        course = db.execute("SELECT * FROM courses WHERE id = :id",
                                id = request.args.get('course')
                                )
        if course[0]["contents"] != None:
            contents = "<div class='col-sm-4 contentparam'><li>" + course[0]['contents'] + "</li></div>"
            contents = contents.replace("\r\n\r\n", "</li></div><div class='col-sm-4 contentparam'><li>")
            contents = contents.replace("\r\n", "")
            course[0]['contents'] = contents
        return render_template('manage-course.html', course = course[0], dates = dates)

    
@app.route("/technical", methods=["GET"])
def technical(message=""):
    return render_template("technical.html")


@app.route("/exams", methods=["GET"])
def exams(message=""):
    return render_template("exams.html")


@app.route("/search", methods=["GET", "POST"])
def search(message=""):
    if request.method == "POST":
        q = request.form.get("term")
        q = "%%" + q + "%%"
        results = db.execute("SELECT id, name, description, type, icon FROM courses WHERE (name ILIKE :q AND type = 1) OR (name ILIKE :q AND type = 2)", q=q)
        return jsonify(results)
        
    elif request.args.get("term") != None:
        q = request.args.get("term")
        q = "%%" + q + "%%"
        results = db.execute("SELECT id, name, description, type, icon FROM courses WHERE (name ILIKE :q AND type = 1) OR (name ILIKE :q AND type = 2)", q=q)
        return render_template("search.html", results = results, term = request.args.get("term"))
    
    else:
        return render_template("search.html")


@app.route('/sitemap.xml')
def static_from_root():
    return send_from_directory(app.static_folder, request.path[1:])    
    
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404



if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port,debug=False)
    
