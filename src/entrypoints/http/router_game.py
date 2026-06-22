"""Game router — endpoints land in tasks 3.6–3.8."""

from fastapi import APIRouter

router = APIRouter(prefix="/game", tags=["game"])
