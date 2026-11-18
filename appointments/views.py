from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from .forms import (
    AppointmentForm,
    MedicalReportForm,
    LoginForm,
    RegisterForm,
)

from .models import (
    Doctor,
    Patient,
    Appointment,
    MedicalReport,
)


# ==========================================================
# HOME
# ==========================================================

def home(request):

    featured_doctors = Doctor.objects.filter(
        is_active=True
    )[:8]

    return render(
        request,
        "home.html",
        {
            "featured_doctors": featured_doctors
        }
    )


# ==========================================================
# DOCTOR LIST
# ==========================================================

def doctor_list(request):

    doctors = Doctor.objects.filter(
        is_active=True
    )

    search = request.GET.get("search")
    department = request.GET.get("department")

    if search:
        doctors = doctors.filter(
            name__icontains=search
        )

    if department:
        doctors = doctors.filter(
            department=department
        )

    return render(
        request,
        "doctors/doctor_list.html",
        {
            "doctors": doctors,
            "search": search,
            "department": department,
        }
    )


# ==========================================================
# DOCTOR DETAIL
# ==========================================================

def doctor_detail(request, pk):

    doctor = get_object_or_404(
        Doctor,
        id=pk
    )

    return render(
        request,
        "doctors/doctor_detail.html",
        {
            "doctor": doctor
        }
    )


# ==========================================================
# BOOK APPOINTMENT
# ==========================================================

@login_required(login_url="login")
def book_appointment(request, pk):

    doctor = get_object_or_404(
        Doctor,
        id=pk
    )

    booked_slots = Appointment.objects.filter(
        doctor=doctor
    ).values_list(
        "appointment_date",
        "time_slot"
    )

    TIME_SLOTS = [
        "09:00 AM",
        "09:30 AM",
        "10:00 AM",
        "10:30 AM",
        "11:00 AM",
        "11:30 AM",
        "02:00 PM",
        "02:30 PM",
        "03:00 PM",
        "03:30 PM",
    ]

    if request.method == "POST":

        form = AppointmentForm(request.POST)

        if form.is_valid():

            patient, created = Patient.objects.get_or_create(

                user=request.user,

                defaults={

                    "name": form.cleaned_data["patient_name"],

                    "age": form.cleaned_data["patient_age"],

                    "gender": form.cleaned_data["patient_gender"],

                    "phone": form.cleaned_data["patient_phone"],

                    "email": form.cleaned_data["patient_email"],

                    "address": form.cleaned_data["patient_address"],

                    "blood_group": form.cleaned_data["patient_blood_group"],
                }
            )

            if not created:

                patient.name = form.cleaned_data["patient_name"]
                patient.age = form.cleaned_data["patient_age"]
                patient.gender = form.cleaned_data["patient_gender"]
                patient.phone = form.cleaned_data["patient_phone"]
                patient.email = form.cleaned_data["patient_email"]
                patient.address = form.cleaned_data["patient_address"]
                patient.blood_group = form.cleaned_data["patient_blood_group"]

                patient.save()

            appointment_date = form.cleaned_data["appointment_date"]
            time_slot = form.cleaned_data["time_slot"]

            if Appointment.objects.filter(
                doctor=doctor,
                appointment_date=appointment_date,
                time_slot=time_slot
            ).exists():

                messages.error(
                    request,
                    "This slot is already booked."
                )

            else:

                appointment = form.save(commit=False)

                appointment.patient = patient
                appointment.doctor = doctor

                appointment.save()

                messages.success(
                    request,
                    "Appointment Booked Successfully."
                )

                return redirect("appointment_success")

    else:

        form = AppointmentForm()

    return render(
        request,
        "appointments/book.html",
        {
            "doctor": doctor,
            "form": form,
            "booked_slots": booked_slots,
            "time_slots": TIME_SLOTS,
            "available_days": doctor.available_days,
        }
    )


# ==========================================================
# AJAX BOOKED SLOTS
# ==========================================================

def get_booked_slots(request, pk):

    doctor = get_object_or_404(
        Doctor,
        id=pk
    )

    date = request.GET.get("date")

    slots = list(

        Appointment.objects.filter(
            doctor=doctor,
            appointment_date=date
        ).values_list(
            "time_slot",
            flat=True
        )

    )

    return JsonResponse(
        {
            "booked_slots": slots
        }
    )


# ==========================================================
# SUCCESS PAGE
# ==========================================================

def appointment_success(request):

    return render(
        request,
        "appointments/success.html"
    )


# ==========================================================
# PATIENT DASHBOARD
# ==========================================================

