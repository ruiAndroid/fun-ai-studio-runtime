from pydantic import BaseModel, Field
from typing import Optional


class DeployAppRequest(BaseModel):
    userId: str = Field(min_length=1)
    appId: str = Field(min_length=1)
    image: str = Field(min_length=1)
    containerPort: int = Field(default=3000, ge=1, le=65535)
    basePath: str = Field(default="", description="external path prefix like /apps/{appId}")


class StopAppRequest(BaseModel):
    userId: str = Field(min_length=1)
    appId: str = Field(min_length=1)


class DeleteAppRequest(BaseModel):
    userId: str = Field(min_length=1)
    appId: str = Field(min_length=1)


class AppStatusResponse(BaseModel):
    appId: str
    containerName: str
    exists: bool
    running: bool
    image: Optional[str] = None
    port: Optional[int] = None

