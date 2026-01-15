from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


@dataclass(frozen=True)
class Category:
    label: str
    thread_prefix: str
    senders: list[str]
    subject_templates: list[str]
    snippet_templates: list[str]
    body_templates: list[str]


CATEGORIES: list[Category] = [
    Category(
        label="SCHOOL",
        thread_prefix="t-school",
        senders=[
            "Google Classroom <no-reply@classroom.google.com>",
            "MyCourses <noreply@mycourses.school>",
            "TA Office Hours <ta@cs.school>",
        ],
        subject_templates=[
            "Assignment due {day_name}",
            "New grade posted: {course}",
            "Reminder: quiz in {course}",
            "{course}: lecture notes uploaded",
            "Project checkpoint: {course}",
        ],
        snippet_templates=[
            "Don’t forget to submit by {time_str}.",
            "A new item was posted in {course}.",
            "Your grade has been updated.",
        ],
        body_templates=[
            "Hi, this is a reminder that your {course} assignment is due on {date_str} at {time_str}.",
            "New material for {course} is now available. Please review before {day_name}.",
            "Office hours update: {course} support is available on {day_name} at {time_str}.",
        ],
    ),
    Category(
        label="PROMOS",
        thread_prefix="t-promos",
        senders=[
            "Zara <news@zara.com>",
            "Amazon Deals <deals@amazon.com>",
            "Sephora <hello@sephora.com>",
            "Best Buy <offers@bestbuy.ca>",
        ],
        subject_templates=[
            "{percent}% off ends tonight",
            "Limited time: {percent}% off selected items",
            "Flash sale: {category} deals",
            "Your coupon expires {day_name}",
            "New arrivals: {category}",
        ],
        snippet_templates=[
            "Shop now before it’s gone.",
            "Limited quantities available.",
            "Offer valid until {time_str}.",
        ],
        body_templates=[
            "Save {percent}% on {category}. Offer valid until {date_str} {time_str}.",
            "New arrivals in {category}. Free returns available.",
            "Your exclusive code gives {percent}% off on selected items.",
        ],
    ),
    Category(
        label="BILLS",
        thread_prefix="t-bills",
        senders=[
            "Hydro Quebec <billing@hydroquebec.example>",
            "Rogers <billing@rogers.example>",
            "Bank Statement <statements@bank.example>",
            "Insurance Co <billing@insurance.example>",
        ],
        subject_templates=[
            "Your bill is ready ({month})",
            "Payment confirmation ({amount})",
            "Statement available: {month}",
            "Reminder: payment due {date_str}",
        ],
        snippet_templates=[
            "View your statement online.",
            "Your payment has been received.",
            "Payment due soon.",
        ],
        body_templates=[
            "Your {month} bill is now available. Amount due: {amount}. Due date: {date_str}.",
            "We received your payment of {amount}. Thank you.",
            "Your statement for {month} is ready. Please review for accuracy.",
        ],
    ),
    Category(
        label="WORK",
        thread_prefix="t-work",
        senders=[
            "GitHub <noreply@github.com>",
            "CI Alerts <ci@inboxsherpa.local>",
            "Project Update <pm@team.example>",
            "Interview Scheduling <recruiting@company.example>",
        ],
        subject_templates=[
            "Build failed: {repo}",
            "PR review requested: {repo}",
            "Meeting notes: {project}",
            "Action required: {task}",
            "Interview schedule update",
        ],
        snippet_templates=[
            "Please check the latest run logs.",
            "You have a pending review request.",
            "Summary of decisions and next steps.",
        ],
        body_templates=[
            "CI status: {repo} reported a failure at {time_str}. Please investigate.",
            "PR needs review in {repo}. Deadline: {day_name}.",
            "Next steps for {project}: {task}. Please confirm by {date_str}.",
        ],
    ),
    Category(
        label="CALENDAR",
        thread_prefix="t-calendar",
        senders=[
            "Google Calendar <calendar-notification@google.com>",
            "Zoom <no-reply@zoom.us>",
            "Eventbrite <orders@eventbrite.com>",
        ],
        subject_templates=[
            "Event reminder: {event}",
            "Invitation: {event}",
            "Updated: {event} ({day_name})",
            "Your meeting starts in 10 minutes",
        ],
        snippet_templates=[
            "Location: {location}.",
            "Join link available.",
            "Please respond to the invitation.",
        ],
        body_templates=[
            "Reminder: {event} on {date_str} at {time_str}. Location: {location}.",
            "Invitation: {event}. Please RSVP. Time: {time_str}.",
            "Join your meeting: {event}. Link: https://example.com/join/{id_short}",
        ],
    ),
]

