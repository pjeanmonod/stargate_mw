from django.apps import AppConfig

class Cloud01Config(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'middleware.apps.cloud01'

    def ready(self):
        import middleware.apps.cloud01.signals  

