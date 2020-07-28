from celery_task.celery import app

def test3():
    print("test3----------------")

def test4():
    print("test4--------------")
    test3()

@app.task
def celery_run():
    test3()
    test4()
    return "task2"


if __name__ == '__main__':
    celery_run()
