from django.shortcuts import render, redirect
from django.contrib.auth.hashers import make_password, check_password
from django.conf import settings
import os
import firebase_admin
from firebase_admin import credentials, firestore, storage
from google.cloud.firestore_v1.base_query import FieldFilter
from datetime import datetime, timezone
import uuid

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
firebase_config_path = os.path.join(
    BASE_DIR, "serviceAccountKey.json"
)  # substitute with environment variable in production
cred = credentials.Certificate(firebase_config_path)
firebase_admin.initialize_app(
    cred,
    {"storageBucket": "opcuafusion.appspot.com"},
)


def home(request):
    return render(request, "user_account/home.html")


def login_page(request):

    if request.session.get("is_logged_in"):
        return redirect("dashboard")

    if request.method == "POST":
        email = request.POST.get("email").strip().lower()
        password = request.POST.get("password").strip()

        user = get_user_info(email)

        if user["approved"] == True and check_password(password, user["password"]):

            request.session["is_logged_in"] = True
            request.session["email"] = email
            return redirect("dashboard")
        elif user["approved"] == False:
            return render(
                request,
                "user_account/login.html",
                {"error": "Call ------------ for account approval"},
            )
        else:
            return render(
                request, "user_account/login.html", {"error": "Invalid credentials"}
            )

    return render(request, "user_account/login.html")


def register_page(request):

    if request.session.get("is_logged_in"):
        return redirect("dashboard")

    if request.method == "POST":

        name = request.POST.get("name").strip().title()
        email = request.POST.get("email").lower()
        password = request.POST.get("password")
        job_role = request.POST.get("job_role").strip().title()
        company_name = request.POST.get("company_name").strip().title()
        description = request.POST.get("description").strip()

        db = firestore.client()
        users_collection_ref = db.collection("users")

        field_filter1 = FieldFilter("email", "==", email)
        query = users_collection_ref.where(filter=field_filter1).limit(1).stream()

        user_exists = any(query)

        if not user_exists:

            hashed_password = make_password(password)

            user_data = {
                "name": name,
                "email": email,
                "password": hashed_password,
                "job_role": job_role,
                "company_name": company_name,
                "description": description,
                "account_created_timestamp": datetime.now(timezone.utc),
                "account_updated_timestamp": datetime.now(timezone.utc),
                "approved": False,
            }

            users_collection_ref.add(user_data)

            return redirect("login")
        else:
            return render(
                request, "user_account/register.html", {"error": "User already exists"}
            )

    return render(request, "user_account/register.html")


def dashboard(request):

    if not request.session.get("is_logged_in"):
        return redirect("login")

    email = request.session.get("email")
    user = get_user_info(email)
    user_id = get_user_info(email, True)

    db = firestore.client()
    quotes_collection_ref = db.collection("quote_requests")
    query = quotes_collection_ref.where("user_id", "==", user_id).stream()

    quote_requests = []
    for doc in query:
        data = doc.to_dict()
        quote_requests.append(
            {
                "id": doc.id,
                "title": data.get("title"),
                "request_timestamp": data.get("request_timestamp"),
                "finish_timestamp": data.get("finish_timestamp"),
                "status": data.get("status"),
                "report": data.get("report"),
                "file_url": data.get("file_url"),
            }
        )
    return render(
        request,
        "user_account/dashboard.html",
        {
            "name": user["name"],
            "email": user["email"],
            "job_role": user["job_role"],
            "company_name": user["company_name"],
            "description": user["description"],
            "quote_requests": quote_requests,
        },
    )


def quote_request_info(request, quote_id):

    if not request.session.get("is_logged_in"):
        return redirect("login")

    email = request.session.get("email")
    user_id = get_user_info(email, get_id=True)

    db = firestore.client()
    quotes_collection_ref = db.collection("quote_requests")
    doc_ref = quotes_collection_ref.document(quote_id)
    doc = doc_ref.get()

    if doc.exists:
        quote = doc.to_dict()

        if quote.get("user_id") != user_id:

            return redirect("login")

        return render(request, "user_account/quote_request_info.html", {"quote": quote})
    else:
        return redirect("home")


