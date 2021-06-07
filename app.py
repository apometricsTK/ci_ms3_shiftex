import os
import time
import datetime
import uuid

from flask import Flask, render_template, request, url_for, redirect, flash

from bson import ObjectId
from flask_restful import Api, Resource
from flask_login import LoginManager, current_user, login_user, logout_user, login_required, UserMixin
from flask_bcrypt import Bcrypt

from db import mongo
from forms import LoginForm, RegistrationForm


if os.path.exists("env.py"):
    import env

app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY")

app.config["MONGO_URI"] = os.environ.get("MONGO_URI")

mongo.init_app(app)

bcrypt = Bcrypt()
bcrypt.init_app(app)

api = Api(app)

login_manager = LoginManager()
login_manager.init_app(app)


class User(UserMixin):
    """
    https://stackoverflow.com/questions/54992412/flask-login-usermixin-class-with-a-mongodb/55003240
    """
    def __init__(self, user_json):
        self.user_json = user_json
        self.first_name = user_json["first_name"]
        self.last_name = user_json["last_name"]
        self.email = user_json["email"]
        self.drugstoreId = user_json["drugstoreId"]
        self.passwordHash = user_json["passwordHash"]
        self.id = user_json["user_id"]

    @staticmethod
    def register_user(first_name, last_name, email, drugstore_id, password_hash):
        user_id_random = uuid.uuid4().urn
        user_id_taken = mongo.db.users.find_one({"user_id": user_id_random})
        while user_id_taken is not None:
            user_id_random = uuid.uuid4().urn
            user_id_taken = mongo.db.users.find_one({"user_id": user_id_random})

        registration = {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "drugstoreId": int(drugstore_id),
            "passwordHash": password_hash,
            "user_id": user_id_random
        }
        mongo.db.users.insert_one(registration)

    @login_manager.user_loader
    def load_user(user_id):
        u = mongo.db.users.find_one({"user_id": user_id})
        if not u:
            return None
        return User(u)


class SwapsQueriesAPI(Resource):
    @login_required
    def get(self, rotation_id):
        swaps_plan_cursor = list(mongo.db.swaps.find({"planId": int(rotation_id)}))
        if len(swaps_plan_cursor) == 0:
            return {"error": "Not Found"}, 404

        else:
            swaps_plan = []
            for document in swaps_plan_cursor:
                document.pop("_id")
                swaps_plan.append(document)
            return swaps_plan, 200


class SwapQueryAPI(Resource):
    @login_required
    def get(self, shift_id):
        check_swap = mongo.db.swaps.find_one({"shiftId": shift_id})
        if check_swap is None:
            return {"error": "Not Found"}, 404

        else:
            check_swap.pop("_id")
            return check_swap, 200

    @login_required
    def put(self, shift_id):
        check_swap = mongo.db.swaps.find_one({"shiftId": shift_id})
        if check_swap is not None:
            return {"error": "Already there"}, 409

        else:
            find_shift_cursor = mongo.db.shifts.find_one({"_id": ObjectId(shift_id)})
            query_document = {
                "shiftId": shift_id,
                "drugstoreId": find_shift_cursor["drugstoreId"],
                "planId": find_shift_cursor["planId"],
                "digitsId": find_shift_cursor["digitsId"],
                "offer": [],
                "reject": [],
                "accept": []
            }
            mongo.db.swaps.insert_one(query_document)
            return {"success": "Swap query posted"}, 201

    @login_required
    def delete(self, shift_id):
        check_swap = mongo.db.swaps.find_one({"shiftId": shift_id})
        if check_swap is None:
            return {"error": "Not Found"}, 404

        else:
            mongo.db.swaps.delete_one({"shiftId": shift_id})
            return "", 204


class SwapHandlingAPI(Resource):
    @login_required
    def patch(self, original_shift, mode, offer_id):
        swap_document = mongo.db.swaps.find_one({"shiftId": original_shift})
        offer_document = mongo.db.shifts.find_one({"_id": ObjectId(offer_id)})

        if swap_document is None:
            return {"error": "Original shift not found"}, 404
        elif mode not in ["offer", "reject", "accept"]:
            return {"error": "Mode not supported"}, 400
        elif offer_document is None:
            return {"error": "Offered shift not found"}, 404

        elif mode == "offer":
            if offer_id in swap_document["offer"] or swap_document["reject"] or swap_document["accept"]:
                return {"error": "Offered already"}, 409
            else:
                mongo.db.swaps.find_one_and_update(
                    {"shiftId": original_shift},
                    {"$addToSet":
                        {"offer": offer_id}
                     }
                )
                return {"success": "Offer posted"}, 201

        elif mode == "reject":
            if offer_id in swap_document[mode]:
                return {"error": "Rejected already"}, 409
            else:
                mongo.db.swaps.find_one_and_update(
                    {"shiftId": original_shift},
                    {"$addToSet":
                        {mode: offer_id},
                     "$pull":
                        {"offer": offer_id,
                         "accept": offer_id
                         }
                     }
                )
                return {"success": "Offer rejected"}, 201

        elif mode == "accept":
            if offer_id in swap_document[mode]:
                return {"error": "Accepted already"}, 409
            else:
                mongo.db.swaps.find_one_and_update(
                    {"shiftId": original_shift},
                    {"$addToSet":
                        {mode: offer_id},
                     "$pull":
                        {"offer": offer_id,
                         "reject": offer_id
                         }
                     }
                )
                return {"success": "Offer accepted"}, 201

        else:
            return {"error": "Bad request"}, 400


