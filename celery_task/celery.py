from celery import Celery 

app = Celery("celery_test")

app.config_from_object("celery_task.celeryconfig")
