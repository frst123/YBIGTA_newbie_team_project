import json

from typing import Dict, Optional

from app.user.user_schema import User
from app.config import USER_DATA

from sqlalchemy import Column, String
from sqlalchemy.orm import Session
from app.user.user_schema import User
from database.mysql_connection import Base

## DB CRUD 클래스
## 테이블 이름: users

class UserModel(Base):
    __tablename__ = "users"

    email    = Column(String(255), primary_key=True, index=True)
    password = Column(String(255), nullable=False)
    username = Column(String(100), nullable=False)



class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _to_schema(self, row: UserModel) -> User:
        return User(email=row.email, password=row.password, username=row.username)

    def get_user_by_email(self, email: str) -> Optional[User]:
        row = self.db.query(UserModel).filter(UserModel.email == email).first()
        return self._to_schema(row) if row else None

    def save_user(self, user: User) -> User:
        row = self.db.query(UserModel).filter(UserModel.email == user.email).first()
        if row is None:                      # Create
            row = UserModel(
                email=user.email,
                password=user.password,
                username=user.username,
            )
            self.db.add(row)
        else:                                # Update
            row.password = user.password
            row.username = user.username
        self.db.commit()
        self.db.refresh(row)
        return self._to_schema(row)

    def delete_user(self, user: User) -> User:
        row = self.db.query(UserModel).filter(UserModel.email == user.email).first()
        if row is not None:
            self.db.delete(row)
            self.db.commit()
        return user