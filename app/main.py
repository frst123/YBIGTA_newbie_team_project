from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import uvicorn
import os

from app.review.review_router import review
from app.user.user_router import user
from app.config import PORT

from database.mysql_connection import engine, Base
from app.user import user_repository


app = FastAPI()
app.include_router(user)
app.include_router(review)

Base.metadata.create_all(bind=engine)

static_path = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_path), name="static")

app.include_router(user)

if __name__=="__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=PORT, reload=True)