@login_required(login_url="login")
def patient_dashboard(request):

    patient, created = Patient.objects.get_or_create(

        user=request.user,

        defaults={

            "name": request.user.get_full_name() or request.user.username,

            "age": 0,

            "gender": "Male",

            "phone": "",

            "email": request.user.email,

            "address": "",

            "blood_group": "O+",

        }
    )

    appointments = Appointment.objects.filter(
        patient=patient
    ).order_by(
        "-appointment_date"
    )

    return render(
        request,
        "appointments/dashboard.html",
        {
            "patient": patient,
            "appointments": appointments,
        }
    )


# ==========================================================
# ADMIN DASHBOARD
# ==========================================================

@login_required(login_url="login")
def admin_dashboard(request):

    if not request.user.is_staff:

        messages.error(
            request,
            "Access Denied."
        )

        return redirect("home")

    search = request.GET.get("search")

    appointments = Appointment.objects.select_related(
        "doctor",
        "patient"
    ).order_by(
        "-appointment_date"
    )

    if search:

        appointments = appointments.filter(
            patient__name__icontains=search
        )

    context = {

        "doctor_count": Doctor.objects.count(),

        "patient_count": Patient.objects.count(),

        "appointment_count": Appointment.objects.count(),

        "report_count": MedicalReport.objects.count(),

        "appointments": appointments,

    }

    return render(
        request,
        "adminpanel/dashboard.html",
        context
    )


# ==========================================================
# UPDATE APPOINTMENT STATUS
# ==========================================================

@login_required(login_url="login")
def update_appointment_status(request, pk, status):

    if not request.user.is_staff:

        return redirect("home")

    appointment = get_object_or_404(
        Appointment,
        id=pk
    )

    appointment.status = status

    appointment.save()

    messages.success(
        request,
        "Appointment Updated Successfully."
    )

    return redirect("admin_dashboard")


# ==========================================================
# CREATE / UPDATE MEDICAL REPORT
# ==========================================================

@login_required(login_url="login")
def create_medical_report(request, appointment_id):

    if not request.user.is_staff:
        messages.error(request, "Only admin users can create medical reports.")
        return redirect("home")

    appointment = get_object_or_404(
        Appointment.objects.select_related("patient", "doctor"),
        id=appointment_id
    )

    # A report is linked one-to-one with an appointment.
    # If it already exists, open the same form in edit mode.
    existing_report = MedicalReport.objects.filter(
        appointment=appointment
    ).first()

    if request.method == "POST":
        form = MedicalReportForm(
            request.POST,
            instance=existing_report
        )

        if form.is_valid():
            report = form.save(commit=False)
            report.appointment = appointment
            report.save()

            appointment.status = "COMPLETED"
            appointment.save(update_fields=["status"])

            messages.success(request, "Medical report saved successfully.")
            return redirect("view_medical_report", appointment_id=appointment.id)

    else:
        form = MedicalReportForm(instance=existing_report)

    return render(
        request,
        "reports/create_report.html",
        {
            "appointment": appointment,
            "form": form,
            "is_edit": existing_report is not None,
        }
    )


# ==========================================================
# VIEW MEDICAL REPORT
# ==========================================================

@login_required(login_url="login")
def view_medical_report(request, appointment_id):

    appointment = get_object_or_404(
        Appointment.objects.select_related("patient", "doctor"),
        id=appointment_id
    )

    report = get_object_or_404(
        MedicalReport,
        appointment=appointment
    )

    # Staff can view all reports. Patients can only view their own.
    if not request.user.is_staff:
        if appointment.patient.user_id != request.user.id:
            messages.error(request, "You are not authorized to view this report.")
            return redirect("patient_dashboard")

    return render(
        request,
        "reports/view_report.html",
        {
            "appointment": appointment,
            "report": report,
        }
    )


# ==========================================================
# DOWNLOAD MEDICAL REPORT AS PDF
# ==========================================================