COURSES = ["CIVL-203", "INF1015", "COMM-220", "ECON-110", "MATH-240"]
PRODUCT_CATS = ["jackets", "shoes", "headphones", "skincare", "jeans", "laptops"]
REPOS = ["InboxSherpa", "MindGarden", "portfolio-site", "infra"]
PROJECTS = ["InboxSherpa MVP", "Data pipeline", "Resume refresh"]
TASKS = ["review PR", "fix failing test", "reply to email", "prepare slides", "update README"]
EVENTS = ["Team Standup", "Client Call", "Career Fair", "Office Hours", "Study Group"]
LOCATIONS = ["Online", "Room 201", "Zoom", "Campus Library", "Building A"]
MONTHS = ["January", "February", "March", "April", "May", "June"]
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate sample inbox JSON for Day 3 import.")
    parser.add_argument("--out", default="data/sample_inbox.json", help="Output JSON file path.")
    parser.add_argument("--n", type=int, default=500, help="Number of messages to generate.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for determinism.")
    args = parser.parse_args()

    random.seed(args.seed)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime(2026, 1, 12, 12, 0, tzinfo=timezone.utc)


    messages: list[dict] = []
    for i in range(args.n):
        cat = random.choice(CATEGORIES)

        # spread over last 14 days
        minutes_ago = random.randint(0, 2 * 24 * 60)  # keep it within last 48h of demo day
        ts = now - timedelta(minutes=minutes_ago)

        percent = random.choice([10, 15, 20, 25, 30, 40, 50])
        amount = f"${random.randint(20, 350)}.{random.randint(0, 99):02d}"
        course = random.choice(COURSES)
        product_cat = random.choice(PRODUCT_CATS)
        repo = random.choice(REPOS)
        project = random.choice(PROJECTS)
        task = random.choice(TASKS)
        event = random.choice(EVENTS)
        location = random.choice(LOCATIONS)
        month = random.choice(MONTHS)
        day_name = random.choice(DAY_NAMES)

        ctx = {
            "percent": percent,
            "amount": amount,
            "course": course,
            "category": product_cat,
            "repo": repo,
            "project": project,
            "task": task,
            "event": event,
            "location": location,
            "month": month,
            "day_name": day_name,
            "date_str": ts.date().isoformat(),
            "time_str": ts.strftime("%H:%M"),
            "id_short": f"{i:06d}",
        }

        sender = random.choice(cat.senders)
        subject = random.choice(cat.subject_templates).format(**ctx)
        snippet = random.choice(cat.snippet_templates).format(**ctx)
        body = random.choice(cat.body_templates).format(**ctx)

        # a few threads per category
        thread_bucket = random.randint(1, 40)
        thread_external_id = f"{cat.thread_prefix}-{thread_bucket:02d}"

        msg = {
            "external_id": f"json-{i+1:06d}",  # unique across dataset
            "thread_external_id": thread_external_id,
            "timestamp": iso_z(ts),
            "sender": sender,
            "subject": subject,
            "snippet": snippet,
            "body_text": body,
            "labels": [cat.label],
        }

        messages.append(msg)

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(messages)} messages to {out_path}")


if __name__ == "__main__":
    main()
