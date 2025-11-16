from django.apps import AppConfig

class Cloud01Config(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'cloud01'

    def ready(self):
        import cloud01.signals  # noqa
