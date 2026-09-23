from typing import List, Optional
from pydantic import BaseModel

class FolderInfo(BaseModel):
    name: str
    created_at: str

class FileInfo(BaseModel):
    name: str
    size: int
    modified_at: str
    url: str
    cover_url: Optional[str] = None

class CreateFolderRequest(BaseModel):
    name: str
    path: str = ""  # 父目录（多级相对路径，如「一年级/语文」），空 = 根目录

class RenameFileRequest(BaseModel):
    new_name: str

class SendEmailRequest(BaseModel):
    folder_name: str
    files: List[str]
    to_email: Optional[str] = None