@login_required(login_url="login")
def download_medical_report(request, appointment_id):

    appointment = get_object_or_404(
        Appointment.objects.select_related("patient", "doctor"),
        id=appointment_id
    )

    report = get_object_or_404(
        MedicalReport,
        appointment=appointment
    )

    # Apply the same ownership check to PDF downloads.
    if not request.user.is_staff:
        if appointment.patient.user_id != request.user.id:
            messages.error(request, "You are not authorized to download this report.")
            return redirect("patient_dashboard")

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"Medical Report - {appointment.patient.name}",
        author="Hospital Appointment Portal",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "HospitalTitle",
        parent=styles["Title"],
        fontSize=17,
        leading=22,
        textColor=colors.HexColor("#164e75"),
        alignment=1,
        spaceAfter=6,
    )
    section_style = ParagraphStyle(
        "ReportSection",
        parent=styles["Heading2"],
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#164e75"),
        spaceBefore=12,
        spaceAfter=5,
    )
    body_style = ParagraphStyle(
        "ReportBody",
        parent=styles["BodyText"],
        fontSize=9,
        leading=14,
    )

    story = [
        Paragraph("HOSPITAL MEDICAL REPORT", title_style),
        Paragraph("Patient consultation record", styles["Normal"]),
        Spacer(1, 12),
    ]

    def safe_text(value):
        return escape(str(value if value not in (None, "") else "Not provided")).replace("\\n", "<br/>")

    patient = appointment.patient
    doctor = appointment.doctor

    details = [
        [Paragraph("<b>Patient Name</b>", body_style), Paragraph(safe_text(patient.name), body_style)],
        [Paragraph("<b>Age / Gender</b>", body_style), Paragraph(safe_text(patient.age) + " / " + safe_text(patient.gender), body_style)],
        [Paragraph("<b>Phone</b>", body_style), Paragraph(safe_text(patient.phone), body_style)],
        [Paragraph("<b>Email</b>", body_style), Paragraph(safe_text(patient.email), body_style)],
        [Paragraph("<b>Doctor</b>", body_style), Paragraph("Dr. " + safe_text(doctor.name), body_style)],
        [Paragraph("<b>Department</b>", body_style), Paragraph(safe_text(doctor.get_department_display()), body_style)],
        [Paragraph("<b>Appointment Date</b>", body_style), Paragraph(safe_text(appointment.appointment_date), body_style)],
        [Paragraph("<b>Appointment Time</b>", body_style), Paragraph(safe_text(appointment.time_slot), body_style)],
        [Paragraph("<b>Report Date</b>", body_style), Paragraph(safe_text(report.report_date.strftime("%d %B %Y, %I:%M %p")), body_style)],
    ]

    details_table = Table(details, colWidths=[43 * mm, 117 * mm], hAlign="LEFT")
    details_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eaf1f6")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c8d2dc")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(details_table)

    report_sections = [
        ("Diagnosis", report.diagnosis),
        ("Prescription", report.prescription),
        ("Medicines", report.medicines),
        ("Doctor's Notes", report.doctor_notes),
    ]

    for heading, content in report_sections:
        story.append(Paragraph(escape(heading), section_style))
        story.append(Paragraph(safe_text(content), body_style))

    story.extend([
        Spacer(1, 24),
        Paragraph(
            "This document was generated by the Hospital Appointment Portal.",
            styles["Italic"]
        ),
    ])

    document.build(story)
    pdf = buffer.getvalue()
    buffer.close()

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="medical_report_{appointment.id}.pdf"'
    )
    return response


# ==========================================================
# LOGIN
# ==========================================================

def login_view(request):

    if request.user.is_authenticated:

        return redirect("home")

    form = LoginForm(
        request,
        data=request.POST or None
    )

    if request.method == "POST":

        if form.is_valid():

            user = form.get_user()

            login(request, user)

            messages.success(

                request,

                f"Welcome {user.first_name or user.username}!"

            )

            return redirect("home")

    return render(

        request,

        "registration/login.html",

        {

            "form": form

        }

    )


# ==========================================================
# REGISTER
# ==========================================================

def register_view(request):

    if request.user.is_authenticated:

        return redirect("home")

    form = RegisterForm(request.POST or None)

    if request.method == "POST":

        if form.is_valid():

            username = form.cleaned_data["username"]

            email = form.cleaned_data["email"]

            if User.objects.filter(username=username).exists():

                messages.error(

                    request,

                    "Username already exists."

                )

                return render(

                    request,

                    "registration/register.html",

                    {

                        "form": form

                    }

                )

            if User.objects.filter(email=email).exists():

                messages.error(

                    request,

                    "Email already registered."

                )

                return render(

                    request,

                    "registration/register.html",

                    {

                        "form": form

                    }

                )

            User.objects.create_user(

                username=username,

                email=email,

                password=form.cleaned_data["password"],

                first_name=form.cleaned_data["first_name"],

                last_name=form.cleaned_data["last_name"],

            )

            messages.success(

                request,

                "Registration Successful. Please Login."

            )

            return redirect("login")

    return render(

        request,

        "registration/register.html",

        {

            "form": form

        }

    )


# ==========================================================
# LOGOUT
# ==========================================================

@login_required(login_url="login")
def logout_view(request):

    logout(request)

    messages.success(

        request,

        "Logged out successfully."

    )

    return redirect("login")