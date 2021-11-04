import os
import re
from pathlib import Path
import datetime
import time
from concurrent.futures import ThreadPoolExecutor
from flask import (
    Flask,
    flash,
    abort,
    render_template,
    redirect,
    request,
    send_file,
    url_for,
)

from flask_executor import Executor as Flask_Executor
from flask_login import LoginManager, login_user, logout_user, login_required
from peewee import *
import operator
import functools
from . import speech_api
from . import inventory
from . import db

db.database.create_tables([db.Call, db.Inventory, db.User])

app = Flask(__name__, instance_relative_config=True)

app.config.from_pyfile("config.py")

executor = ThreadPoolExecutor()

flask_executor = Flask_Executor(app)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)

# inventory.end_incomplete_inventory()


def background_inventory():
    while True:
        print("Start background inventory check!")
        query = db.Inventory.select().where(db.Inventory.end_date == None)
        if query.exists():
            print("Already inventorying!")
        else:
            print("Running inventory!")
            with app.app_context():
                inventory.run_inventory()
        time.sleep(app.config["INVENTORY_INTERVAL"])


executor.submit(background_inventory)


@login_manager.user_loader
def load_user(user_id):
    return db.User.select(db.User.id == user_id).get()


@app.template_filter("parent")
def parent(path):
    path = Path(path)
    return path.parent


@app.template_filter("seconds_fmt")
def seconds_fmt(seconds):
    return str(datetime.timedelta(seconds=int(seconds)))


@app.template_filter("timestamp_link")
def timestamp_link(text):
    patterns = re.findall("({[0-9]*})(\\w+)", text)
    print(patterns)
    print("length of patterns: " + str(len(patterns)))
    if len(patterns) > 0:
        print("patterns to replace!")
        for pattern in patterns:
            seconds_pattern = pattern[0]
            escaped_seconds_pattern = re.escape(seconds_pattern)
            seconds = re.search("{([0-9]*)}", seconds_pattern).group(1)
            word = pattern[1]
            print("seconds pattern " + seconds_pattern)
            print("escaped_seconds_pattern " + escaped_seconds_pattern)
            print("seconds " + seconds)
            print("word " + word)

            # result = re.search("{([0-9]*)}(\\w+)?", pattern[0]+pattern[1])
            # print(result)
            # if result and len(result.groups()) > 0:
            #     print(result.group(1))
            #     print(result.group(2))
            text = re.sub(
                escaped_seconds_pattern + word,
                '<a role="button" seconds="%s" class="seconds" style="color:#85C1E9;">%s</a>' % (seconds, word),
                text,
            )
    return text


@app.template_filter("regex_capture")
def regex_capture(text, regex):
    result = re.search(regex, text, flags=re.IGNORECASE)
    if result and len(result.groups()) > 0:
        concat = ""
        for group in result.groups():
            if concat == "":
                concat = group
            else:
                concat = concat + " ... " + group
        return concat
    else:
        return text

    return result


@app.before_request
def before_request():
    db.database.connect()


@app.after_request
def after_request(response):
    response.headers.add('Accept-Ranges', 'bytes')
    db.database.close()
    return response


@app.route("/", defaults={"req_path": ""})
@app.route("/<path:req_path>")
@login_required
def explore(req_path):
    # Joining the base and the requested path
    abs_path = Path(app.config["DOWNLOAD_FOLDER"]).joinpath(req_path)

    # Return 404 if path doesn't exist
    if not os.path.exists(abs_path):
        return abort(404)

    # Check if path is a file and serve
    if abs_path.is_file():
        return send_file(abs_path)

    # Show directory contents
    files = os.listdir(abs_path)
    files.sort()
    metadata = None
    # Determine if we are on a directory leaf
    if len(files) > 0 and abs_path.joinpath(files[0]).is_file():
        leaf = True
        rel_path = abs_path.relative_to(app.config["DOWNLOAD_FOLDER"])
        # Compose a dict where relative path is the key
        metadata = {}
        for file in files:
            path = rel_path.joinpath(file)
            file_metadata = db.Call.select().where(db.Call.path == path)
            if file_metadata:
                file_metadata = file_metadata.get()
                data = {
                    "incoming": file_metadata.incoming,
                    "receiving": file_metadata.receiving,
                    "initiating": file_metadata.initiating,
                    "text": file_metadata.text,
                    "date_time": file_metadata.date_time,
                    "duration": file_metadata.duration,
                }
                metadata[str(path)] = data
            else:
                metadata[str(path)] = None
    else:
        leaf = False

    return render_template("explore.j2", files=files, metadata=metadata, leaf=leaf)