class ShiftsQueriesAPI(Resource):
    @login_required
    def post(self):
        shift_id_dict = eval(request.data.decode("UTF-8"))
        shift_object_id_list = []
        for object_id_string in shift_id_dict["ids"]:
            shift_object_id_list.append(ObjectId(object_id_string))

        shifts_list = list(mongo.db.shifts.aggregate([
            {"$match": {"_id": {"$in": shift_object_id_list}}},
            {"$project": {
                "_id": 0,
                "shiftId": {
                    "$toString": "$_id"
                },
                "drugstoreId": 1,
                "from": 1,
                "to": 1
            }}
        ]))
        return shifts_list, 200


api.add_resource(SwapsQueriesAPI, "/api/swaps/<rotation_id>", endpoint="swaps_queries")
api.add_resource(SwapQueryAPI, "/api/swap/<shift_id>", endpoint="swap_query")
api.add_resource(SwapHandlingAPI, "/api/swap/<original_shift>/<mode>/<offer_id>", endpoint="swap_handling")
api.add_resource(ShiftsQueriesAPI, "/api/shifts/", endpoint="shifts_queries")


@app.template_filter()
def timestamp_to_readable(timestamp):
    timestamp = timestamp // 1000
    dt = datetime.datetime.fromtimestamp(timestamp)
    return dt


@app.template_filter()
def duration_to_readable(shift):
    shift_start = timestamp_to_readable(shift["from"])
    shift_end = timestamp_to_readable(shift["to"])
    duration = shift_end - shift_start
    return duration.total_seconds() // 3600


@app.template_filter()
def shift_id_list(swap_list):
    output = []
    for shift in swap_list:
        output.append(shift["shiftId"])
    return output


@app.route("/")
def index():
    today_time = time.strftime("%A, %d %b %Y", time.localtime())
    now_unixtime = int(time.time()) * 1000
    today_duty_list = list(mongo.db.shifts.find(
        {"$and": [
            {"from": {"$lt": now_unixtime}},
            {"to": {"$gt": now_unixtime}}
        ]}))
    return render_template("index.html",
                           today_duty_list=today_duty_list,
                           today_time=today_time)


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("user"))

    form = LoginForm()

    if form.validate_on_submit():
        check_user = mongo.db.users.find_one({"email": form.email.data})
        if check_user and bcrypt.check_password_hash(check_user["passwordHash"], form.password.data):
            print(check_user)
            user = User(check_user)
            print(user.get_id())
            login_user(user, remember=form.remember.data)
            flash("Login successful!")
            return redirect(url_for("user"))

    return render_template("login.html", form=form)


@login_required
@app.route("/logout")
def logout():
    logout_user()
    flash(f"Logout successful!")
    return redirect(url_for("index"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("user"))

    form = RegistrationForm()

    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode("utf-8")
        User.register_user(form.first_name.data,
                           form.last_name.data,
                           form.email.data,
                           form.drugstore_id.data,
                           hashed_password)
        flash(f"Registration complete for {form.first_name.data} {form.last_name.data}.")
        return redirect(url_for("login"))
    return render_template("register.html", form=form)


@login_required
@app.route("/user")
def user():
    drugstore_id = current_user.drugstoreId
    shifts_list = list(mongo.db.shifts.find(
        {"drugstoreId": drugstore_id}
    ))
    swaps_list = list(mongo.db.swaps.find(
        {"digitsId": shifts_list[0]["digitsId"]}
    ))

    total_hours = 0
    for shift in shifts_list:
        total_hours += duration_to_readable(shift)

    return render_template("user.html",
                           shifts_list=shifts_list,
                           swaps_list=swaps_list,
                           total_hours=total_hours)


@login_required
@app.route("/admin")
def admin():
    overview = {"count_shifts": int(mongo.db.shifts.count_documents({})),
                "count_pharmacies": len(mongo.db.shifts.distinct("drugstoreId")),
                "count_rotation_plans": len(mongo.db.shifts.distinct("planId")),
                "count_rotations": len(mongo.db.shifts.distinct("digitsId"))
                }
    return render_template("admin.html", overview=overview)


if __name__ == "__main__":
    app.run(
        debug=True)
# todo: debug mode !
