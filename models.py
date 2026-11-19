import json
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from db import Base 

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(120), unique=True, nullable=False)
    password = Column(String(255), nullable=False)

# Backward-compatible alias
user = User

class Reports(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String(150), nullable=True)
    resume_text = Column(Text, nullable=True)
    result = Column(Text, nullable=True)  # JSON-encoded string
    created_at = Column(DateTime, default=datetime.utcnow)

    def get_result_data(self):
        """Returns the result as a python dictionary safely."""
        if not self.result:
            return {}
        try:
            return json.loads(self.result)
        except Exception:
            return {"error": "Invalid result data", "raw": self.result}

# Backward-compatible alias
Report = Reports