@app.route("/search")
@login_required
def search():
    if request.args:
        print(request.args)
        clauses = []
        for key in request.args:
            if key == "text":
                if request.args.get("regex") == "on":
                    clauses.append(db.Call.text.regexp(request.args.get(key)))
                else:
                    # Strip any regex
                    s = re.escape(request.args.get(key))
                    clauses.append(db.Call.text.regexp(s))

            if key == "date_filter" and request.args[key].strip() != "":
                regex = re.search(
                    "^(.*) - (.*)$", request.args.get("date_filter").strip()
                )
                start_date = datetime.datetime.strptime(
                    regex.group(1), "%m/%d/%Y %I:%M %p"
                )
                end_date = datetime.datetime.strptime(
                    regex.group(2), "%m/%d/%Y %I:%M %p"
                )
                clauses.append((db.Call.date_time.between(start_date, end_date)))

            if key == "initiating" and request.args[key].strip() != "":
                clauses.append(db.Call.initiating == request.args.get(key).strip())

            if key == "receiving" and request.args[key].strip() != "":
                clauses.append(db.Call.receiving == request.args.get(key).strip())

            if key == "bi-directional" and request.args[key].strip() != "":
                clauses.append(
                    (db.Call.initiating == request.args.get(key).strip())
                    | (db.Call.receiving == request.args.get(key).strip())
                )

            if key == "incoming" and not request.args.get("outgoing"):
                clauses.append(db.Call.incoming == True)

            if key == "outgoing" and not request.args.get("incoming"):
                clauses.append(db.Call.incoming == False)

            if key == "max_duration" and request.args[key].strip() != "":
                clauses.append(
                    db.Call.duration <= float(request.args.get(key).strip()) * 60
                )

            if key == "min_duration" and request.args[key].strip() != "":
                clauses.append(
                    db.Call.duration >= float(request.args.get(key).strip()) * 60
                )

        # try:
        if request.args["logic"] == "and":
            filter = functools.reduce(operator.and_, clauses)
        else:
            filter = functools.reduce(operator.or_, clauses)

        results = db.Call.select().where(filter).order_by(db.Call.date_time.asc())

        print(results)

        total_duration = 0

        if not results.exists():
            flash("Nothing found!")
            average_duration = 0
        else:
            for result in results:
                total_duration = total_duration + result.duration
            average_duration = total_duration / results.count()

        return render_template(
            "search.j2",
            results=results,
            total_duration=total_duration,
            average_duration=average_duration,
            args=request.args,
        )
        # except Exception as e:
        #     flash(str(e))
        #     return render_template("search.j2", args=request.args)
    else:
        return render_template("search.j2", args=request.args)


@app.route("/run-inventory")
@login_required
def run_inventory():
    print("Manual inventory run!")
    query = db.Inventory.select().where(db.Inventory.end_date == None)
    if query.exists():
        flash("Inventory is already running!")
        print("Inventory is already running!")
    else:
        flash("Running inventory!")
        print("Running inventory!")
        flask_executor.submit(inventory.run_inventory)
    return redirect(url_for("inventory_status"))


@app.route("/inventory-status")
@login_required
def inventory_status():
    query = db.Inventory.select().order_by(db.Inventory.start_date.desc()).limit(1)
    if query.exists():
        last_inventory = query.get()
    else:
        flash("No inventory found!")
        last_inventory = None
    calls = db.Call.select()
    return render_template("inventory_status.j2", last_inventory=last_inventory)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        password = request.form.get("password")
        user = db.User.select().get()
        if user.password == password:
            login_user(user)
            return redirect(url_for("explore"))
        else:
            flash("Bad credential!")
    return render_template("login.j2")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))