def quote_request(request):

    if not request.session.get("is_logged_in"):
        return redirect("login")

    if request.method == "POST":

        title = request.POST.get("title")
        description = request.POST.get("description")
        gcode = request.POST.get("gcode")
        quantity = request.POST.get("quantity")
        design_units = request.POST.get("design_units")
        material = request.POST.get("material")
        aluminum_type = request.POST.get("aluminum_type")
        surface_finish = request.POST.get("surface_finish")
        tolerance = request.POST.get("tolerance")

        uploaded_file = request.FILES.get("file_input")
        technical_drawing = request.FILES.get("technical_drawing")

        required_fields = [
            title,
            description,
            quantity,
            design_units,
            material,
            surface_finish,
            tolerance,
            uploaded_file,
        ]
        if not all(required_fields):
            return render(
                request,
                "user_account/quote_request.html",
                {"error": "Please fill in all required fields."},
            )

        if material == "Aluminum":
            return render(
                request,
                "user_account/quote_request.html",
                {"error": "Please select the type of Aluminum."},
            )

        if not uploaded_file.name.endswith(".zip"):
            return render(
                request,
                "user_account/quote_request.html",
                {"error": "Only .zip files are allowed for the main upload."},
            )

        max_file_size = 20 * 1024 * 1024
        if uploaded_file.size > max_file_size:
            return render(
                request,
                "user_account/quote_request.html",
                {"error": "File size exceeds the maximum limit of 20 MB."},
            )

        try:

            bucket = storage.bucket()
            unique_filename = f"{uuid.uuid4()}_{uploaded_file.name}"
            blob = bucket.blob(f"opcua_cloud/{unique_filename}")
            blob.upload_from_file(uploaded_file.file, content_type="application/zip")

            blob.make_public()
            file_url = blob.public_url

            technical_drawing_url = None
            if technical_drawing:

                unique_td_filename = f"{uuid.uuid4()}_{technical_drawing.name}"
                td_blob = bucket.blob(f"opcua_cloud/{unique_td_filename}")
                td_blob.upload_from_file(technical_drawing.file)
                td_blob.make_public()
                technical_drawing_url = td_blob.public_url

            form_data_unedited = {
                "user_id": get_user_info(request.session.get("email"), True),
                "title": title,
                "description": description,
                "gcode": gcode,
                "quantity": quantity,
                "design_units": design_units,
                "material": material,
                "aluminum_type": aluminum_type,
                "surface_finish": surface_finish,
                "tolerance": tolerance,
                "file_url": file_url,
                "technical_drawing_url": technical_drawing_url,
                "request_timestamp": datetime.now(timezone.utc),
            }

            form_data_edited = form_data_unedited.copy()
            form_data_edited.update(
                {
                    "title": title.title(),
                    "description": description.capitalize(),
                    "start_timestamp": None,
                    "status": None,
                    "finish_timestamp": None,
                    "report": None,
                    "updated_timestamp": None,
                }
            )

            db = firestore.client()
            forms_collection_ref_unedited = db.collection("quote_requests_unedited")
            forms_collection_ref_unedited.add(form_data_unedited)

            forms_collection_ref = db.collection("quote_requests")
            forms_collection_ref.add(form_data_edited)

            return render(
                request,
                "user_account/quote_request.html",
                {"success": "Form submitted successfully."},
            )

        except Exception as e:
            return render(
                request,
                "user_account/quote_request.html",
                {"error": f"An error occurred: {str(e)}"},
            )

    else:
        return render(request, "user_account/quote_request.html")


def logout(request):
    request.session.flush()
    return redirect("home")


def get_user_info(email, get_id=None):

    db = firestore.client()

    users_collection_ref = db.collection("users")
    query = users_collection_ref.where("email", "==", email).stream()

    user = None
    for doc in query:
        if get_id != None:
            return doc.id
        user = doc.to_dict()
        break
    return user


def guide(request):
    return render(request, "user_account/guide.html")
