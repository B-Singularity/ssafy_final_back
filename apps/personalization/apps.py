from django.apps import AppConfig

class PersonalizationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.personalization'
    # verbose_name = "개인화" # 선택 사항