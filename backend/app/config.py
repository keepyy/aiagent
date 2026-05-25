from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    use_mock_llm: bool = True

    @property
    def effective_mock(self) -> bool:
        return self.use_mock_llm or not self.openai_api_key.strip()


settings = Settings()
