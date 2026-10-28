
import logging

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import generic

from .models import (
    Choice,
    Course,
    Enrollment,
    Question,
    Submission,
)

logger = logging.getLogger(__name__)


def registration_request(request):
    context = {}

    if request.method == "GET":
        return render(
            request,
            "onlinecourse/user_registration_bootstrap.html",
            context,
        )

    username = request.POST.get("username", "").strip()
    password = request.POST.get("psw", "")
    first_name = request.POST.get("firstname", "").strip()
    last_name = request.POST.get("lastname", "").strip()

    if not username or not password:
        context["message"] = "Username and password are required."
        return render(
            request,
            "onlinecourse/user_registration_bootstrap.html",
            context,
        )

    if User.objects.filter(username=username).exists():
        context["message"] = "User already exists."
        return render(
            request,
            "onlinecourse/user_registration_bootstrap.html",
            context,
        )

    user = User.objects.create_user(
        username=username,
        password=password,
        first_name=first_name,
        last_name=last_name,
    )
    login(request, user)
    return redirect("onlinecourse:index")


def login_request(request):
    context = {}

    if request.method != "POST":
        return render(
            request,
            "onlinecourse/user_login_bootstrap.html",
            context,
        )

    username = request.POST.get("username", "").strip()
    password = request.POST.get("psw", "")
    user = authenticate(
        request,
        username=username,
        password=password,
    )

    if user is not None:
        login(request, user)
        return redirect("onlinecourse:index")

    context["message"] = "Invalid username or password."
    return render(
        request,
        "onlinecourse/user_login_bootstrap.html",
        context,
    )


def logout_request(request):
    logout(request)
    return redirect("onlinecourse:index")


def check_if_enrolled(user, course):
    if not user.is_authenticated:
        return False

    return Enrollment.objects.filter(
        user=user,
        course=course,
    ).exists()


class CourseListView(generic.ListView):
    template_name = "onlinecourse/course_list_bootstrap.html"
    context_object_name = "course_list"

    def get_queryset(self):
        courses = Course.objects.order_by("-total_enrollment")[:10]

        for course in courses:
            course.is_enrolled = check_if_enrolled(
                self.request.user,
                course,
            )

        return courses


class CourseDetailView(generic.DetailView):
    model = Course
    template_name = "onlinecourse/course_details_bootstrap.html"


def enroll(request, course_id):
    course = get_object_or_404(Course, pk=course_id)

    if not request.user.is_authenticated:
        return redirect("onlinecourse:login")

    if not check_if_enrolled(request.user, course):
        Enrollment.objects.create(
            user=request.user,
            course=course,
            mode="honor",
        )
        course.total_enrollment += 1
        course.save(update_fields=["total_enrollment"])

    return HttpResponseRedirect(
        reverse(
            "onlinecourse:course_details",
            args=(course.id,),
        )
    )


def extract_answers(request):
    submitted_answers = []

    for key, value in request.POST.items():
        if not key.startswith("choice"):
            continue

        try:
            submitted_answers.append(int(value))
        except (TypeError, ValueError):
            continue

    return submitted_answers


def submit(request, course_id):
    if not request.user.is_authenticated:
        return redirect("onlinecourse:login")

    course = get_object_or_404(Course, pk=course_id)

    enrollment = get_object_or_404(
        Enrollment,
        user=request.user,
        course=course,
    )

    if request.method != "POST":
        return redirect(
            "onlinecourse:course_details",
            pk=course.id,
        )

    submission = Submission.objects.create(
        enrollment=enrollment,
    )

    selected_answers = extract_answers(request)

    valid_choices = Choice.objects.filter(
        question__course=course,
        id__in=selected_answers,
    )

    submission.choices.set(valid_choices)

    return redirect(
        "onlinecourse:show_exam_result",
        course_id=course.id,
        submission_id=submission.id,
    )


def show_exam_result(request, course_id, submission_id):
    if not request.user.is_authenticated:
        return redirect("onlinecourse:login")

    course = get_object_or_404(Course, pk=course_id)

    submission = get_object_or_404(
        Submission,
        pk=submission_id,
        enrollment__course=course,
        enrollment__user=request.user,
    )

    questions = course.question_set.prefetch_related(
        "choice_set",
    ).all()

    total_points = sum(question.grade for question in questions)
    earned_points = 0
    exam_results = []

    for question in questions:
        choices = list(question.choice_set.all())

        selected_choice = submission.choices.filter(
            question=question,
        ).first()

        correct_choice = next(
            (
                choice
                for choice in choices
                if choice.is_correct
            ),
            None,
        )

        is_correct = (
            selected_choice is not None
            and selected_choice.is_correct
        )

        if is_correct:
            earned_points += question.grade

        exam_results.append(
            {
                "question": question,
                "choices": choices,
                "selected_choice": selected_choice,
                "correct_choice": correct_choice,
                "is_correct": is_correct,
            }
        )

    grade = (
        round(earned_points * 100 / total_points)
        if total_points > 0
        else 0
    )

    return render(
        request,
        "onlinecourse/exam_result_bootstrap.html",
        {
            "course": course,
            "submission": submission,
            "grade": grade,
            "earned_points": earned_points,
            "total_points": total_points,
            "exam_results": exam_results,
        },
    )
