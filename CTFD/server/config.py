from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    ctfd_base_url: str = "https://demo.ctfd.io/api/v1"
    ctfd_admin_token: str = ""
    ctfd_session_cookie: str = ""
    mcp_host: str = "0.0.0.0"   
    mcp_port: int = 9999
    file_cache_dir: str = "./file_cache"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "allow"

settings = Settings()
