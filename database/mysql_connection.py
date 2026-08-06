from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

import os
from dotenv import load_dotenv

load_dotenv()

# .env에 저장된 MYSQL 정보 로드 후 매핑
user   = os.getenv("MYSQL_USER")
passwd = os.getenv("MYSQL_PASSWORD")
host   = os.getenv("MYSQL_HOST")
port   = os.getenv("MYSQL_PORT", "3306")
db     = os.getenv("MYSQL_DATABASE")

DB_URL = f'mysql+pymysql://{user}:{passwd}@{host}:{port}/{db}?charset=utf8'

engine = create_engine(DB_URL, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base() # ORM 모델 생성