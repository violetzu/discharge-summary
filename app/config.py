import os


class Settings:
    # vLLM — separate instance per model
    SUMMARY_BASE_URL: str = os.getenv("SUMMARY_BASE_URL", "http://vllm-summary:8010")
    VALIDATION_BASE_URL: str = os.getenv("VALIDATION_BASE_URL", "http://vllm-validation:8011")

    # must match --served-model-name in vLLM
    SUMMARY_MODEL: str = os.getenv("SUMMARY_MODEL", "gemma-summary")
    VALIDATION_MODEL: str = os.getenv("VALIDATION_MODEL", "gemma-validation")

    API_KEY: str = os.getenv("API_KEY", "NONE")
    HIS_KEY: str = os.getenv("HIS_KEY", "NONE")


settings = Settings()
