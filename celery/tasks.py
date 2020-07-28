import time
from celery import Celery


broker = 'redis://localhost:6378/1'
backend = 'redis://localhost:6378/2'
app = Celery('my_task',broker=broker,backend=backend)   


@app.task
def add(x,y):
    print('-----------------add --------------------')
    time.sleep(10)                  
    return x + y

