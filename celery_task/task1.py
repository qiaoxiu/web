from celery_task.celery import app

def test1():
    print("-------------test1----------------")

def test2():
    print("-------------test2--------------")
    test1()

@app.task
def celery_run():
    test1()
    test2()
    return "task1"

if __name__ == '__main__':
    celery_run()
