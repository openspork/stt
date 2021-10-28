import os
import re
from pathlib import Path
import datetime
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
from flask_executor import Executor
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

executor = Executor(app)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    return db.User.select(db.User.id == user_id).get()


@app.template_filter("parent")
def parent(path):
    path = Path(path)
    return path.parent


@app.template_filter("time_fmt")
def time_fmt(seconds):
    return str(datetime.timedelta(seconds=int(seconds)))


@app.before_request
def before_request():
    db.database.connect()


@app.after_request
def after_request(response):
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

            if key == "text":
                clauses.append(db.Call.text.contains(request.args.get(key)))
        try:
            if request.args["logic"] == "and":
                filter = functools.reduce(operator.and_, clauses)
            else:
                filter = functools.reduce(operator.or_, clauses)

            results = db.Call.select().where(filter).order_by(db.Call.date_time.asc())

            total_duration = 0

            if not results.exists():
                flash("Nothing found!")
                average_duration = 0
            else:
                for result in results:
                    total_duration = total_duration + result.duration
                average_duration = total_duration / results.count()
                print(fn.MAX(results).scalar())
                raise Exception

            return render_template("search.j2", results=results, total_duration=total_duration, average_duration=average_duration, args=request.args)
        except Exception as e:
            flash(str(e))
            return redirect(url_for("search"))
    else:
        return render_template("search.j2", args=request.args)


@app.route("/run-inventory")
@login_required
def run_inventory():
    query = db.Inventory.select().where(db.Inventory.end_date == None)
    if query.exists():
        print("already inventorying")
        current_inventory = query.get()
        flash(
            "Inventory is already running!  %s/%s"
            % (
                current_inventory.skipped_paths + current_inventory.finished_paths,
                current_inventory.total_paths,
            )
        )
    else:
        flash("Running inventory!")
        # inventory.dispatch_inventory()
        executor.submit(inventory.run_inventory)
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
