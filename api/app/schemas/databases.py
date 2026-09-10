from pydantic import BaseModel, ConfigDict
from typing import Optional

class DatabaseConnectionBase(BaseModel):
    name: str
    db_type: str
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    database_name: Optional[str] = None
    file_path: Optional[str] = None

class DatabaseConnectionCreate(DatabaseConnectionBase):
    password: Optional[str] = None

class DatabaseConnectionResponse(DatabaseConnectionBase):
    id: str
    
    model_config = ConfigDict(from_attributes=True)
