"""Random activity suggestions for the planner page."""

import random

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter(prefix="/api/suggestions", tags=["suggestions"])

SUGGESTIONS: dict[str, list[str]] = {
    "outdoors": [
        "Go for a walk without your phone",
        "Go on a hike somewhere you haven't been",
        "Have a picnic in the park",
        "Take a bike ride",
        "Watch the sunset somewhere with a view",
    ],
    "social": [
        "Hang out with friends",
        "Call a family member you haven't spoken to in a while",
        "Invite someone for coffee",
        "Cook dinner for friends",
        "Join a local meetup or class",
    ],
    "rest": [
        "Have a slow morning with no plans",
        "Take a nap without feeling guilty",
        "Read a book for an hour",
        "Take a long bath or shower and switch off",
        "Go to bed early",
    ],
    "creative": [
        "Try a new recipe",
        "Sketch or doodle for 20 minutes",
        "Write a letter to your future self",
        "Make a playlist for the week",
        "Take photos on a walk around your area",
    ],
    "learning": [
        "Visit a museum or gallery",
        "Watch a documentary",
        "Practise a language for 20 minutes",
        "Learn something new from a YouTube tutorial",
        "Go to a library and browse",
    ],
}


class Suggestion(BaseModel):
    text: str
    category: str


ALL_SUGGESTIONS = [Suggestion(text=text, category=category) for category, texts in SUGGESTIONS.items() for text in texts]


@router.get("/random", response_model=Suggestion)
def random_suggestion(
    exclude: str | None = Query(default=None, max_length=200, description="Skip this suggestion, so the same one isn't shown twice in a row"),
):
    choices = [s for s in ALL_SUGGESTIONS if s.text != exclude] or ALL_SUGGESTIONS
    return random.choice(choices)
