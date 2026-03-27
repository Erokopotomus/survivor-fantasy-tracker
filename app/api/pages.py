import os
from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

router = APIRouter(tags=["Pages"])


@router.get("/", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html")


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    return templates.TemplateResponse(request, "dashboard.html")


@router.get("/cast", response_class=HTMLResponse)
async def cast_page(request: Request):
    return templates.TemplateResponse(request, "cast.html")


@router.get("/scoring", response_class=HTMLResponse)
async def scoring_page(request: Request):
    return templates.TemplateResponse(request, "scoring.html")


@router.get("/episode-scores", response_class=HTMLResponse)
async def episode_scores_page(request: Request):
    return templates.TemplateResponse(request, "episode_scores.html")


@router.get("/castaway/{castaway_id}", response_class=HTMLResponse)
async def castaway_detail_page(request: Request, castaway_id: int):
    return templates.TemplateResponse(request, "castaway_detail.html", {"castaway_id": castaway_id})


@router.get("/rosters", response_class=HTMLResponse)
async def rosters_page(request: Request):
    return templates.TemplateResponse(request, "rosters.html")


@router.get("/draft", response_class=HTMLResponse)
async def draft_page(request: Request):
    return templates.TemplateResponse(request, "draft.html")


@router.get("/weekly-recap", response_class=HTMLResponse)
async def weekly_recap_page(request: Request):
    return templates.TemplateResponse(request, "weekly_recap.html")


@router.get("/rules", response_class=HTMLResponse)
async def rules_page(request: Request):
    return templates.TemplateResponse(request, "rules.html")
