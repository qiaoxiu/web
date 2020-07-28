celery_task 是使用celery 实现定时任务的demo ，消息队列使用的是redis 
定时任务与异步任务的唯一多的一个关于 beat_schedule  的配置，配置关于定时任务调度的信息等配置 一般配置在一个单独文件 在celeryconfig.py

beat schedule 是需要读取该配置 定期的更新到中间broker中 供消费者worker  读取 实现定时任务的调用 
worker  具体消费消息来执行 定时任务 



celery -A celery_task beat # 发布任务 将配置更新redis中 

celery -A celery_task worker -l info -P eventlet # 启动worker 需要 安装 eventlet pip install eventlet 


worker  会不停的读取消息 消费消息 定时的调用 taskxx 输出


 




